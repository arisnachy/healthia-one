from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from healthia_one.google_ai_transport import build_google_ai_client
from healthia_one.opportunity_autopilot import (
    AssistanceProgram,
    Discovery,
    DiscoveryKind,
    EvidenceTier,
    SourceCitation,
    WatchTopic,
    discovery_fingerprint,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchCandidate(BaseModel):
    source_name: str
    source_id: str
    title: str
    url: str
    publisher: str = ""
    abstract: str = ""
    published_at: datetime | None = None
    evidence_tier: EvidenceTier = EvidenceTier.UNKNOWN
    peer_reviewed: bool = False
    official: bool = False
    source_claims: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class SourceFetchError(RuntimeError):
    pass


@dataclass
class UrlTransport:
    timeout_seconds: int = 12
    user_agent: str = "HealthIA-ONE/0.8 research-radar"

    def _request(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, application/xml, text/xml, */*",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read()
        except Exception as exc:  # pragma: no cover - network behavior
            raise SourceFetchError(f"Research source request failed: {url}") from exc

    def json(self, url: str) -> dict[str, Any]:
        try:
            return json.loads(self._request(url).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceFetchError(f"Research source returned invalid JSON: {url}") from exc

    def text(self, url: str) -> str:
        try:
            return self._request(url).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceFetchError(f"Research source returned invalid UTF-8: {url}") from exc


def _parse_date(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidates = [raw, raw[:10], raw.replace(" ", "-")]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    for fmt in ("%Y %b %d", "%Y %b", "%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def infer_evidence_tier(title: str, publication_types: list[str] | None = None) -> EvidenceTier:
    text = " ".join([title, *(publication_types or [])]).lower()
    if "guideline" in text or "practice guideline" in text:
        return EvidenceTier.GUIDELINE
    if "systematic review" in text or "meta-analysis" in text or "meta analysis" in text:
        return EvidenceTier.SYSTEMATIC_REVIEW
    if "randomized" in text or "randomised" in text or "clinical trial" in text:
        return EvidenceTier.RANDOMIZED_TRIAL
    if "cohort" in text or "case-control" in text or "observational" in text:
        return EvidenceTier.OBSERVATIONAL
    if "case series" in text or "case report" in text:
        return EvidenceTier.CASE_SERIES
    if "preprint" in text:
        return EvidenceTier.PREPRINT
    return EvidenceTier.UNKNOWN


def _xml_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


class PubMedSource:
    ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def __init__(self, transport: UrlTransport | None = None) -> None:
        self.transport = transport or UrlTransport()

    def search(self, topic: WatchTopic, *, max_results: int = 5, days: int = 120) -> list[ResearchCandidate]:
        since = (utc_now() - timedelta(days=days)).strftime("%Y/%m/%d")
        term = f'({topic.condition}) AND {since}:3000/12/31[pdat]'
        params = urllib.parse.urlencode(
            {
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": max(1, min(max_results, 20)),
                "sort": "pub_date",
            }
        )
        payload = self.transport.json(f"{self.ESEARCH}?{params}")
        ids = [str(item) for item in payload.get("esearchresult", {}).get("idlist", []) if item]
        if not ids:
            return []
        fetch_params = urllib.parse.urlencode(
            {
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
            }
        )
        xml = self.transport.text(f"{self.EFETCH}?{fetch_params}")
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise SourceFetchError("PubMed EFetch returned invalid XML") from exc

        output: list[ResearchCandidate] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = _xml_text(article.find(".//MedlineCitation/PMID"))
            title = _xml_text(article.find(".//Article/ArticleTitle"))
            abstract = " ".join(
                _xml_text(node) for node in article.findall(".//Article/Abstract/AbstractText")
            ).strip()
            journal = _xml_text(article.find(".//Article/Journal/Title"))
            publication_types = [
                _xml_text(node) for node in article.findall(".//Article/PublicationTypeList/PublicationType")
            ]
            tier = infer_evidence_tier(title, publication_types)
            date_value = (
                _xml_text(article.find(".//Article/Journal/JournalIssue/PubDate/MedlineDate"))
                or " ".join(
                    value
                    for value in (
                        _xml_text(article.find(".//Article/Journal/JournalIssue/PubDate/Year")),
                        _xml_text(article.find(".//Article/Journal/JournalIssue/PubDate/Month")),
                        _xml_text(article.find(".//Article/Journal/JournalIssue/PubDate/Day")),
                    )
                    if value
                )
            )
            if not pmid or not title:
                continue
            output.append(
                ResearchCandidate(
                    source_name="PubMed",
                    source_id=f"PMID:{pmid}",
                    title=title,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    publisher=journal or "PubMed / NLM",
                    abstract=abstract[:8000],
                    published_at=_parse_date(date_value),
                    evidence_tier=tier,
                    peer_reviewed=False,
                    official=True,
                    source_claims=[abstract[:1200]] if abstract else [],
                    raw={
                        "publication_types": publication_types,
                        "peer_review_status": "unknown",
                    },
                )
            )
        return output


class EuropePmcSource:
    SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def __init__(self, transport: UrlTransport | None = None) -> None:
        self.transport = transport or UrlTransport()

    def search(self, topic: WatchTopic, *, max_results: int = 5, days: int = 120) -> list[ResearchCandidate]:
        query = f'"{topic.condition}" sort_date:y'
        params = urllib.parse.urlencode(
            {
                "query": query,
                "resultType": "core",
                "format": "json",
                "pageSize": max(1, min(max_results, 20)),
            }
        )
        payload = self.transport.json(f"{self.SEARCH}?{params}")
        results = payload.get("resultList", {}).get("result", [])
        cutoff = utc_now() - timedelta(days=days)
        output: list[ResearchCandidate] = []
        for item in results:
            title = str(item.get("title") or "").strip()
            source = str(item.get("source") or "MED").strip()
            identifier = str(item.get("id") or item.get("pmid") or item.get("pmcid") or "").strip()
            if not title or not identifier:
                continue
            journal_info = item.get("journalInfo") if isinstance(item.get("journalInfo"), dict) else {}
            published = _parse_date(
                item.get("firstPublicationDate")
                or item.get("electronicPublicationDate")
                or journal_info.get("printPublicationDate")
            )
            if published and published < cutoff:
                continue
            publication_types = [str(item.get("pubType") or "")]
            tier = infer_evidence_tier(title, publication_types)
            is_preprint = bool(item.get("isPreprint")) or tier == EvidenceTier.PREPRINT
            abstract = str(item.get("abstractText") or "").strip()
            output.append(
                ResearchCandidate(
                    source_name="Europe PMC",
                    source_id=f"{source}:{identifier}",
                    title=title,
                    url=f"https://europepmc.org/article/{source}/{identifier}",
                    publisher=str(item.get("journalTitle") or "Europe PMC"),
                    abstract=abstract[:8000],
                    published_at=published,
                    evidence_tier=EvidenceTier.PREPRINT if is_preprint else tier,
                    peer_reviewed=False,
                    official=True,
                    source_claims=[abstract[:1200]] if abstract else [],
                    raw={
                        "cited_by_count": item.get("citedByCount"),
                        "is_preprint": is_preprint,
                        "peer_review_status": "unknown",
                    },
                )
            )
        return output


class ClinicalTrialsSource:
    SEARCH = "https://clinicaltrials.gov/api/v2/studies"

    def __init__(self, transport: UrlTransport | None = None) -> None:
        self.transport = transport or UrlTransport()

    def search(self, topic: WatchTopic, *, max_results: int = 5, days: int = 365) -> list[ResearchCandidate]:
        params = urllib.parse.urlencode(
            {
                "query.term": topic.condition,
                "pageSize": max(1, min(max_results, 20)),
                "format": "json",
            }
        )
        payload = self.transport.json(f"{self.SEARCH}?{params}")
        output: list[ResearchCandidate] = []
        for study in payload.get("studies", []):
            protocol = study.get("protocolSection", {})
            identification = protocol.get("identificationModule", {})
            status = protocol.get("statusModule", {})
            description = protocol.get("descriptionModule", {})
            nct_id = str(identification.get("nctId") or "").strip()
            title = str(
                identification.get("briefTitle")
                or identification.get("officialTitle")
                or ""
            ).strip()
            if not nct_id or not title:
                continue
            updated = _parse_date(
                (status.get("lastUpdatePostDateStruct") or {}).get("date")
                or (status.get("studyFirstPostDateStruct") or {}).get("date")
            )
            summary = str(description.get("briefSummary") or "").strip()
            output.append(
                ResearchCandidate(
                    source_name="ClinicalTrials.gov",
                    source_id=nct_id,
                    title=title,
                    url=f"https://clinicaltrials.gov/study/{nct_id}",
                    publisher="ClinicalTrials.gov / NLM",
                    abstract=summary[:8000],
                    published_at=updated,
                    evidence_tier=EvidenceTier.CLINICAL_TRIAL,
                    peer_reviewed=False,
                    official=True,
                    source_claims=[summary[:1200]] if summary else [],
                    raw={
                        "overall_status": status.get("overallStatus"),
                        "conditions": protocol.get("conditionsModule", {}).get("conditions", []),
                        "peer_review_status": "not_applicable",
                    },
                )
            )
        return output


def candidate_to_discovery(
    topic: WatchTopic,
    candidate: ResearchCandidate,
    *,
    relevance_score: float,
    interrupt_score: float,
) -> Discovery:
    kind = (
        DiscoveryKind.CLINICAL_TRIAL
        if candidate.evidence_tier == EvidenceTier.CLINICAL_TRIAL
        else DiscoveryKind.SCIENTIFIC
    )
    return Discovery(
        fingerprint=discovery_fingerprint(
            source_id=candidate.source_id,
            title=candidate.title,
            condition=topic.condition,
            subject_id=topic.subject_id,
        ),
        kind=kind,
        title=candidate.title,
        condition=topic.condition,
        subject_id=topic.subject_id,
        subject_label=topic.subject_label,
        relation=topic.relation,
        summary=candidate.abstract[:1600] or "New source found; full appraisal is pending.",
        why_relevant=(
            f"Matched the monitored topic '{topic.condition}' for {topic.subject_label} "
            f"({topic.relation})."
        ),
        source=SourceCitation(
            source_id=candidate.source_id,
            title=candidate.title,
            url=candidate.url,
            publisher=candidate.publisher,
            published_at=candidate.published_at,
            evidence_tier=candidate.evidence_tier,
            peer_reviewed=candidate.peer_reviewed,
            official=candidate.official,
        ),
        source_claims=candidate.source_claims,
        limitations=[
            "A new publication or trial does not by itself change an individual treatment plan.",
            "Patient-specific applicability requires professional review and the full source, not only metadata/abstract.",
        ],
        changes_care_now=False,
        requires_professional_review=True,
        relevance_score=max(0, min(relevance_score, 1)),
        interrupt_score=max(0, min(interrupt_score, 1)),
    )


class ScientificRadar:
    def __init__(
        self,
        *,
        pubmed: PubMedSource | None = None,
        europe_pmc: EuropePmcSource | None = None,
        clinical_trials: ClinicalTrialsSource | None = None,
    ) -> None:
        self.sources = [
            pubmed or PubMedSource(),
            europe_pmc or EuropePmcSource(),
            clinical_trials or ClinicalTrialsSource(),
        ]

    def scan(self, topic: WatchTopic, *, per_source: int = 4) -> list[ResearchCandidate]:
        output: list[ResearchCandidate] = []
        seen: set[str] = set()
        for source in self.sources:
            for candidate in source.search(topic, max_results=per_source):
                key = candidate.source_id or candidate.url
                if key in seen:
                    continue
                seen.add(key)
                output.append(candidate)
        output.sort(
            key=lambda item: item.published_at or datetime(1900, 1, 1, tzinfo=timezone.utc),
            reverse=True,
        )
        return output


OFFICIAL_RESOURCE_DOMAINS = {
    "gov",
    "gob",
    "gov.do",
    "gob.do",
    "nih.gov",
    "cdc.gov",
    "who.int",
    "paho.org",
    "clinicaltrials.gov",
    "medlineplus.gov",
    "usa.gov",
    "benefits.gov",
    "conadis.gob.do",
    "superate.gob.do",
}


def _host_allowed(url: str, allowed_domains: set[str]) -> bool:
    host = urlparse(url).hostname or ""
    host = host.lower().strip(".")
    for domain in allowed_domains:
        normalized = domain.lower().strip(".")
        if host == normalized or host.endswith("." + normalized):
            return True
        if normalized in {"gov", "gob"} and (host.endswith(".gov") or host.endswith(".gob")):
            return True
    return False


def _extract_json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value, count=1).strip()
        value = re.sub(r"```$", "", value, count=1).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Grounded resource search did not return JSON.")
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Grounded resource search did not return an object.")
    return parsed


class GroundedResourceRadar:
    """Optional paid discovery layer.

    Google Search grounding may discover a program candidate, but requirements
    extracted by the model are deliberately marked UNKNOWN until a separate
    source/form verification step confirms them. Discovery is not eligibility.
    """

    def __init__(
        self,
        settings,
        *,
        enabled: bool = False,
        max_calls: int = 1,
        allowed_domains: set[str] | None = None,
    ) -> None:
        self.settings = settings
        self.enabled = enabled
        self.max_calls = max(0, max_calls)
        self.calls = 0
        self.allowed_domains = allowed_domains or set(OFFICIAL_RESOURCE_DOMAINS)

    def search_programs(
        self,
        topic: WatchTopic,
        *,
        country: str,
        region: str = "",
        locality: str = "",
    ) -> list[AssistanceProgram]:
        if not self.enabled or self.calls >= self.max_calls:
            return []
        self.calls += 1

        from google.genai import types

        client = build_google_ai_client(self.settings)
        location = ", ".join(item for item in (locality, region, country) if item)
        prompt = {
            "task": "find_official_patient_support_programs",
            "condition": topic.condition,
            "subject_relation": topic.relation,
            "location": location,
            "requirements": [
                "Use current web information.",
                "Prefer government, public-health, academic, or established nonprofit sources.",
                "Do not claim eligibility; only extract candidate requirements for later source verification.",
                "Return only programs with a direct source URL.",
                "Do not infer income, disability certification, citizenship, residence, or diagnosis.",
                "Return JSON with a programs array.",
            ],
            "program_schema": {
                "title": "string",
                "provider": "string",
                "url": "string",
                "kind": "financial_assistance|government_benefit|community|family_support",
                "benefit_summary": "string",
                "country": "string",
                "region": "string",
                "locality": "string",
                "deadline": "YYYY-MM-DD or null",
                "submission_method": "portal|email|in_person|mail|unknown",
                "submission_destination": "string",
                "requirements": [
                    {"label": "string", "type": "condition|country|age_min|age_max|caregiver_of_condition|unknown", "value": "string"}
                ],
                "required_documents": [{"label": "string", "keywords": ["string"]}],
            },
        }
        response = client.models.generate_content(
            model=self.settings.model,
            contents=json.dumps(prompt, ensure_ascii=False),
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=min(int(self.settings.ai_max_output_tokens), 1800),
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        payload = _extract_json_object(str(getattr(response, "text", "") or ""))
        output: list[AssistanceProgram] = []
        for raw in payload.get("programs", [])[:10]:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            if not url or not _host_allowed(url, self.allowed_domains):
                continue
            kind_value = str(raw.get("kind") or "community")
            try:
                kind = DiscoveryKind(kind_value)
            except ValueError:
                kind = DiscoveryKind.COMMUNITY
            requirements = []
            for index, requirement in enumerate(raw.get("requirements") or []):
                if not isinstance(requirement, dict):
                    continue
                extracted_type = str(requirement.get("type") or "unknown")
                requirements.append(
                    {
                        "key": f"req_{index + 1}",
                        "label": str(requirement.get("label") or f"Requirement {index + 1}"),
                        "rule": {
                            "type": "unknown",
                            "value": requirement.get("value"),
                            "extracted_type": extracted_type,
                            "source_verification_required": True,
                        },
                        "required": True,
                    }
                )
            # Even when the model returns no explicit requirements, keep a
            # fail-closed verification blocker before eligibility/submission.
            requirements.append(
                {
                    "key": "source_verification",
                    "label": "Verify official program requirements against the source/form",
                    "rule": {
                        "type": "unknown",
                        "source_verification_required": True,
                    },
                    "required": True,
                }
            )
            required_documents = []
            for index, document in enumerate(raw.get("required_documents") or []):
                if not isinstance(document, dict):
                    continue
                required_documents.append(
                    {
                        "key": f"doc_{index + 1}",
                        "label": str(document.get("label") or f"Document {index + 1}"),
                        "keywords": [str(item) for item in (document.get("keywords") or [])[:8]],
                    }
                )
            deadline = None
            raw_deadline = str(raw.get("deadline") or "").strip()
            if raw_deadline:
                try:
                    deadline = datetime.fromisoformat(raw_deadline).date()
                except ValueError:
                    deadline = None
            submission_method = str(raw.get("submission_method") or "unknown")
            if submission_method not in {"portal", "email", "in_person", "mail", "unknown"}:
                submission_method = "unknown"
            title = str(raw.get("title") or "").strip()[:220]
            provider = str(raw.get("provider") or "").strip()[:220]
            if not title or not provider:
                continue
            output.append(
                AssistanceProgram(
                    title=title,
                    provider=provider,
                    kind=kind,
                    official_source=True,
                    url=url,
                    country=str(raw.get("country") or country)[:100],
                    region=str(raw.get("region") or region)[:100],
                    locality=str(raw.get("locality") or locality)[:100],
                    benefit_summary=str(raw.get("benefit_summary") or "")[:1200],
                    condition_terms=[topic.condition],
                    deadline=deadline,
                    requirements=requirements,
                    required_documents=required_documents,
                    submission_method=submission_method,
                    submission_destination=str(raw.get("submission_destination") or "")[:500],
                )
            )
        return output
