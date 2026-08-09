from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from healthia_one.google_constellation import GoogleAction, GoogleActionRequest, GoogleGrant
from healthia_one.google_connector_runtime import ConnectorResult, GoogleActionExecutor


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def mission_id() -> str:
    return f"gmission_{uuid4().hex[:16]}"


class MissionKind(StrEnum):
    CARE_NAVIGATION = "care_navigation"
    ASSISTANCE_ENROLLMENT = "assistance_enrollment"
    CONSULTATION_PREP = "consultation_prep"
    FOLLOWUP_RECOVERY = "followup_recovery"


class MissionState(StrEnum):
    RECEIVED = "received"
    DISCOVERING = "discovering"
    AWAITING_SELECTION = "awaiting_selection"
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    CONTACTING = "contacting"
    AWAITING_EXTERNAL_EVENT = "awaiting_external_event"
    SLOT_OFFERED = "slot_offered"
    SCHEDULING = "scheduling"
    FOLLOWUP_CREATED = "followup_created"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class PublicMissionEvent(BaseModel):
    at: datetime = Field(default_factory=utc_now)
    event_type: str
    summary: str
    resource_id: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class OfferedSlot(BaseModel):
    start: str
    end: str
    time_zone: str = ""
    source_message_id: str = ""


class GmailReplySignal(BaseModel):
    thread_id: str
    message_id: str
    history_id: str = ""
    classification: str
    offered_slots: list[OfferedSlot] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    safe_excerpt: str = ""
    confidence: float = Field(default=0.0, ge=0, le=1)


class GoogleHealthMission(BaseModel):
    id: str = Field(default_factory=mission_id)
    patient_id: str
    kind: MissionKind
    title: str
    state: MissionState = MissionState.RECEIVED
    condition_or_need: str = ""
    location: dict[str, Any] = Field(default_factory=dict)
    provider_query: str = ""
    selected_place: dict[str, Any] = Field(default_factory=dict)
    provider_email: str = ""
    gmail_thread_id: str = ""
    offered_slots: list[OfferedSlot] = Field(default_factory=list)
    selected_slot: OfferedSlot | None = None
    calendar_event_id: str = ""
    task_ids: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    action_authorizations: dict[str, str] = Field(default_factory=dict)
    public_events: list[PublicMissionEvent] = Field(default_factory=list)
    tool_outputs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def record(self, event_type: str, summary: str, resource_id: str = "", evidence_ids: list[str] | None = None) -> None:
        self.public_events.append(
            PublicMissionEvent(
                event_type=event_type,
                summary=summary,
                resource_id=resource_id,
                evidence_ids=list(evidence_ids or []),
            )
        )
        self.updated_at = utc_now()


class MissionStore(Protocol):
    def load(self, patient_id: str, mission_id: str) -> GoogleHealthMission | None:
        ...

    def save(self, mission: GoogleHealthMission) -> None:
        ...


class MemoryMissionStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], GoogleHealthMission] = {}

    def load(self, patient_id: str, mission_id: str) -> GoogleHealthMission | None:
        value = self._values.get((patient_id, mission_id))
        return value.model_copy(deep=True) if value else None

    def save(self, mission: GoogleHealthMission) -> None:
        self._values[(mission.patient_id, mission.id)] = mission.model_copy(deep=True)


class FirestoreMissionStore:
    COLLECTION = "healthia_google_missions"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.client = firestore.Client(project=project)

    def _doc(self, patient_id: str, mission_id: str):
        return self.client.collection(self.COLLECTION).document(patient_id).collection("missions").document(mission_id)

    def load(self, patient_id: str, mission_id: str) -> GoogleHealthMission | None:
        snapshot = self._doc(patient_id, mission_id).get()
        return GoogleHealthMission.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, mission: GoogleHealthMission) -> None:
        self._doc(mission.patient_id, mission.id).set(mission.model_dump(mode="json"))


class MissionTransitionError(ValueError):
    pass


class GoogleHealthMissionCoordinator:
    """Event-resumable mission coordinator.

    Gemini/ADK may decide *what* mission the patient wants and interpret an
    external reply, but this coordinator owns the state transitions and tool
    execution boundaries. It contains no private chain-of-thought.
    """

    def __init__(self, executor: GoogleActionExecutor, store: MissionStore | None = None) -> None:
        self.executor = executor
        self.store = store or MemoryMissionStore()

    def create_navigation_mission(
        self,
        *,
        patient_id: str,
        condition_or_need: str,
        provider_query: str,
        lat: float,
        lng: float,
        title: str = "Find support and arrange care",
        kind: MissionKind = MissionKind.CARE_NAVIGATION,
    ) -> GoogleHealthMission:
        mission = GoogleHealthMission(
            patient_id=patient_id,
            kind=kind,
            title=title,
            condition_or_need=condition_or_need,
            provider_query=provider_query,
            location={"lat": lat, "lng": lng},
        )
        mission.record("mission.created", "HealthIA created a patient-scoped navigation mission.")
        self.store.save(mission)
        return mission

    def _execute(self, mission: GoogleHealthMission, grants: list[GoogleGrant], action: GoogleAction, payload: dict[str, Any], *, authorization_key: str = "") -> tuple[Any, ConnectorResult | None]:
        auth_id = mission.action_authorizations.get(authorization_key or str(action), "")
        req = GoogleActionRequest(
            patient_id=mission.patient_id,
            mission_id=mission.id,
            action=action,
            payload=payload,
            explicit_authorization_id=auth_id,
        )
        receipt, outcome = self.executor.execute(req, grants)
        mission.record(
            f"tool.{action}",
            receipt.safe_summary,
            resource_id=receipt.resource_id,
            evidence_ids=receipt.evidence_ids,
        )
        return receipt, outcome

    def discover(self, mission: GoogleHealthMission, grants: list[GoogleGrant], *, radius_m: int = 10000) -> GoogleHealthMission:
        if mission.state not in {MissionState.RECEIVED, MissionState.DISCOVERING, MissionState.BLOCKED}:
            raise MissionTransitionError(f"Cannot discover providers from {mission.state}")
        mission.state = MissionState.DISCOVERING
        maps_receipt, maps_outcome = self._execute(
            mission,
            grants,
            GoogleAction.MAPS_SEARCH_NEARBY,
            {
                "lat": mission.location["lat"],
                "lng": mission.location["lng"],
                "radius_m": radius_m,
                "max_results": 8,
            },
        )
        if maps_receipt.status != "completed" or maps_outcome is None:
            mission.state = MissionState.BLOCKED
            self.store.save(mission)
            return mission
        mission.tool_outputs["place_candidates"] = maps_outcome.data.get("places") or []
        mission.state = MissionState.AWAITING_SELECTION
        mission.record("mission.awaiting_selection", "Nearby candidates are ready; HealthIA needs one verified/selected destination before disclosure or contact.")
        self.store.save(mission)
        return mission

    def select_provider(self, mission: GoogleHealthMission, *, place: dict[str, Any], provider_email: str = "") -> GoogleHealthMission:
        if mission.state != MissionState.AWAITING_SELECTION:
            raise MissionTransitionError("Provider selection is only valid after discovery")
        mission.selected_place = dict(place)
        mission.provider_email = provider_email.strip()
        mission.state = MissionState.AWAITING_AUTHORIZATION if mission.provider_email else MissionState.AWAITING_SELECTION
        mission.record("provider.selected", "A provider/resource candidate was selected; clinical appropriateness is not inferred from proximity alone.", resource_id=str(place.get("id") or ""))
        self.store.save(mission)
        return mission

    def check_availability(self, mission: GoogleHealthMission, grants: list[GoogleGrant], *, time_min: str, time_max: str, time_zone: str) -> GoogleHealthMission:
        receipt, outcome = self._execute(
            mission,
            grants,
            GoogleAction.CALENDAR_FREEBUSY,
            {"time_min": time_min, "time_max": time_max, "time_zone": time_zone, "calendar_ids": ["primary"]},
        )
        if receipt.status == "completed" and outcome is not None:
            mission.tool_outputs["calendar_freebusy"] = outcome.data
        self.store.save(mission)
        return mission

    def authorize_action(self, mission: GoogleHealthMission, action: GoogleAction, authorization_id: str) -> GoogleHealthMission:
        if not authorization_id.strip():
            raise ValueError("authorization_id is required")
        mission.action_authorizations[str(action)] = authorization_id.strip()
        mission.record("authorization.recorded", f"Patient authorization recorded for {action}.", resource_id=authorization_id.strip())
        self.store.save(mission)
        return mission

    def contact_selected_provider(self, mission: GoogleHealthMission, grants: list[GoogleGrant], *, subject: str, body: str) -> GoogleHealthMission:
        if not mission.provider_email:
            raise MissionTransitionError("Selected provider has no verified/entered email destination")
        mission.state = MissionState.CONTACTING
        receipt, outcome = self._execute(
            mission,
            grants,
            GoogleAction.GMAIL_SEND,
            {"to": [mission.provider_email], "subject": subject, "body": body},
        )
        if receipt.status == "blocked":
            mission.state = MissionState.AWAITING_AUTHORIZATION
        elif receipt.status == "completed" and outcome is not None:
            mission.gmail_thread_id = str(outcome.data.get("threadId") or "")
            mission.state = MissionState.AWAITING_EXTERNAL_EVENT
            mission.record("mission.awaiting_reply", "Inquiry sent; mission is waiting for an event-driven provider reply.", resource_id=mission.gmail_thread_id)
        else:
            mission.state = MissionState.FAILED
        self.store.save(mission)
        return mission

    def ingest_gmail_reply(self, mission: GoogleHealthMission, signal: GmailReplySignal) -> GoogleHealthMission:
        if mission.state != MissionState.AWAITING_EXTERNAL_EVENT:
            raise MissionTransitionError("Gmail reply can only resume a mission waiting for an external event")
        if mission.gmail_thread_id and signal.thread_id != mission.gmail_thread_id:
            raise PermissionError("Gmail reply thread does not match the mission-linked thread")
        if signal.confidence < 0.7:
            mission.state = MissionState.AWAITING_EXTERNAL_EVENT
            mission.record("gmail.reply_ambiguous", "A reply arrived but its administrative meaning is not clear enough to act on automatically.", resource_id=signal.message_id)
        elif signal.classification in {"appointment_offered", "appointment_confirmed"} and signal.offered_slots:
            mission.offered_slots = list(signal.offered_slots)
            mission.state = MissionState.SLOT_OFFERED
            mission.record("gmail.appointment_offered", f"Provider offered {len(signal.offered_slots)} appointment slot(s).", resource_id=signal.message_id)
        elif signal.classification == "missing_documents":
            mission.required_documents = list(dict.fromkeys([*mission.required_documents, *signal.missing_documents]))
            mission.state = MissionState.AWAITING_EXTERNAL_EVENT
            mission.record("gmail.missing_documents", "Provider requested additional documents; the mission remains open.", resource_id=signal.message_id)
        elif signal.classification in {"approved", "application_received"}:
            mission.state = MissionState.AWAITING_EXTERNAL_EVENT
            mission.record(f"gmail.{signal.classification}", f"Provider/program reply classified as {signal.classification}; original message remains the source of truth.", resource_id=signal.message_id)
        elif signal.classification == "rejected":
            mission.state = MissionState.BLOCKED
            mission.record("gmail.rejected", "The external source states that the request was rejected; no appeal reason is invented.", resource_id=signal.message_id)
        else:
            mission.record("gmail.reply_received", "A mission-linked reply was received and preserved without forcing an unsupported status.", resource_id=signal.message_id)
        self.store.save(mission)
        return mission

    def choose_slot(self, mission: GoogleHealthMission, slot: OfferedSlot) -> GoogleHealthMission:
        if mission.state != MissionState.SLOT_OFFERED:
            raise MissionTransitionError("A slot can only be selected after an offer")
        if slot not in mission.offered_slots:
            raise ValueError("Selected slot is not one of the provider-offered slots")
        mission.selected_slot = slot
        mission.state = MissionState.AWAITING_AUTHORIZATION
        mission.record("slot.selected", "Patient selected one provider-offered appointment slot.", resource_id=slot.source_message_id)
        self.store.save(mission)
        return mission

    def finalize_appointment(
        self,
        mission: GoogleHealthMission,
        grants: list[GoogleGrant],
        *,
        summary: str,
        time_zone: str,
        create_followup_task: bool = True,
    ) -> GoogleHealthMission:
        if mission.selected_slot is None:
            raise MissionTransitionError("No provider-offered slot is selected")
        mission.state = MissionState.SCHEDULING
        place_name = str((mission.selected_place.get("displayName") or {}).get("text") or mission.selected_place.get("formattedAddress") or "Health appointment")
        event = {
            "summary": summary,
            "location": str(mission.selected_place.get("formattedAddress") or ""),
            "description": f"HealthIA mission {mission.id}. No diagnosis details are placed in the title.",
            "start": {"dateTime": mission.selected_slot.start, "timeZone": time_zone},
            "end": {"dateTime": mission.selected_slot.end, "timeZone": time_zone},
        }
        receipt, outcome = self._execute(
            mission,
            grants,
            GoogleAction.CALENDAR_CREATE_EVENT,
            {"calendar_id": "primary", "event": event},
        )
        if receipt.status == "blocked":
            mission.state = MissionState.AWAITING_AUTHORIZATION
            self.store.save(mission)
            return mission
        if receipt.status != "completed" or outcome is None:
            mission.state = MissionState.FAILED
            self.store.save(mission)
            return mission
        mission.calendar_event_id = receipt.resource_id
        mission.record("calendar.booked", f"Calendar event created for the selected provider slot at {place_name}.", resource_id=receipt.resource_id)

        if create_followup_task:
            task_receipt, _ = self._execute(
                mission,
                grants,
                GoogleAction.TASKS_CREATE,
                {
                    "tasklist": "@default",
                    "task": {
                        "title": "Prepare for health appointment",
                        "notes": "Review required documents and questions in HealthIA before the appointment.",
                        "due": mission.selected_slot.start,
                    },
                },
            )
            if task_receipt.status == "completed" and task_receipt.resource_id:
                mission.task_ids.append(task_receipt.resource_id)

        mission.state = MissionState.COMPLETED
        mission.record("mission.completed", "The navigation mission has a verifiable scheduled outcome and remains linked to its receipts.")
        self.store.save(mission)
        return mission
