from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CapabilityStatus(StrEnum):
    EXISTING = "existing"
    EXECUTABLE = "executable"
    CONTRACT = "contract"
    DEFERRED = "deferred"


class CapabilityRisk(StrEnum):
    LOW = "low"
    SENSITIVE_READ = "sensitive_read"
    EXTERNAL_MUTATION = "external_mutation"
    CLINICAL_SAFETY = "clinical_safety"
    POPULATION_DATA = "population_data"


class GoogleCloudCapability(BaseModel):
    id: str
    google_product: str
    role: str
    status: CapabilityStatus
    risk: CapabilityRisk
    event_driven: bool = False
    patient_facing: bool = True
    notes: str = ""
    dependencies: list[str] = Field(default_factory=list)


CAPABILITIES: dict[str, GoogleCloudCapability] = {
    "vertex_brain": GoogleCloudCapability(
        id="vertex_brain",
        google_product="Vertex AI / Gemini",
        role="Semantic orchestration, multimodal reasoning and bounded synthesis.",
        status=CapabilityStatus.EXISTING,
        risk=CapabilityRisk.CLINICAL_SAFETY,
        dependencies=["mission_engine", "safety_boundary"],
        notes="Gemini proposes and synthesizes; deterministic policy owns safety and mutations.",
    ),
    "adk_orchestration": GoogleCloudCapability(
        id="adk_orchestration",
        google_product="Google ADK",
        role="Demand-driven specialist/tool orchestration under the HealthIA Conversation Brain.",
        status=CapabilityStatus.EXISTING,
        risk=CapabilityRisk.CLINICAL_SAFETY,
        dependencies=["vertex_brain"],
    ),
    "places_navigation": GoogleCloudCapability(
        id="places_navigation",
        google_product="Google Maps Platform · Places + Routes",
        role="Nearby care/resources, verified place details and travel-time routing.",
        status=CapabilityStatus.EXECUTABLE,
        risk=CapabilityRisk.SENSITIVE_READ,
        dependencies=["google_grants", "maps_api_key"],
        notes="Proximity never equals clinical appropriateness; candidates require selection/verification.",
    ),
    "calendar_scheduling": GoogleCloudCapability(
        id="calendar_scheduling",
        google_product="Google Calendar API",
        role="Free/busy planning and authorized appointment event lifecycle.",
        status=CapabilityStatus.EXECUTABLE,
        risk=CapabilityRisk.EXTERNAL_MUTATION,
        dependencies=["google_oauth", "google_action_authorization"],
    ),
    "gmail_communications": GoogleCloudCapability(
        id="gmail_communications",
        google_product="Gmail API + Cloud Pub/Sub",
        role="Mission-linked drafts/messages and event-driven reply wakeups without mailbox polling.",
        status=CapabilityStatus.EXECUTABLE,
        risk=CapabilityRisk.EXTERNAL_MUTATION,
        event_driven=True,
        dependencies=["google_oauth", "pubsub", "google_action_authorization"],
        notes="Live Pub/Sub ingress and OAuth deployment still require Cloud proof before production claim.",
    ),
    "people_trusted_contacts": GoogleCloudCapability(
        id="people_trusted_contacts",
        google_product="People API",
        role="Resolve authorized contact candidates for caregivers/family communication.",
        status=CapabilityStatus.EXECUTABLE,
        risk=CapabilityRisk.SENSITIVE_READ,
        dependencies=["google_oauth", "patient_confirmation_for_genogram_link"],
        notes="A contact label never proves a biological/clinical relationship.",
    ),
    "drive_documents": GoogleCloudCapability(
        id="drive_documents",
        google_product="Google Drive API",
        role="Authorized export/container and mission-linked document organization.",
        status=CapabilityStatus.EXECUTABLE,
        risk=CapabilityRisk.EXTERNAL_MUTATION,
        dependencies=["google_oauth", "google_action_authorization"],
        notes="Current executable slice creates/recovers file containers/metadata; full byte upload linkage remains a promotion gate.",
    ),
    "tasks_followup": GoogleCloudCapability(
        id="tasks_followup",
        google_product="Google Tasks API",
        role="Authorized preparation and follow-up tasks tied to HealthIA missions.",
        status=CapabilityStatus.EXECUTABLE,
        risk=CapabilityRisk.EXTERNAL_MUTATION,
        dependencies=["google_oauth", "google_action_authorization"],
    ),
    "document_ai": GoogleCloudCapability(
        id="document_ai",
        google_product="Document AI",
        role="OCR/layout, key-value, table and checkbox extraction for forms, letters, labs and administrative packets.",
        status=CapabilityStatus.CONTRACT,
        risk=CapabilityRisk.SENSITIVE_READ,
        dependencies=["cloud_storage", "provenance"],
        notes="Extraction is not eligibility; Gemini/policy interprets extracted fields against verified source rules.",
    ),
    "vision_ocr": GoogleCloudCapability(
        id="vision_ocr",
        google_product="Cloud Vision API",
        role="General image/document OCR and visual text support.",
        status=CapabilityStatus.CONTRACT,
        risk=CapabilityRisk.SENSITIVE_READ,
        dependencies=["cloud_storage"],
        notes="Not labeled as a medical-image diagnostic engine.",
    ),
    "healthcare_interop": GoogleCloudCapability(
        id="healthcare_interop",
        google_product="Cloud Healthcare API",
        role="FHIR/DICOM/HL7 interoperability gateway around the HealthIA canonical twin.",
        status=CapabilityStatus.CONTRACT,
        risk=CapabilityRisk.CLINICAL_SAFETY,
        dependencies=["clinical_mapping", "provenance"],
        notes="HealthIA does not need to become internally FHIR-shaped; the gateway maps selected canonical resources.",
    ),
    "speech_input": GoogleCloudCapability(
        id="speech_input",
        google_product="Cloud Speech-to-Text / Gemini Live",
        role="Streaming voice input into the same Conversation Brain.",
        status=CapabilityStatus.CONTRACT,
        risk=CapabilityRisk.SENSITIVE_READ,
        dependencies=["consent", "conversation_brain"],
    ),
    "speech_output": GoogleCloudCapability(
        id="speech_output",
        google_product="Cloud Text-to-Speech / Gemini Live audio",
        role="Patient-facing spoken responses and accessible education.",
        status=CapabilityStatus.CONTRACT,
        risk=CapabilityRisk.LOW,
        dependencies=["conversation_brain"],
    ),
    "translation": GoogleCloudCapability(
        id="translation",
        google_product="Cloud Translation",
        role="Multilingual presentation while preserving one canonical clinical record.",
        status=CapabilityStatus.CONTRACT,
        risk=CapabilityRisk.SENSITIVE_READ,
        dependencies=["canonical_clinical_representation"],
    ),
    "firebase_auth": GoogleCloudCapability(
        id="firebase_auth",
        google_product="Firebase Authentication / Identity Platform",
        role="Patient identity and session authentication distinct from HealthIA authorization.",
        status=CapabilityStatus.CONTRACT,
        risk=CapabilityRisk.SENSITIVE_READ,
        dependencies=["patient_isolation"],
    ),
    "fcm_notifications": GoogleCloudCapability(
        id="fcm_notifications",
        google_product="Firebase Cloud Messaging",
        role="Event-driven mission notifications after interruptibility/consent gates.",
        status=CapabilityStatus.CONTRACT,
        risk=CapabilityRisk.EXTERNAL_MUTATION,
        event_driven=True,
        dependencies=["mission_engine", "notification_policy"],
    ),
    "cloud_storage": GoogleCloudCapability(
        id="cloud_storage",
        google_product="Cloud Storage",
        role="Private original-byte evidence store for documents, images, audio and generated private media.",
        status=CapabilityStatus.EXISTING,
        risk=CapabilityRisk.SENSITIVE_READ,
        dependencies=["signed_access", "patient_isolation"],
    ),
    "firestore_state": GoogleCloudCapability(
        id="firestore_state",
        google_product="Cloud Firestore",
        role="Durable patient state, missions, outbox, grants, authorizations and receipts.",
        status=CapabilityStatus.EXISTING,
        risk=CapabilityRisk.SENSITIVE_READ,
        event_driven=True,
        dependencies=["patient_isolation"],
    ),
    "health_connect": GoogleCloudCapability(
        id="health_connect",
        google_product="Android Health Connect",
        role="Patient-authorized continuous device observations into the longitudinal twin.",
        status=CapabilityStatus.EXISTING,
        risk=CapabilityRisk.SENSITIVE_READ,
        event_driven=True,
        dependencies=["device_identity", "metric_permissions"],
    ),
    "bigquery_population": GoogleCloudCapability(
        id="bigquery_population",
        google_product="BigQuery",
        role="Aggregate/de-identified population analytics separate from patient conversational memory.",
        status=CapabilityStatus.DEFERRED,
        risk=CapabilityRisk.POPULATION_DATA,
        patient_facing=False,
        dependencies=["deidentification", "governance"],
    ),
    "forms_followup": GoogleCloudCapability(
        id="forms_followup",
        google_product="Google Forms API",
        role="Optional external questionnaires when a form is more useful than conversation.",
        status=CapabilityStatus.DEFERRED,
        risk=CapabilityRisk.EXTERNAL_MUTATION,
        dependencies=["google_oauth", "consent"],
        notes="Forms do not replace the chat-first adaptive interview.",
    ),
    "wallet_credentials": GoogleCloudCapability(
        id="wallet_credentials",
        google_product="Google Wallet API",
        role="Optional patient-held passes/credentials/reminders where clinically and legally appropriate.",
        status=CapabilityStatus.DEFERRED,
        risk=CapabilityRisk.EXTERNAL_MUTATION,
        dependencies=["consent", "credential_policy"],
    ),
    "education_video": GoogleCloudCapability(
        id="education_video",
        google_product="Vertex AI Veo + YouTube Data API",
        role="Personalized private educational media and trusted public education search.",
        status=CapabilityStatus.CONTRACT,
        risk=CapabilityRisk.CLINICAL_SAFETY,
        dependencies=["education_safety", "patient_understanding_state"],
        notes="Patient-specific clinical media is private by default; public YouTube upload is a separate explicit action.",
    ),
}


def capability_manifest() -> dict:
    counts = {status.value: 0 for status in CapabilityStatus}
    for capability in CAPABILITIES.values():
        counts[capability.status.value] += 1
    return {
        "capabilities": [item.model_dump(mode="json") for item in CAPABILITIES.values()],
        "counts": counts,
        "truth_boundary": "A capability marked contract/deferred must never be described as a live integration.",
    }
