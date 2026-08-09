from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from healthia_one.google_ai_transport import build_google_ai_client
from healthia_one.opportunity_autopilot import AssistanceProgram, ProgramRequirement, RequiredDocument
from healthia_one.research_radar import OFFICIAL_RESOURCE_DOMAINS, _extract_json_object, _host_allowed


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProgramSourceArtifact(BaseModel):
    url: str
    final_url: str
    content_type: str
    sha256: str
    size_bytes: int
    text: str = ""
    body: bytes = Field(default=b"", exclude=True)


class VerifiedRequirement(BaseModel):
    key: str
    label: str
    rule_type: str
    value: Any = None
    required: bool = True
    evidence_excerpt: str = ""
    source_verification_required: bool = False


class ProgramSourceVerification(BaseModel):
    patient_id: str
    program_id: str
    source_url: str
    final_url: str
    source_sha256: str
    content_type: str
    requirements: list[VerifiedRequirement] = Field(default_factory=list)
    required_documents: list[RequiredDocument] = Field(default_factory=list)
    deadline: date | None = None
    submission_method: str = "unknown"
    submission_destination: str = ""
    caveats: list[str] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=utc_now)

    def apply(self, program: AssistanceProgram) -> AssistanceProgram:
        updated = program.model_copy(deep=True)
        updated.requirements = [
            ProgramRequirement(
                key=item.key,
                label=item.label,
                rule={
                    "type": item.rule_type if not item.source_verification_required else "unknown",
                    "value": item.value,
                    "evidence_excerpt": item.evidence_excerpt,
                    "source_sha256": self.source_sha256,
                    "source_verification_required": item.source_verification_required,
                },
                required=item.required,
            )
            for item in self.requirements
        ]
        updated.required_documents = [item.model_copy(deep=True) for item in self.required_documents]
        updated.deadline = self.deadline or updated.deadline
        if self.submission_method in {"portal", "email", "in_person", "mail", "unknown"}:
            updated.submission_method = self.submission_method
        if self.submission_destination:
            updated.submission_destination = self.submission_destination
        updated.source_checked_at = self.verified_at
        return updated


class ProgramVerificationStore(Protocol):
    def get(self, patient_id: str, program_id: str) -> ProgramSourceVerification | None: ...
    def save(self, verification: ProgramSourceVerification) -> None: ...


class MemoryProgramVerificationStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], ProgramSourceVerification] = {}
        self._lock = threading.RLock()

    def get(self, patient_id: str, program_id: str) -> ProgramSourceVerification | None:
        with self._lock:
            value = self._values.get((patient_id, program_id))
            return value.model_copy(deep=True) if value else None

    def save(self, verification: ProgramSourceVerification) -> None:
        with self._lock:
            self._values[(verification.patient_id, verification.program_id)] = verification.model_copy(deep=True)


class JsonProgramVerificationStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def get(self, patient_id: str, program_id: str) -> ProgramSourceVerification | None:
        with self._lock:
            raw = self._read().get(patient_id, {}).get(program_id)
            return ProgramSourceVerification.model_validate(raw) if raw else None

    def save(self, verification: ProgramSourceVerification) -> None:
        with self._lock:
            values = self._read()
            patient = values.setdefault(verification.patient_id, {})
            patient[verification.program_id] = verification.model_dump(mode="json")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)


class FirestoreProgramVerificationStore:
    COLLECTION = "healthia_program_verifications"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore
        self.client = firestore.Client(project=project)

    def _doc(self, patient_id: str, program_id: str):
        return self.client.collection(self.COLLECTION).document(patient_id).collection("programs").document(program_id)

    def get(self, patient_id: str, program_id: str) -> ProgramSourceVerification | None:
        snapshot = self._doc(patient_id, program_id).get()
        return ProgramSourceVerification.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, verification: ProgramSourceVerification) -> None:
        self._doc(verification.patient_id, verification.program_id).set(verification.model_dump(mode="json"))


def build_program_verification_store(settings) -> ProgramVerificationStore:
    if settings.store_backend == "memory":
        return MemoryProgramVerificationStore()
    if settings.store_backend == "firestore":
        import os
        return FirestoreProgramVerificationStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    data_path = Path(settings.data_path)
    return JsonProgramVerificationStore(data_path.parent / "program-verifications.json")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            value = " ".join(str(data or "").split())
            if value:
                self.parts.append(value)

    def text(self) -> str:
        return "\n".join(self.parts)


class ProgramSourceLoader:
    def __init__(self, *, max_bytes: int = 5 * 1024 * 1024, timeout_seconds: int = 15, allowed_domains: set[str] | None = None) -> None:
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds
        self.allowed_domains = allowed_domains or set(OFFICIAL_RESOURCE_DOMAINS)

    def load(self, url: str) -> ProgramSourceArtifact:
        if not _host_allowed(url, self.allowed_domains):
            raise PermissionError("Program source is outside the approved official-domain boundary")
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "HealthIA-ONE/0.8 program-source-verifier",
                "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.1",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # pragma: no cover - network
            final_url = str(response.geturl() or url)
            if not _host_allowed(final_url, self.allowed_domains):
                raise PermissionError("Program source redirected outside the approved official-domain boundary")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > self.max_bytes:
                raise ValueError("Program source exceeds the configured size limit")
            body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise ValueError("Program source exceeds the configured size limit")
            content_type = str(response.headers.get_content_type() or "application/octet-stream").lower()

        if content_type not in {"text/html", "text/plain", "application/pdf"}:
            raise ValueError(f"Unsupported program source content type: {content_type}")

        text = ""
        if content_type == "text/plain":
            text = body.decode("utf-8", errors="replace")
        elif content_type == "text/html":
            parser = _TextExtractor()
            parser.feed(body.decode("utf-8", errors="replace"))
            text = parser.text()

        return ProgramSourceArtifact(
            url=url,
            final_url=final_url,
            content_type=content_type,
            sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
            text=text[:120_000],
            body=body,
        )


PROGRAM_SOURCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "maxLength": 220},
                    "rule_type": {"type": "string", "enum": ["condition", "country", "age_min", "age_max", "caregiver_of_condition", "document_present", "unknown"]},
                    "value": {},
                    "required": {"type": "boolean"},
                    "evidence_excerpt": {"type": "string", "maxLength": 320},
                },
                "required": ["label", "rule_type", "required", "evidence_excerpt"],
            },
            "maxItems": 30,
        },
        "required_documents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "maxLength": 220},
                    "keywords": {"type": "array", "items": {"type": "string", "maxLength": 80}, "maxItems": 8},
                },
                "required": ["label", "keywords"],
            },
            "maxItems": 30,
        },
        "deadline": {"type": ["string", "null"]},
        "submission_method": {"type": "string", "enum": ["portal", "email", "in_person", "mail", "unknown"]},
        "submission_destination": {"type": "string", "maxLength": 500},
        "caveats": {"type": "array", "items": {"type": "string", "maxLength": 300}, "maxItems": 10},
    },
    "required": ["requirements", "required_documents", "submission_method", "submission_destination", "caveats"],
}


class ProgramSourceExtractor(Protocol):
    def extract(self, artifact: ProgramSourceArtifact, program: AssistanceProgram) -> dict[str, Any]: ...


class GeminiProgramSourceExtractor:
    def __init__(self, settings, *, enabled: bool = False, max_calls: int = 1) -> None:
        self.settings = settings
        self.enabled = enabled
        self.max_calls = max(0, max_calls)
        self.calls = 0

    def extract(self, artifact: ProgramSourceArtifact, program: AssistanceProgram) -> dict[str, Any]:
        if not self.enabled or self.calls >= self.max_calls:
            raise PermissionError("Program source verification AI call is not enabled")
        self.calls += 1
        from google.genai import types
        client = build_google_ai_client(self.settings)
        instruction = {
            "task": "extract_assistance_program_requirements_from_original_source",
            "program": {"title": program.title, "provider": program.provider, "url": program.url},
            "rules": [
                "Use only the supplied original page/document. Do not use outside knowledge.",
                "Every typed eligibility requirement needs a short verbatim evidence_excerpt from the source.",
                "If a requirement cannot be expressed safely using the allowed rule types, use unknown.",
                "Country values must use a full country name, never infer residence from language or locale.",
                "Do not invent income, citizenship, disability certification, diagnosis, dates, or submission destinations.",
                "List documents only when the source explicitly asks for them.",
            ],
        }
        prompt = json.dumps(instruction, ensure_ascii=False)
        contents: list[Any] = [prompt]
        if artifact.content_type == "application/pdf":
            contents.append(types.Part.from_bytes(data=artifact.body, mime_type="application/pdf"))
        else:
            contents.append(artifact.text)
        response = client.models.generate_content(
            model=self.settings.model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=min(int(self.settings.ai_max_output_tokens), 2200),
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                response_mime_type="application/json",
                response_json_schema=PROGRAM_SOURCE_SCHEMA,
            ),
        )
        return _extract_json_object(str(getattr(response, "text", "") or ""))


def _normalized_excerpt(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


class OfficialProgramVerifier:
    def __init__(self, *, loader: ProgramSourceLoader, extractor: ProgramSourceExtractor, store: ProgramVerificationStore) -> None:
        self.loader = loader
        self.extractor = extractor
        self.store = store

    def verify(self, patient_id: str, program: AssistanceProgram) -> ProgramSourceVerification:
        artifact = self.loader.load(program.url)
        payload = self.extractor.extract(artifact, program)
        requirements: list[VerifiedRequirement] = []
        source_text = _normalized_excerpt(artifact.text)

        for index, raw in enumerate(payload.get("requirements") or []):
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or "").strip()
            if not label:
                continue
            rule_type = str(raw.get("rule_type") or "unknown")
            if rule_type not in {"condition", "country", "age_min", "age_max", "caregiver_of_condition", "document_present", "unknown"}:
                rule_type = "unknown"
            excerpt = str(raw.get("evidence_excerpt") or "").strip()[:320]
            needs_more = rule_type == "unknown" or not excerpt
            if artifact.content_type in {"text/html", "text/plain"} and excerpt and _normalized_excerpt(excerpt) not in source_text:
                needs_more = True
                rule_type = "unknown"
            requirements.append(
                VerifiedRequirement(
                    key=f"verified_req_{index + 1}",
                    label=label,
                    rule_type=rule_type,
                    value=raw.get("value"),
                    required=bool(raw.get("required", True)),
                    evidence_excerpt=excerpt,
                    source_verification_required=needs_more,
                )
            )

        if not requirements:
            requirements.append(
                VerifiedRequirement(
                    key="verified_req_unknown",
                    label="Verify official program requirements manually",
                    rule_type="unknown",
                    value=None,
                    required=True,
                    evidence_excerpt="",
                    source_verification_required=True,
                )
            )

        documents = []
        for index, raw in enumerate(payload.get("required_documents") or []):
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or "").strip()
            if not label:
                continue
            documents.append(
                RequiredDocument(
                    key=f"verified_doc_{index + 1}",
                    label=label,
                    keywords=[str(item)[:80] for item in (raw.get("keywords") or [])[:8]],
                )
            )

        deadline = None
        raw_deadline = str(payload.get("deadline") or "").strip()
        if raw_deadline:
            try:
                deadline = date.fromisoformat(raw_deadline)
            except ValueError:
                deadline = None

        method = str(payload.get("submission_method") or "unknown")
        if method not in {"portal", "email", "in_person", "mail", "unknown"}:
            method = "unknown"

        destination = str(payload.get("submission_destination") or "")[:500].strip()
        caveats = [str(item)[:300] for item in (payload.get("caveats") or [])[:10]]
        if method == "portal" and destination:
            allowed_domains = set(getattr(self.loader, "allowed_domains", None) or OFFICIAL_RESOURCE_DOMAINS)
            if not _host_allowed(destination, allowed_domains):
                destination = ""
                caveats.append("Submission destination is outside the approved official-domain boundary and was discarded.")

        verification = ProgramSourceVerification(
            patient_id=patient_id,
            program_id=program.id,
            source_url=program.url,
            final_url=artifact.final_url,
            source_sha256=artifact.sha256,
            content_type=artifact.content_type,
            requirements=requirements,
            required_documents=documents,
            deadline=deadline,
            submission_method=method,
            submission_destination=destination,
            caveats=caveats[:10],
        )
        self.store.save(verification)
        return verification
