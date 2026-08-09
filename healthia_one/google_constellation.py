from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class GoogleService(StrEnum):
    MAPS = "maps"
    CALENDAR = "calendar"
    GMAIL = "gmail"
    PEOPLE = "people"
    DRIVE = "drive"
    TASKS = "tasks"
    YOUTUBE = "youtube"
    DOCUMENT_AI = "document_ai"
    HEALTHCARE = "healthcare"
    FCM = "fcm"
    SPEECH = "speech"
    TEXT_TO_SPEECH = "text_to_speech"
    VEO = "veo"
    GEMINI_LIVE = "gemini_live"


class GoogleAction(StrEnum):
    MAPS_SEARCH_NEARBY = "maps.search_nearby"
    MAPS_TEXT_SEARCH = "maps.text_search"
    MAPS_PLACE_DETAILS = "maps.place_details"
    MAPS_ROUTE = "maps.route"

    CALENDAR_FREEBUSY = "calendar.freebusy"
    CALENDAR_CREATE_EVENT = "calendar.create_event"
    CALENDAR_UPDATE_EVENT = "calendar.update_event"
    CALENDAR_CANCEL_EVENT = "calendar.cancel_event"

    GMAIL_READ_THREAD = "gmail.read_thread"
    GMAIL_DRAFT = "gmail.draft"
    GMAIL_SEND = "gmail.send"
    GMAIL_REPLY = "gmail.reply"
    GMAIL_WATCH = "gmail.watch"

    PEOPLE_READ_CONTACTS = "people.read_contacts"
    PEOPLE_RESOLVE_CONTACT = "people.resolve_contact"

    DRIVE_EXPORT_FILE = "drive.export_file"
    DRIVE_UPDATE_EXPORT = "drive.update_export"

    TASKS_CREATE = "tasks.create"
    TASKS_UPDATE = "tasks.update"
    TASKS_COMPLETE = "tasks.complete"

    YOUTUBE_SEARCH = "youtube.search"
    YOUTUBE_UPLOAD = "youtube.upload"

    DOCUMENT_AI_PROCESS = "document_ai.process"

    HEALTHCARE_FHIR_READ = "healthcare.fhir_read"
    HEALTHCARE_FHIR_SEARCH = "healthcare.fhir_search"
    HEALTHCARE_FHIR_WRITE = "healthcare.fhir_write"
    HEALTHCARE_DICOM_METADATA = "healthcare.dicom_metadata"

    FCM_SEND_MISSION_NOTIFICATION = "fcm.send_mission_notification"

    SPEECH_RECOGNIZE = "speech.recognize"
    TEXT_TO_SPEECH_SYNTHESIZE = "text_to_speech.synthesize"

    VEO_GENERATE = "veo.generate"
    GEMINI_LIVE_SESSION = "gemini_live.session"


class GrantBundle(StrEnum):
    MAPS_LOCATION = "maps_location"
    CALENDAR_READ = "calendar_read"
    CALENDAR_WRITE = "calendar_write"
    GMAIL_READ_RELEVANT = "gmail_read_relevant"
    GMAIL_SEND = "gmail_send"
    CONTACTS_READ = "contacts_read"
    DRIVE_EXPORT = "drive_export"
    TASKS_WRITE = "tasks_write"
    YOUTUBE_SEARCH = "youtube_search"
    YOUTUBE_UPLOAD = "youtube_upload"
    DOCUMENT_AI_PROCESS = "document_ai_process"
    HEALTHCARE_READ = "healthcare_read"
    HEALTHCARE_WRITE = "healthcare_write"
    FCM_NOTIFY = "fcm_notify"
    SPEECH_TRANSCRIBE = "speech_transcribe"
    TEXT_TO_SPEECH = "text_to_speech"
    VEO_GENERATE = "veo_generate"
    GEMINI_LIVE = "gemini_live"


class GoogleActionPolicy(BaseModel):
    service: GoogleService
    required_grants: set[GrantBundle] = Field(default_factory=set)
    mutates_external_state: bool = False
    explicit_authorization_required: bool = False
    sensitive_disclosure_possible: bool = False


ACTION_POLICIES: dict[GoogleAction, GoogleActionPolicy] = {
    GoogleAction.MAPS_SEARCH_NEARBY: GoogleActionPolicy(service=GoogleService.MAPS, required_grants={GrantBundle.MAPS_LOCATION}),
    GoogleAction.MAPS_TEXT_SEARCH: GoogleActionPolicy(service=GoogleService.MAPS, required_grants={GrantBundle.MAPS_LOCATION}),
    GoogleAction.MAPS_PLACE_DETAILS: GoogleActionPolicy(service=GoogleService.MAPS, required_grants={GrantBundle.MAPS_LOCATION}),
    GoogleAction.MAPS_ROUTE: GoogleActionPolicy(service=GoogleService.MAPS, required_grants={GrantBundle.MAPS_LOCATION}),
    GoogleAction.CALENDAR_FREEBUSY: GoogleActionPolicy(service=GoogleService.CALENDAR, required_grants={GrantBundle.CALENDAR_READ}),
    GoogleAction.CALENDAR_CREATE_EVENT: GoogleActionPolicy(service=GoogleService.CALENDAR, required_grants={GrantBundle.CALENDAR_WRITE}, mutates_external_state=True, explicit_authorization_required=True),
    GoogleAction.CALENDAR_UPDATE_EVENT: GoogleActionPolicy(service=GoogleService.CALENDAR, required_grants={GrantBundle.CALENDAR_WRITE}, mutates_external_state=True, explicit_authorization_required=True),
    GoogleAction.CALENDAR_CANCEL_EVENT: GoogleActionPolicy(service=GoogleService.CALENDAR, required_grants={GrantBundle.CALENDAR_WRITE}, mutates_external_state=True, explicit_authorization_required=True),
    GoogleAction.GMAIL_READ_THREAD: GoogleActionPolicy(service=GoogleService.GMAIL, required_grants={GrantBundle.GMAIL_READ_RELEVANT}, sensitive_disclosure_possible=True),
    GoogleAction.GMAIL_DRAFT: GoogleActionPolicy(service=GoogleService.GMAIL, required_grants={GrantBundle.GMAIL_SEND}, sensitive_disclosure_possible=True),
    GoogleAction.GMAIL_SEND: GoogleActionPolicy(service=GoogleService.GMAIL, required_grants={GrantBundle.GMAIL_SEND}, mutates_external_state=True, explicit_authorization_required=True, sensitive_disclosure_possible=True),
    GoogleAction.GMAIL_REPLY: GoogleActionPolicy(service=GoogleService.GMAIL, required_grants={GrantBundle.GMAIL_SEND}, mutates_external_state=True, explicit_authorization_required=True, sensitive_disclosure_possible=True),
    GoogleAction.GMAIL_WATCH: GoogleActionPolicy(service=GoogleService.GMAIL, required_grants={GrantBundle.GMAIL_READ_RELEVANT}, mutates_external_state=True),
    GoogleAction.PEOPLE_READ_CONTACTS: GoogleActionPolicy(service=GoogleService.PEOPLE, required_grants={GrantBundle.CONTACTS_READ}, sensitive_disclosure_possible=True),
    GoogleAction.PEOPLE_RESOLVE_CONTACT: GoogleActionPolicy(service=GoogleService.PEOPLE, required_grants={GrantBundle.CONTACTS_READ}, sensitive_disclosure_possible=True),
    GoogleAction.DRIVE_EXPORT_FILE: GoogleActionPolicy(service=GoogleService.DRIVE, required_grants={GrantBundle.DRIVE_EXPORT}, mutates_external_state=True, explicit_authorization_required=True, sensitive_disclosure_possible=True),
    GoogleAction.DRIVE_UPDATE_EXPORT: GoogleActionPolicy(service=GoogleService.DRIVE, required_grants={GrantBundle.DRIVE_EXPORT}, mutates_external_state=True, explicit_authorization_required=True, sensitive_disclosure_possible=True),
    GoogleAction.TASKS_CREATE: GoogleActionPolicy(service=GoogleService.TASKS, required_grants={GrantBundle.TASKS_WRITE}, mutates_external_state=True, explicit_authorization_required=True),
    GoogleAction.TASKS_UPDATE: GoogleActionPolicy(service=GoogleService.TASKS, required_grants={GrantBundle.TASKS_WRITE}, mutates_external_state=True, explicit_authorization_required=True),
    GoogleAction.TASKS_COMPLETE: GoogleActionPolicy(service=GoogleService.TASKS, required_grants={GrantBundle.TASKS_WRITE}, mutates_external_state=True, explicit_authorization_required=True),
    GoogleAction.YOUTUBE_SEARCH: GoogleActionPolicy(service=GoogleService.YOUTUBE, required_grants={GrantBundle.YOUTUBE_SEARCH}),
    GoogleAction.YOUTUBE_UPLOAD: GoogleActionPolicy(service=GoogleService.YOUTUBE, required_grants={GrantBundle.YOUTUBE_UPLOAD}, mutates_external_state=True, explicit_authorization_required=True, sensitive_disclosure_possible=True),
    GoogleAction.DOCUMENT_AI_PROCESS: GoogleActionPolicy(
        service=GoogleService.DOCUMENT_AI,
        required_grants={GrantBundle.DOCUMENT_AI_PROCESS},
        sensitive_disclosure_possible=True,
    ),
    GoogleAction.HEALTHCARE_FHIR_READ: GoogleActionPolicy(
        service=GoogleService.HEALTHCARE,
        required_grants={GrantBundle.HEALTHCARE_READ},
        sensitive_disclosure_possible=True,
    ),
    GoogleAction.HEALTHCARE_FHIR_SEARCH: GoogleActionPolicy(
        service=GoogleService.HEALTHCARE,
        required_grants={GrantBundle.HEALTHCARE_READ},
        sensitive_disclosure_possible=True,
    ),
    GoogleAction.HEALTHCARE_FHIR_WRITE: GoogleActionPolicy(
        service=GoogleService.HEALTHCARE,
        required_grants={GrantBundle.HEALTHCARE_WRITE},
        mutates_external_state=True,
        explicit_authorization_required=True,
        sensitive_disclosure_possible=True,
    ),
    GoogleAction.HEALTHCARE_DICOM_METADATA: GoogleActionPolicy(
        service=GoogleService.HEALTHCARE,
        required_grants={GrantBundle.HEALTHCARE_READ},
        sensitive_disclosure_possible=True,
    ),
    GoogleAction.FCM_SEND_MISSION_NOTIFICATION: GoogleActionPolicy(
        service=GoogleService.FCM,
        required_grants={GrantBundle.FCM_NOTIFY},
        mutates_external_state=True,
        explicit_authorization_required=True,
        sensitive_disclosure_possible=False,
    ),
    GoogleAction.SPEECH_RECOGNIZE: GoogleActionPolicy(
        service=GoogleService.SPEECH,
        required_grants={GrantBundle.SPEECH_TRANSCRIBE},
        sensitive_disclosure_possible=True,
    ),
    GoogleAction.TEXT_TO_SPEECH_SYNTHESIZE: GoogleActionPolicy(
        service=GoogleService.TEXT_TO_SPEECH,
        required_grants={GrantBundle.TEXT_TO_SPEECH},
        sensitive_disclosure_possible=True,
    ),
    GoogleAction.VEO_GENERATE: GoogleActionPolicy(
        service=GoogleService.VEO,
        required_grants={GrantBundle.VEO_GENERATE},
        mutates_external_state=True,
        explicit_authorization_required=True,
        sensitive_disclosure_possible=True,
    ),
    GoogleAction.GEMINI_LIVE_SESSION: GoogleActionPolicy(service=GoogleService.GEMINI_LIVE, required_grants={GrantBundle.GEMINI_LIVE}, sensitive_disclosure_possible=True),
}


class GoogleGrant(BaseModel):
    id: str = Field(default_factory=lambda: new_id("grant"))
    patient_id: str
    bundle: GrantBundle
    scopes: list[str] = Field(default_factory=list)
    enabled: bool = True
    granted_at: datetime = Field(default_factory=utc_now)
    revoked_at: datetime | None = None


class GoogleActionRequest(BaseModel):
    id: str = Field(default_factory=lambda: new_id("greq"))
    patient_id: str
    mission_id: str
    action: GoogleAction
    payload: dict[str, Any] = Field(default_factory=dict)
    explicit_authorization_id: str = ""
    standing_authorization_id: str = ""

    @property
    def service(self) -> GoogleService:
        return ACTION_POLICIES[self.action].service


class GoogleAuthorizationDecision(BaseModel):
    allowed: bool
    reason: str
    missing_grants: list[GrantBundle] = Field(default_factory=list)
    explicit_authorization_required: bool = False


class GoogleActionReceipt(BaseModel):
    id: str = Field(default_factory=lambda: new_id("receipt"))
    patient_id: str
    mission_id: str
    provider: str = "google"
    service: GoogleService
    action: GoogleAction
    resource_id: str = ""
    status: str
    authorization_id: str = ""
    idempotency_key: str
    occurred_at: datetime = Field(default_factory=utc_now)
    safe_summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


def active_grant_bundles(grants: list[GoogleGrant], patient_id: str) -> set[GrantBundle]:
    return {grant.bundle for grant in grants if grant.patient_id == patient_id and grant.enabled and grant.revoked_at is None}


def authorize_google_action(request: GoogleActionRequest, grants: list[GoogleGrant]) -> GoogleAuthorizationDecision:
    policy = ACTION_POLICIES[request.action]
    active = active_grant_bundles(grants, request.patient_id)
    missing = sorted(policy.required_grants - active, key=str)
    if missing:
        return GoogleAuthorizationDecision(
            allowed=False,
            reason="Required Google permission bundle is not granted for this patient.",
            missing_grants=missing,
            explicit_authorization_required=policy.explicit_authorization_required,
        )
    has_action_authorization = bool(request.explicit_authorization_id.strip() or request.standing_authorization_id.strip())
    if policy.explicit_authorization_required and not has_action_authorization:
        return GoogleAuthorizationDecision(
            allowed=False,
            reason="External mutation requires patient authorization before execution.",
            explicit_authorization_required=True,
        )
    return GoogleAuthorizationDecision(
        allowed=True,
        reason="Action satisfies the Google grant and authorization boundary.",
        explicit_authorization_required=policy.explicit_authorization_required,
    )


def build_idempotency_key(request: GoogleActionRequest) -> str:
    payload = json.dumps(request.payload, sort_keys=True, ensure_ascii=False, default=str)
    raw = "|".join((request.patient_id, request.mission_id, str(request.action), payload, request.explicit_authorization_id, request.standing_authorization_id))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_google_receipt(
    request: GoogleActionRequest,
    *,
    status: str,
    resource_id: str = "",
    safe_summary: str = "",
    evidence_ids: list[str] | None = None,
) -> GoogleActionReceipt:
    authorization_id = request.explicit_authorization_id or request.standing_authorization_id
    return GoogleActionReceipt(
        patient_id=request.patient_id,
        mission_id=request.mission_id,
        service=request.service,
        action=request.action,
        resource_id=resource_id,
        status=status,
        authorization_id=authorization_id,
        idempotency_key=build_idempotency_key(request),
        safe_summary=safe_summary,
        evidence_ids=list(evidence_ids or []),
    )
