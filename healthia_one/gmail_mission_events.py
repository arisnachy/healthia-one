from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib import parse

from pydantic import BaseModel, Field

from healthia_one.google_connector_runtime import AccessTokenProvider, JsonTransport, _bearer
from healthia_one.google_constellation import GoogleService
from healthia_one.google_mission_runtime import (
    GmailReplySignal,
    GoogleHealthMission,
    GoogleHealthMissionCoordinator,
    MissionState,
    OfferedSlot,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GmailPushNotification(BaseModel):
    email_address: str
    history_id: str
    pubsub_message_id: str = ""
    publish_time: str = ""


class GmailWatchState(BaseModel):
    patient_id: str
    email_address: str
    history_id: str
    expiration_ms: int | None = None
    enabled: bool = True
    updated_at: datetime = Field(default_factory=utc_now)


class GmailMessageChange(BaseModel):
    message_id: str
    thread_id: str
    history_id: str = ""


class GmailWatchStore(Protocol):
    def load(self, patient_id: str) -> GmailWatchState | None: ...
    def save(self, state: GmailWatchState) -> None: ...


class MissionResolver(Protocol):
    def waiting_by_thread(self, patient_id: str, thread_id: str) -> GoogleHealthMission | None: ...


class ReplyInterpreter(Protocol):
    def interpret(self, mission: GoogleHealthMission, gmail_thread: dict[str, Any], *, message_id: str, history_id: str) -> GmailReplySignal: ...


class MemoryGmailWatchStore:
    def __init__(self) -> None:
        self._values: dict[str, GmailWatchState] = {}

    def load(self, patient_id: str) -> GmailWatchState | None:
        value = self._values.get(patient_id)
        return value.model_copy(deep=True) if value else None

    def save(self, state: GmailWatchState) -> None:
        self._values[state.patient_id] = state.model_copy(deep=True)


class FirestoreGmailWatchStore:
    COLLECTION = "healthia_gmail_watch_state"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore
        self.client = firestore.Client(project=project)

    def load(self, patient_id: str) -> GmailWatchState | None:
        snapshot = self.client.collection(self.COLLECTION).document(patient_id).get()
        return GmailWatchState.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, state: GmailWatchState) -> None:
        self.client.collection(self.COLLECTION).document(state.patient_id).set(state.model_dump(mode="json"))


class FirestoreMissionResolver:
    COLLECTION = "healthia_google_missions"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore
        self.client = firestore.Client(project=project)

    def waiting_by_thread(self, patient_id: str, thread_id: str) -> GoogleHealthMission | None:
        query = (
            self.client.collection(self.COLLECTION)
            .document(patient_id)
            .collection("missions")
            .where("gmail_thread_id", "==", thread_id)
            .where("state", "==", MissionState.AWAITING_EXTERNAL_EVENT.value)
            .limit(2)
        )
        values = [GoogleHealthMission.model_validate(item.to_dict()) for item in query.stream()]
        if len(values) > 1:
            raise RuntimeError("Multiple waiting HealthIA missions are linked to the same Gmail thread")
        return values[0] if values else None


def decode_gmail_pubsub_push(envelope: dict[str, Any]) -> GmailPushNotification:
    message = envelope.get("message") or {}
    encoded = str(message.get("data") or "")
    if not encoded:
        raise ValueError("Pub/Sub push message has no data")
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode((encoded + padding).encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid Gmail Pub/Sub data payload") from exc
    email = str(payload.get("emailAddress") or "").strip().lower()
    history_id = str(payload.get("historyId") or "").strip()
    if not email or not history_id.isdigit():
        raise ValueError("Gmail Pub/Sub notification is missing emailAddress/historyId")
    return GmailPushNotification(
        email_address=email,
        history_id=history_id,
        pubsub_message_id=str(message.get("messageId") or ""),
        publish_time=str(message.get("publishTime") or ""),
    )


class GmailHistoryReader:
    def __init__(self, patient_id: str, token_provider: AccessTokenProvider, transport: JsonTransport | None = None) -> None:
        self.patient_id = patient_id
        self.token_provider = token_provider
        self.transport = transport or JsonTransport()

    @property
    def headers(self) -> dict[str, str]:
        return _bearer(self.token_provider.access_token(self.patient_id, GoogleService.GMAIL))

    def added_messages(self, start_history_id: str) -> tuple[list[GmailMessageChange], str]:
        page_token = ""
        changes: dict[str, GmailMessageChange] = {}
        latest_history_id = str(start_history_id)
        while True:
            query = {
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
                "maxResults": "100",
            }
            if page_token:
                query["pageToken"] = page_token
            url = "https://gmail.googleapis.com/gmail/v1/users/me/history?" + parse.urlencode(query)
            payload = self.transport.call("GET", url, headers=self.headers)
            latest_history_id = str(payload.get("historyId") or latest_history_id)
            for history in payload.get("history") or []:
                hid = str(history.get("id") or "")
                for added in history.get("messagesAdded") or []:
                    message = added.get("message") or {}
                    mid = str(message.get("id") or "")
                    tid = str(message.get("threadId") or "")
                    if mid and tid:
                        changes[mid] = GmailMessageChange(message_id=mid, thread_id=tid, history_id=hid)
            page_token = str(payload.get("nextPageToken") or "")
            if not page_token:
                break
        return list(changes.values()), latest_history_id

    def thread(self, thread_id: str) -> dict[str, Any]:
        encoded = parse.quote(thread_id, safe="")
        return self.transport.call(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{encoded}?format=full",
            headers=self.headers,
        )


class GmailMissionEventBridge:
    """Resume only mission-linked Gmail threads from push/history events."""

    def __init__(
        self,
        *,
        watch_store: GmailWatchStore,
        mission_resolver: MissionResolver,
        coordinator: GoogleHealthMissionCoordinator,
        history_reader_factory,
        interpreter: ReplyInterpreter,
    ) -> None:
        self.watch_store = watch_store
        self.mission_resolver = mission_resolver
        self.coordinator = coordinator
        self.history_reader_factory = history_reader_factory
        self.interpreter = interpreter

    def process(self, patient_id: str, envelope: dict[str, Any]) -> list[GoogleHealthMission]:
        notification = decode_gmail_pubsub_push(envelope)
        watch = self.watch_store.load(patient_id)
        if watch is None or not watch.enabled:
            raise PermissionError("No active Gmail watch is registered for this patient")
        if notification.email_address != watch.email_address.lower():
            raise PermissionError("Gmail push mailbox does not match the patient-authorized watch")
        if int(notification.history_id) <= int(watch.history_id):
            return []

        reader: GmailHistoryReader = self.history_reader_factory(patient_id)
        changes, latest = reader.added_messages(watch.history_id)
        resumed: list[GoogleHealthMission] = []
        seen_threads: set[str] = set()
        for change in changes:
            if change.thread_id in seen_threads:
                continue
            seen_threads.add(change.thread_id)
            mission = self.mission_resolver.waiting_by_thread(patient_id, change.thread_id)
            if mission is None:
                # A mailbox change unrelated to a HealthIA mission is ignored.
                continue
            thread = reader.thread(change.thread_id)
            signal = self.interpreter.interpret(
                mission,
                thread,
                message_id=change.message_id,
                history_id=change.history_id or notification.history_id,
            )
            resumed.append(self.coordinator.ingest_gmail_reply(mission, signal))

        # Advance only after all matching mission events are processed without error.
        watch.history_id = max(str(latest), notification.history_id, key=int)
        watch.updated_at = utc_now()
        self.watch_store.save(watch)
        return resumed


ADMIN_REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": [
                "appointment_offered",
                "appointment_confirmed",
                "missing_documents",
                "approved",
                "application_received",
                "rejected",
                "other",
            ],
        },
        "offered_slots": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "time_zone": {"type": "string"},
                },
                "required": ["start", "end", "time_zone"],
            },
        },
        "missing_documents": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 12},
        "safe_excerpt": {"type": "string", "maxLength": 400},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["classification", "offered_slots", "missing_documents", "safe_excerpt", "confidence"],
}


class GeminiAdministrativeReplyInterpreter:
    """Classify administrative reply state; never make a clinical decision."""

    def __init__(self, settings) -> None:
        self.settings = settings

    @staticmethod
    def _safe_thread_projection(thread: dict[str, Any]) -> dict[str, Any]:
        messages = []
        for raw in (thread.get("messages") or [])[-6:]:
            payload = raw.get("payload") or {}
            headers = {
                str(item.get("name") or "").lower(): str(item.get("value") or "")[:500]
                for item in payload.get("headers") or []
                if str(item.get("name") or "").lower() in {"from", "to", "subject", "date", "message-id"}
            }
            messages.append(
                {
                    "id": str(raw.get("id") or ""),
                    "threadId": str(raw.get("threadId") or ""),
                    "headers": headers,
                    "snippet": str(raw.get("snippet") or "")[:1200],
                }
            )
        return {"id": str(thread.get("id") or ""), "messages": messages}

    def interpret(self, mission: GoogleHealthMission, gmail_thread: dict[str, Any], *, message_id: str, history_id: str) -> GmailReplySignal:
        if self.settings.llm_backend != "gemini_api" or not self.settings.adk_ready:
            return GmailReplySignal(
                thread_id=mission.gmail_thread_id,
                message_id=message_id,
                history_id=history_id,
                classification="other",
                confidence=0,
                safe_excerpt="Reply received; administrative classification requires Gemini runtime.",
            )

        from google.genai import types
        from healthia_one.google_ai_transport import build_google_ai_client

        prompt = {
            "task": "classify_healthcare_administrative_reply",
            "mission": {
                "id": mission.id,
                "kind": mission.kind,
                "title": mission.title,
                "provider_email": mission.provider_email,
                "required_documents": mission.required_documents,
            },
            "thread": self._safe_thread_projection(gmail_thread),
            "rules": [
                "Use only the supplied mission-linked Gmail thread.",
                "Classify administrative workflow state only; do not infer diagnosis, treatment, eligibility, or medical advice.",
                "Appointment slots must be explicitly stated in the thread; otherwise return none.",
                "Approved means the sender explicitly approved the request. Receipt/under review is application_received, not approved.",
                "If wording is ambiguous, return other with confidence below 0.7.",
            ],
        }
        client = build_google_ai_client(self.settings)
        response = client.models.generate_content(
            model=self.settings.model,
            contents=json.dumps(prompt, ensure_ascii=False),
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=min(int(self.settings.ai_max_output_tokens), 900),
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                response_mime_type="application/json",
                response_json_schema=ADMIN_REPLY_SCHEMA,
            ),
        )
        raw = json.loads(str(response.text or "{}"))
        slots = [
            OfferedSlot(
                start=str(item["start"]),
                end=str(item["end"]),
                time_zone=str(item.get("time_zone") or ""),
                source_message_id=message_id,
            )
            for item in raw.get("offered_slots") or []
            if isinstance(item, dict) and item.get("start") and item.get("end")
        ]
        return GmailReplySignal(
            thread_id=mission.gmail_thread_id,
            message_id=message_id,
            history_id=history_id,
            classification=str(raw.get("classification") or "other"),
            offered_slots=slots,
            missing_documents=[str(item)[:160] for item in (raw.get("missing_documents") or [])],
            safe_excerpt=str(raw.get("safe_excerpt") or "")[:400],
            confidence=float(raw.get("confidence") or 0),
        )
