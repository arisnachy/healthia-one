from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any, Protocol

from pydantic import BaseModel, Field

from healthia_one.auth import patient_scope
from healthia_one.bp_followup_guardian import MISSION_TYPE as BP_FOLLOWUP_MISSION_TYPE
from healthia_one.control import audit
from healthia_one.models import ChatMessage, MissionStatus, RiskLevel, SourceRef, VitalRecord


GUARDIAN_EMAIL_REPLY_CONSENT = "guardian_email_replies"
_BP_REPLY = re.compile(
    r"(?i)\b(?:bp|blood\s*pressure|presi[oó]n(?:\s*arterial)?)\s*[:=\-]?\s*(\d{2,3})\s*/\s*(\d{2,3})\b"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GuardianEmailThreadLink(BaseModel):
    patient_id: str
    mission_id: str
    thread_id: str
    provider_message_id: str
    event_id: str
    enabled: bool = True
    processed_message_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def seen(self, message_id: str) -> bool:
        return message_id == self.provider_message_id or message_id in set(self.processed_message_ids)

    def mark_processed(self, message_id: str) -> None:
        if message_id and message_id not in self.processed_message_ids:
            self.processed_message_ids.append(message_id)
            self.processed_message_ids = self.processed_message_ids[-64:]
        self.updated_at = utc_now()


class GuardianEmailThreadStore(Protocol):
    def load_by_thread(self, patient_id: str, thread_id: str) -> GuardianEmailThreadLink | None: ...
    def save(self, link: GuardianEmailThreadLink) -> None: ...


class MemoryGuardianEmailThreadStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], GuardianEmailThreadLink] = {}

    def load_by_thread(self, patient_id: str, thread_id: str) -> GuardianEmailThreadLink | None:
        value = self._values.get((patient_id, thread_id))
        return value.model_copy(deep=True) if value else None

    def save(self, link: GuardianEmailThreadLink) -> None:
        self._values[(link.patient_id, link.thread_id)] = link.model_copy(deep=True)


class FirestoreGuardianEmailThreadStore:
    COLLECTION = "healthia_guardian_email_threads"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore
        self.client = firestore.Client(project=project)

    def _ref(self, patient_id: str, thread_id: str):
        return (
            self.client.collection(self.COLLECTION)
            .document(patient_id)
            .collection("threads")
            .document(thread_id)
        )

    def load_by_thread(self, patient_id: str, thread_id: str) -> GuardianEmailThreadLink | None:
        snapshot = self._ref(patient_id, thread_id).get()
        return GuardianEmailThreadLink.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, link: GuardianEmailThreadLink) -> None:
        self._ref(link.patient_id, link.thread_id).set(link.model_dump(mode="json"))


def build_guardian_email_thread_store(settings) -> GuardianEmailThreadStore:
    if settings.store_backend == "firestore":
        import os
        return FirestoreGuardianEmailThreadStore(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
    return MemoryGuardianEmailThreadStore()


def gmail_thread_evidence_id(thread_id: str) -> str:
    return f"gmail_thread:{thread_id}"


def thread_id_from_evidence(evidence_ids: list[str]) -> str:
    for value in evidence_ids:
        text = str(value or "")
        if text.startswith("gmail_thread:") and len(text) > len("gmail_thread:"):
            return text[len("gmail_thread:"):]
    return ""


def save_guardian_email_thread_link(
    store: GuardianEmailThreadStore,
    *,
    patient_id: str,
    mission_id: str,
    thread_id: str,
    provider_message_id: str,
    event_id: str,
) -> GuardianEmailThreadLink | None:
    thread_id = str(thread_id or "").strip()
    if not thread_id:
        return None
    existing = store.load_by_thread(patient_id, thread_id)
    if existing is not None:
        if existing.patient_id != patient_id or existing.mission_id != mission_id:
            raise PermissionError("Guardian Gmail thread is already bound to another patient or mission")
        if provider_message_id and not existing.provider_message_id:
            existing.provider_message_id = provider_message_id
        existing.updated_at = utc_now()
        store.save(existing)
        return existing
    link = GuardianEmailThreadLink(
        patient_id=patient_id,
        mission_id=mission_id,
        thread_id=thread_id,
        provider_message_id=str(provider_message_id or ""),
        event_id=str(event_id or ""),
    )
    store.save(link)
    return link


def _headers(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload") or {}
    return {
        str(item.get("name") or "").strip().lower(): str(item.get("value") or "").strip()
        for item in payload.get("headers") or []
    }


def _sender(message: dict[str, Any]) -> str:
    return parseaddr(_headers(message).get("from", ""))[1].strip().lower()


def _snippet(message: dict[str, Any]) -> str:
    return str(message.get("snippet") or "").strip()[:1600]


def _parse_bp_reply(text: str) -> tuple[int, int] | None:
    match = _BP_REPLY.search(str(text or ""))
    if not match:
        return None
    systolic, diastolic = int(match.group(1)), int(match.group(2))
    # VitalRecord performs the final canonical validation. These bounds are only
    # a cheap fail-closed prefilter so dates/order numbers cannot become vitals.
    if not (40 <= systolic <= 300 and 20 <= diastolic <= 200 and systolic > diastolic):
        return None
    return systolic, diastolic


class GuardianEmailReplyOutcome(BaseModel):
    id: str
    mission_id: str
    thread_id: str
    message_id: str
    action: str
    mission_status: str
    evidence_id: str = ""
    duplicate: bool = False


class GuardianEmailReplyHandler:
    """Apply only narrow, mission-linked patient email replies.

    Wave 14 intentionally supports one externally resolvable clinical-data action:
    an explicit `BP 128/80` reply for an already-open blood-pressure follow-up
    mission. The reply becomes patient-reported evidence and then the existing
    canonical Guardian + deterministic safety layer decide whether the mission
    closes or remains human-gated.

    Ordinary mailbox mail, unlinked threads, other senders, free-form numbers and
    unsupported mission types are never turned into clinical data.
    """

    def __init__(self, *, service, thread_store: GuardianEmailThreadStore) -> None:
        self.service = service
        self.thread_store = thread_store

    async def _record_unstructured_reply(
        self,
        *,
        patient_id: str,
        mission_id: str,
        message_id: str,
        thread_id: str,
        text: str,
    ) -> None:
        with patient_scope(patient_id):
            async with self.service._mutation_lock:
                state = await self.service.store.load()
                mission = next((item for item in state.missions if item.id == mission_id), None)
                if mission is None or mission.patient_id != state.profile.id:
                    raise PermissionError("Guardian email reply mission boundary mismatch")
                state.messages.append(
                    ChatMessage(
                        patient_id=state.profile.id,
                        role="patient",
                        author=state.profile.display_name,
                        content=text[:1200] or "Email reply received.",
                        risk_level=RiskLevel.INFO,
                        mission_id=mission.id,
                        metadata={
                            "guardian_email_reply": True,
                            "gmail_thread_id": thread_id,
                            "gmail_message_id": message_id,
                            "structured_action_applied": False,
                        },
                    )
                )
                audit(
                    state,
                    actor="patient_email_reply",
                    action="capture_guardian_email_reply",
                    resource_type="health_mission",
                    resource_id=mission.id,
                    details={
                        "gmail_thread_id": thread_id,
                        "gmail_message_id": message_id,
                        "structured_action_applied": False,
                        "clinical_data_inferred": False,
                    },
                )
                await self.service.store.save(state)

    async def handle(
        self,
        patient_id: str,
        gmail_thread: dict[str, Any],
        *,
        message_id: str,
        history_id: str,
        thread_id: str,
    ) -> GuardianEmailReplyOutcome | None:
        link = self.thread_store.load_by_thread(patient_id, thread_id)
        if link is None or not link.enabled or link.seen(message_id):
            return None
        message = next(
            (item for item in (gmail_thread.get("messages") or []) if str(item.get("id") or "") == message_id),
            None,
        )
        if message is None:
            return None

        with patient_scope(patient_id):
            state = await self.service.snapshot()
        if state.profile.id != patient_id:
            raise PermissionError("Guardian email reply patient boundary mismatch")
        if GUARDIAN_EMAIL_REPLY_CONSENT not in set(state.consent.signal_types):
            return None
        patient_email = str(state.profile.email or "").strip().lower()
        if not patient_email or _sender(message) != patient_email:
            return None
        mission = next((item for item in state.missions if item.id == link.mission_id), None)
        if mission is None or mission.patient_id != patient_id:
            raise PermissionError("Guardian email thread references a missing or foreign mission")
        if mission.status == MissionStatus.CANCELLED:
            return None

        text = _snippet(message)
        if mission.mission_type == BP_FOLLOWUP_MISSION_TYPE:
            values = _parse_bp_reply(text)
            if values is not None:
                systolic, diastolic = values
                vital = VitalRecord(
                    patient_id=patient_id,
                    measured_at=utc_now(),
                    systolic=systolic,
                    diastolic=diastolic,
                    note="Patient-reported in a mission-linked HealthIA email reply.",
                    source=SourceRef(
                        source_type="patient_email_reply",
                        source_id=f"gmail:{message_id}",
                        verified=False,
                    ),
                )
                with patient_scope(patient_id):
                    await self.service.add_vital(vital)
                    persisted = await self.service.snapshot()
                saved_mission = next(item for item in persisted.missions if item.id == mission.id)
                link.mark_processed(message_id)
                self.thread_store.save(link)
                return GuardianEmailReplyOutcome(
                    id=saved_mission.id,
                    mission_id=saved_mission.id,
                    thread_id=thread_id,
                    message_id=message_id,
                    action="blood_pressure_recorded_from_email",
                    mission_status=saved_mission.status.value,
                    evidence_id=vital.id,
                )

        await self._record_unstructured_reply(
            patient_id=patient_id,
            mission_id=mission.id,
            message_id=message_id,
            thread_id=thread_id,
            text=text,
        )
        with patient_scope(patient_id):
            persisted = await self.service.snapshot()
        saved_mission = next(item for item in persisted.missions if item.id == mission.id)
        link.mark_processed(message_id)
        self.thread_store.save(link)
        return GuardianEmailReplyOutcome(
            id=saved_mission.id,
            mission_id=saved_mission.id,
            thread_id=thread_id,
            message_id=message_id,
            action="reply_captured_no_clinical_inference",
            mission_status=saved_mission.status.value,
        )
