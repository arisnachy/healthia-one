from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from healthia_one.models import DocumentCategory, PatientState, new_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


def _tokens(value: str) -> set[str]:
    return {item for item in re.findall(r"[a-z0-9]+", _normalize(value)) if len(item) >= 3}


class DiscoveryKind(StrEnum):
    SCIENTIFIC = "scientific"
    THERAPEUTIC = "therapeutic"
    CLINICAL_TRIAL = "clinical_trial"
    COMMUNITY = "community"
    FINANCIAL_ASSISTANCE = "financial_assistance"
    GOVERNMENT_BENEFIT = "government_benefit"
    FAMILY_SUPPORT = "family_support"


class EvidenceTier(StrEnum):
    GUIDELINE = "guideline"
    SYSTEMATIC_REVIEW = "systematic_review"
    RANDOMIZED_TRIAL = "randomized_trial"
    OBSERVATIONAL = "observational"
    CASE_SERIES = "case_series"
    PREPRINT = "preprint"
    REGULATORY_UPDATE = "regulatory_update"
    CLINICAL_TRIAL = "clinical_trial"
    OFFICIAL_PROGRAM = "official_program"
    COMMUNITY_RESOURCE = "community_resource"
    UNKNOWN = "unknown"


class DiscoveryStatus(StrEnum):
    NEW = "new"
    SAVED = "saved"
    HIDDEN = "hidden"
    ACTIONED = "actioned"


class ApplicationStatus(StrEnum):
    DISCOVERED = "discovered"
    ELIGIBILITY_CHECKED = "eligibility_checked"
    DOCUMENTS_REQUIRED = "documents_required"
    FORM_PREFILLED = "form_prefilled"
    PATIENT_REVIEWED = "patient_reviewed"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTED = "submitted"
    AWAITING_DECISION = "awaiting_decision"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class WatchTopic(BaseModel):
    id: str = Field(default_factory=lambda: new_id("watch"))
    subject_id: str
    subject_label: str
    relation: str = "self"
    condition: str
    source: Literal["profile", "personal_history", "genogram", "conversation", "manual"] = "manual"
    search_terms: list[str] = Field(default_factory=list)
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class SourceCitation(BaseModel):
    source_id: str
    title: str
    url: str
    publisher: str = ""
    published_at: datetime | None = None
    evidence_tier: EvidenceTier = EvidenceTier.UNKNOWN
    peer_reviewed: bool = False
    official: bool = False


class Discovery(BaseModel):
    id: str = Field(default_factory=lambda: new_id("discovery"))
    fingerprint: str
    kind: DiscoveryKind
    title: str
    condition: str
    subject_id: str
    subject_label: str
    relation: str = "self"
    summary: str
    why_relevant: str
    source: SourceCitation
    potential_benefits: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_claims: list[str] = Field(default_factory=list)
    matched_medication_ids: list[str] = Field(default_factory=list)
    changes_care_now: bool = False
    requires_professional_review: bool = False
    relevance_score: float = Field(default=0, ge=0, le=1)
    interrupt_score: float = Field(default=0, ge=0, le=1)
    status: DiscoveryStatus = DiscoveryStatus.NEW
    created_at: datetime = Field(default_factory=utc_now)


class ProgramRequirement(BaseModel):
    key: str
    label: str
    rule: dict[str, Any] = Field(default_factory=dict)
    required: bool = True


class RequiredDocument(BaseModel):
    key: str
    label: str
    accepted_categories: list[DocumentCategory] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class AssistanceProgram(BaseModel):
    id: str = Field(default_factory=lambda: new_id("program"))
    title: str
    provider: str
    kind: DiscoveryKind = DiscoveryKind.FINANCIAL_ASSISTANCE
    official_source: bool = True
    url: str
    country: str = ""
    region: str = ""
    locality: str = ""
    benefit_summary: str = ""
    condition_terms: list[str] = Field(default_factory=list)
    deadline: date | None = None
    requirements: list[ProgramRequirement] = Field(default_factory=list)
    required_documents: list[RequiredDocument] = Field(default_factory=list)
    submission_method: Literal["portal", "email", "in_person", "mail", "unknown"] = "unknown"
    submission_destination: str = ""
    source_checked_at: datetime = Field(default_factory=utc_now)


class EligibilityDecision(BaseModel):
    program_id: str
    likely_eligible: bool | None = None
    matched: list[str] = Field(default_factory=list)
    unmet: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    score: float = Field(default=0, ge=0, le=1)
    checked_at: datetime = Field(default_factory=utc_now)


class ApplicationField(BaseModel):
    key: str
    label: str
    value: str = ""
    source: str = ""
    confidence: float = Field(default=0, ge=0, le=1)
    requires_confirmation: bool = True


class ApplicationPacket(BaseModel):
    id: str = Field(default_factory=lambda: new_id("application"))
    program_id: str
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
    fields: list[ApplicationField] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    attachment_document_ids: list[str] = Field(default_factory=list)
    submission_method: str = "unknown"
    submission_destination: str = ""
    patient_confirmed: bool = False
    external_submission_authorized: bool = False
    receipt: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OpportunityVault(BaseModel):
    patient_id: str
    watch_topics: list[WatchTopic] = Field(default_factory=list)
    discoveries: list[Discovery] = Field(default_factory=list)
    programs: list[AssistanceProgram] = Field(default_factory=list)
    applications: list[ApplicationPacket] = Field(default_factory=list)
    seen_fingerprints: list[str] = Field(default_factory=list)
    processed_event_keys: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


def discovery_fingerprint(*, source_id: str, title: str, condition: str, subject_id: str) -> str:
    raw = "|".join(_normalize(item) for item in (source_id, title, condition, subject_id))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def derive_watch_topics(state: PatientState) -> list[WatchTopic]:
    seen: set[tuple[str, str]] = set()
    topics: list[WatchTopic] = []

    def add(subject_id: str, subject_label: str, relation: str, condition: str, source: str) -> None:
        condition = str(condition or "").strip()
        if len(condition) < 2:
            return
        key = (subject_id, _normalize(condition))
        if key in seen:
            return
        seen.add(key)
        topics.append(
            WatchTopic(
                subject_id=subject_id,
                subject_label=subject_label,
                relation=relation,
                condition=condition,
                source=source,
                search_terms=[condition],
            )
        )

    for condition in state.profile.confirmed_conditions:
        add(state.profile.id, state.profile.display_name, "self", condition, "profile")
    for condition in state.profile.personal_history.chronic_conditions:
        add(state.profile.id, state.profile.display_name, "self", condition, "personal_history")
    for member in state.family_members:
        for condition in member.conditions:
            if condition.confirmed:
                add(member.id, member.display_name, member.relation, condition.name, "genogram")
    return topics


def sync_watch_topics(vault: OpportunityVault, state: PatientState) -> OpportunityVault:
    current = {(item.subject_id, _normalize(item.condition)): item for item in vault.watch_topics}
    for candidate in derive_watch_topics(state):
        key = (candidate.subject_id, _normalize(candidate.condition))
        if key not in current:
            vault.watch_topics.append(candidate)
    vault.updated_at = utc_now()
    return vault


def add_discovery(vault: OpportunityVault, discovery: Discovery) -> bool:
    if discovery.fingerprint in vault.seen_fingerprints:
        return False
    vault.discoveries.append(discovery)
    vault.seen_fingerprints.append(discovery.fingerprint)
    vault.updated_at = utc_now()
    return True


def _medication_text(state: PatientState, medication_id: str) -> str:
    plan = next((item for item in state.medication_plans if item.id == medication_id), None)
    if not plan:
        return ""
    return " ".join(
        item
        for item in (plan.name, plan.generic_name, plan.strength, plan.schedule, plan.purpose)
        if item
    )


def match_current_medications(state: PatientState, condition: str, source_claims: list[str]) -> list[str]:
    condition_tokens = _tokens(condition)
    claim_tokens = _tokens(" ".join(source_claims))
    matched: list[str] = []
    for plan in state.medication_plans:
        if not plan.active:
            continue
        med_tokens = _tokens(_medication_text(state, plan.id))
        purpose_tokens = _tokens(plan.purpose)
        if condition_tokens & purpose_tokens or med_tokens & claim_tokens:
            matched.append(plan.id)
    return matched


def therapeutic_comparison(state: PatientState, discovery: Discovery) -> dict[str, Any]:
    current = []
    for plan in state.medication_plans:
        if not plan.active:
            continue
        current.append(
            {
                "id": plan.id,
                "name": plan.name,
                "strength": plan.strength,
                "schedule": plan.schedule,
                "purpose": plan.purpose,
                "verification_status": plan.verification_status,
            }
        )
    matched_ids = discovery.matched_medication_ids or match_current_medications(
        state, discovery.condition, discovery.source_claims
    )
    return {
        "condition": discovery.condition,
        "current_medications": current,
        "matched_medication_ids": matched_ids,
        "new_evidence": {
            "title": discovery.title,
            "source": discovery.source.model_dump(mode="json"),
            "potential_benefits_from_source": discovery.potential_benefits,
            "limitations": discovery.limitations,
        },
        "patient_specific_claim": False,
        "requires_professional_review": True,
        "safety": (
            "This comparison organizes cited evidence against the recorded medication list. "
            "It does not establish that the new therapy is appropriate, safer, or superior for this patient "
            "and never authorizes starting, stopping, substituting, or changing a dose."
        ),
    }


def _explicit_address_country_match(state: PatientState, expected: Any) -> bool | None:
    """Use only an explicit country name in the patient-entered address.

    Locale/language is never treated as residence. Short country codes such as
    "DO" are intentionally UNKNOWN because they can collide with ordinary text.
    """
    expected_text = _normalize(str(expected or ""))
    address = _normalize(state.profile.address)
    if not address or len(expected_text) < 4:
        return None
    return expected_text in address


def _condition_set(state: PatientState) -> set[str]:
    values = {
        _normalize(item) for item in state.profile.confirmed_conditions + state.profile.personal_history.chronic_conditions
    }
    for member in state.family_members:
        values.update(_normalize(item.name) for item in member.conditions if item.confirmed)
    return {item for item in values if item}


def _family_condition_map(state: PatientState) -> dict[str, set[str]]:
    output: dict[str, set[str]] = {}
    for member in state.family_members:
        output[member.id] = {_normalize(item.name) for item in member.conditions if item.confirmed}
    return output


def _document_matches(state: PatientState, required: RequiredDocument) -> str | None:
    keywords = {_normalize(item) for item in required.keywords + [required.label]}
    for document in reversed(state.documents):
        if required.accepted_categories and document.category not in required.accepted_categories:
            continue
        haystack = _normalize(" ".join([document.title, document.filename, *document.tags]))
        if not keywords or any(keyword and keyword in haystack for keyword in keywords):
            return document.id
    return None


def evaluate_program_eligibility(state: PatientState, program: AssistanceProgram) -> EligibilityDecision:
    matched: list[str] = []
    unmet: list[str] = []
    unknown: list[str] = []
    conditions = _condition_set(state)
    family_conditions = _family_condition_map(state)
    age = max((date.today() - state.profile.birth_date).days // 365, 0)

    for requirement in program.requirements:
        rule = requirement.rule or {}
        kind = str(rule.get("type") or "").strip()
        expected = rule.get("value")
        result: bool | None = None

        if kind == "condition":
            result = _normalize(str(expected)) in conditions
        elif kind == "country":
            result = _explicit_address_country_match(state, expected)
        elif kind == "age_min":
            result = age >= int(expected)
        elif kind == "age_max":
            result = age <= int(expected)
        elif kind == "caregiver_of_condition":
            target = _normalize(str(expected))
            result = any(target in values for values in family_conditions.values())
        elif kind == "document_present":
            document_rule = RequiredDocument(
                key=requirement.key,
                label=requirement.label,
                accepted_categories=[DocumentCategory(item) for item in rule.get("categories", [])],
                keywords=[str(item) for item in rule.get("keywords", [])],
            )
            result = _document_matches(state, document_rule) is not None
        else:
            result = None

        label = requirement.label
        if result is True:
            matched.append(label)
        elif result is False and requirement.required:
            unmet.append(label)
        else:
            unknown.append(label)

    missing_documents = [
        item.label for item in program.required_documents if _document_matches(state, item) is None
    ]
    known_count = len(matched) + len(unmet)
    score = len(matched) / known_count if known_count else 0
    likely: bool | None
    if unmet:
        likely = False
    elif unknown:
        likely = None
    else:
        likely = True
    return EligibilityDecision(
        program_id=program.id,
        likely_eligible=likely,
        matched=matched,
        unmet=unmet,
        unknown=unknown,
        missing_documents=missing_documents,
        score=round(score, 3),
    )


def _profile_fields(state: PatientState) -> list[ApplicationField]:
    values = [
        ("legal_name", "Legal name", state.profile.legal_name, "patient_profile"),
        ("email", "Email", state.profile.email, "patient_profile"),
        ("phone", "Phone", state.profile.phone, "patient_profile"),
        ("address", "Address", state.profile.address, "patient_profile"),
        ("birth_date", "Date of birth", state.profile.birth_date.isoformat(), "patient_profile"),
    ]
    return [
        ApplicationField(
            key=key,
            label=label,
            value=str(value or ""),
            source=source,
            confidence=1 if value else 0,
            requires_confirmation=True,
        )
        for key, label, value, source in values
    ]


def prepare_application(
    state: PatientState,
    program: AssistanceProgram,
    decision: EligibilityDecision,
) -> ApplicationPacket:
    fields = _profile_fields(state)
    missing_fields = [item.label for item in fields if not item.value]
    attachments: list[str] = []
    missing_documents: list[str] = []
    for required in program.required_documents:
        matched = _document_matches(state, required)
        if matched:
            attachments.append(matched)
        else:
            missing_documents.append(required.label)

    if decision.likely_eligible is False:
        status = ApplicationStatus.BLOCKED
    elif missing_fields or missing_documents or decision.unknown:
        status = ApplicationStatus.DOCUMENTS_REQUIRED
    else:
        status = ApplicationStatus.FORM_PREFILLED

    return ApplicationPacket(
        program_id=program.id,
        status=status,
        fields=fields,
        missing_fields=missing_fields + list(decision.unknown),
        missing_documents=missing_documents,
        attachment_document_ids=attachments,
        submission_method=program.submission_method,
        submission_destination=program.submission_destination,
    )


def mark_patient_reviewed(packet: ApplicationPacket, *, confirmed: bool) -> ApplicationPacket:
    packet.patient_confirmed = confirmed
    packet.updated_at = utc_now()
    if confirmed and not packet.missing_fields and not packet.missing_documents:
        packet.status = ApplicationStatus.PATIENT_REVIEWED
    return packet


def authorize_external_submission(packet: ApplicationPacket, *, authorized: bool) -> ApplicationPacket:
    if not authorized:
        packet.external_submission_authorized = False
        packet.updated_at = utc_now()
        return packet
    if not packet.patient_confirmed:
        raise ValueError("Patient review is required before external submission.")
    if packet.missing_fields or packet.missing_documents:
        raise ValueError("Application still has missing fields or documents.")
    packet.external_submission_authorized = True
    packet.status = ApplicationStatus.READY_TO_SUBMIT
    packet.updated_at = utc_now()
    return packet


def record_submission_receipt(packet: ApplicationPacket, receipt: str) -> ApplicationPacket:
    if not packet.external_submission_authorized:
        raise ValueError("External submission is not authorized.")
    value = str(receipt or "").strip()
    if not value:
        raise ValueError("A durable submission receipt is required.")
    packet.receipt = value
    packet.status = ApplicationStatus.SUBMITTED
    packet.updated_at = utc_now()
    return packet


def register_program(vault: OpportunityVault, program: AssistanceProgram) -> bool:
    if any(item.url == program.url or item.id == program.id for item in vault.programs):
        return False
    vault.programs.append(program)
    vault.updated_at = utc_now()
    return True


def upsert_application(vault: OpportunityVault, packet: ApplicationPacket) -> None:
    for index, item in enumerate(vault.applications):
        if item.id == packet.id or item.program_id == packet.program_id:
            vault.applications[index] = packet
            vault.updated_at = utc_now()
            return
    vault.applications.append(packet)
    vault.updated_at = utc_now()


def opportunity_snapshot(vault: OpportunityVault) -> dict[str, Any]:
    actionable = [
        item for item in vault.applications
        if item.status not in {ApplicationStatus.COMPLETED, ApplicationStatus.BLOCKED}
    ]
    return {
        "watch_topics": len([item for item in vault.watch_topics if item.enabled]),
        "new_discoveries": len([item for item in vault.discoveries if item.status == DiscoveryStatus.NEW]),
        "programs": len(vault.programs),
        "active_applications": len(actionable),
        "missing_documents": sorted(
            {document for packet in actionable for document in packet.missing_documents}
        ),
        "latest_discoveries": [
            item.model_dump(mode="json") for item in vault.discoveries[-5:]
        ],
    }
