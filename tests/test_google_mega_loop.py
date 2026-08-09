import base64
import json
from typing import Any

from healthia_one.gmail_mission_events import (
    GmailMessageChange,
    GmailMissionEventBridge,
    GmailWatchState,
)
from healthia_one.gmail_watch_runtime import MemoryGmailWatchDirectory
from healthia_one.google_action_guard import GuardedGoogleActionExecutor, GuardedMissionExecutorAdapter
from healthia_one.google_connector_runtime import ConnectorResult, GoogleActionExecutor
from healthia_one.google_constellation import GrantBundle, GoogleAction, GoogleService
from healthia_one.google_constellation_runtime import GoogleConstellationRuntime, GoogleConstellationService
from healthia_one.google_constellation_store import (
    MemoryGoogleAuthorizationStore,
    MemoryGoogleGrantStore,
    MemoryGoogleReceiptStore,
)
from healthia_one.google_mission_runtime import (
    GmailReplySignal,
    MemoryMissionStore,
    MissionState,
    OfferedSlot,
)
from healthia_one.google_navigation_coordinator import HealthIAGoogleMissionCoordinator
from healthia_one.google_oauth_credentials import MemoryOAuthConnectionStore


class FakeConnector:
    def __init__(self, service: GoogleService):
        self.service = service
        self.calls: list[tuple[GoogleAction, dict[str, Any], str]] = []

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        self.calls.append((action, dict(payload), idempotency_key))
        if action == GoogleAction.MAPS_SEARCH_NEARBY:
            return ConnectorResult(
                safe_summary="Found one place candidate.",
                data={
                    "places": [
                        {
                            "id": "place_support",
                            "displayName": {"text": "Support Center"},
                            "formattedAddress": "Synthetic Street 1",
                            "websiteUri": "https://support.example.org",
                        }
                    ]
                },
            )
        if action == GoogleAction.CALENDAR_FREEBUSY:
            return ConnectorResult(
                safe_summary="Checked authorized calendar availability.",
                data={"calendars": {"primary": {"busy": []}}},
            )
        if action == GoogleAction.GMAIL_SEND:
            return ConnectorResult(
                resource_id="gmail_msg_1",
                safe_summary="Sent exact authorized provider inquiry.",
                data={"id": "gmail_msg_1", "threadId": "thread_1"},
                external_mutation=True,
            )
        if action == GoogleAction.CALENDAR_CREATE_EVENT:
            return ConnectorResult(
                resource_id="calendar_event_1",
                safe_summary="Created exact authorized calendar event.",
                data={"id": "calendar_event_1"},
                external_mutation=True,
            )
        if action == GoogleAction.TASKS_CREATE:
            return ConnectorResult(
                resource_id="task_1",
                safe_summary="Created exact authorized follow-up task.",
                data={"id": "task_1"},
                external_mutation=True,
            )
        raise AssertionError(f"Unexpected action: {action}")


class Reader:
    def __init__(self, slot: OfferedSlot):
        self.slot = slot
        self.calls = 0

    def added_messages(self, start_history_id):
        self.calls += 1
        return [GmailMessageChange(message_id="reply_1", thread_id="thread_1", history_id="901")], "901"

    def thread(self, thread_id):
        return {
            "id": thread_id,
            "messages": [
                {
                    "id": "reply_1",
                    "threadId": thread_id,
                    "snippet": "We can see you Wednesday at 10:30.",
                }
            ],
        }


class Resolver:
    def __init__(self, mission):
        self.mission = mission

    def waiting_by_thread(self, patient_id, thread_id):
        if (
            self.mission.patient_id == patient_id
            and self.mission.gmail_thread_id == thread_id
            and self.mission.state == MissionState.AWAITING_EXTERNAL_EVENT
        ):
            return self.mission
        return None


class Interpreter:
    def __init__(self, slot: OfferedSlot):
        self.slot = slot
        self.calls = 0

    def interpret(self, mission, gmail_thread, *, message_id, history_id):
        self.calls += 1
        return GmailReplySignal(
            thread_id=mission.gmail_thread_id,
            message_id=message_id,
            history_id=history_id,
            classification="appointment_offered",
            offered_slots=[self.slot],
            confidence=0.98,
            safe_excerpt="We can see you Wednesday at 10:30.",
        )


def pubsub_envelope(history="901"):
    raw = json.dumps({"emailAddress": "patient@example.com", "historyId": history}).encode("utf-8")
    data = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return {"message": {"data": data, "messageId": "push_1"}}


def production_shaped_runtime():
    maps = FakeConnector(GoogleService.MAPS)
    calendar = FakeConnector(GoogleService.CALENDAR)
    gmail = FakeConnector(GoogleService.GMAIL)
    tasks = FakeConnector(GoogleService.TASKS)
    grant_store = MemoryGoogleGrantStore()
    receipt_store = MemoryGoogleReceiptStore()
    authorization_store = MemoryGoogleAuthorizationStore()
    mission_store = MemoryMissionStore()
    raw = GoogleActionExecutor(
        connectors={
            GoogleService.MAPS: maps,
            GoogleService.CALENDAR: calendar,
            GoogleService.GMAIL: gmail,
            GoogleService.TASKS: tasks,
        },
        receipt_store=receipt_store,
    )
    guard = GuardedGoogleActionExecutor(
        executor=raw,
        grant_store=grant_store,
        authorization_store=authorization_store,
        receipt_store=receipt_store,
    )
    coordinator = HealthIAGoogleMissionCoordinator(
        GuardedMissionExecutorAdapter(guard),
        store=mission_store,
    )
    runtime = GoogleConstellationRuntime(
        coordinator=coordinator,
        grant_store=grant_store,
        receipt_store=receipt_store,
        authorization_store=authorization_store,
        oauth_connection_store=MemoryOAuthConnectionStore(),
        raw_executor=raw,
        guarded_executor=guard,
    )
    return GoogleConstellationService(runtime), receipt_store, authorization_store, maps, calendar, gmail, tasks


def test_guarded_mega_loop_maps_gmail_push_calendar_tasks_has_receipts_and_no_duplicate_side_effects():
    service, receipts, authorizations, maps, calendar, gmail, tasks = production_shaped_runtime()
    patient_id = "patient_demo"
    for bundle in (
        GrantBundle.MAPS_LOCATION,
        GrantBundle.CALENDAR_READ,
        GrantBundle.CALENDAR_WRITE,
        GrantBundle.GMAIL_SEND,
        GrantBundle.TASKS_WRITE,
    ):
        service.grant(patient_id, bundle)

    mission = service.coordinator.create_navigation_mission(
        patient_id=patient_id,
        condition_or_need="autism family support",
        provider_query="autism support center",
        lat=19.4517,
        lng=-70.6970,
    )
    mission = service.coordinator.discover(mission, service.grants(patient_id))
    assert mission.state == MissionState.AWAITING_SELECTION
    assert len(maps.calls) == 1

    mission = service.coordinator.select_provider(
        mission,
        place=mission.tool_outputs["place_candidates"][0],
        provider_email="intake@example.org",
    )
    mission = service.coordinator.check_availability(
        mission,
        service.grants(patient_id),
        time_min="2026-08-10T08:00:00-04:00",
        time_max="2026-08-17T18:00:00-04:00",
        time_zone="America/Santo_Domingo",
    )

    subject = "Intake availability"
    body = "Please share available intake slots and required documents."
    mission = service.coordinator.contact_selected_provider(
        mission,
        service.grants(patient_id),
        subject=subject,
        body=body,
    )
    assert mission.state == MissionState.AWAITING_AUTHORIZATION
    assert gmail.calls == []

    mail_auth = service.authorize_provider_contact(
        patient_id,
        mission.id,
        subject=subject,
        body=body,
    )
    # A real API/ADK continuation is a new request and reloads durable mission
    # state. Prove that the authorization persisted rather than relying on a
    # mutated Python object from the previous turn.
    mission = service.load_mission(patient_id, mission.id)
    mission = service.coordinator.contact_selected_provider(
        mission,
        service.grants(patient_id),
        subject=subject,
        body=body,
    )
    assert mission.state == MissionState.AWAITING_EXTERNAL_EVENT
    assert mission.gmail_thread_id == "thread_1"
    assert len(gmail.calls) == 1
    assert authorizations.get(patient_id, mail_auth.id).consumed_at is not None

    slot = OfferedSlot(
        start="2026-08-12T10:30:00-04:00",
        end="2026-08-12T11:30:00-04:00",
        time_zone="America/Santo_Domingo",
        source_message_id="reply_1",
    )
    reader = Reader(slot)
    interpreter = Interpreter(slot)
    watches = MemoryGmailWatchDirectory()
    watches.save(
        GmailWatchState(
            patient_id=patient_id,
            email_address="patient@example.com",
            history_id="900",
        )
    )
    resolver = Resolver(mission)
    bridge = GmailMissionEventBridge(
        watch_store=watches,
        mission_resolver=resolver,
        coordinator=service.coordinator,
        history_reader_factory=lambda _patient_id: reader,
        interpreter=interpreter,
    )

    resumed = bridge.process(patient_id, pubsub_envelope())
    assert len(resumed) == 1
    mission = resumed[0]
    resolver.mission = mission
    assert mission.state == MissionState.SLOT_OFFERED
    assert watches.load(patient_id).history_id == "901"

    # Same Pub/Sub history notification is a no-op and cannot re-run Gemini or side effects.
    assert bridge.process(patient_id, pubsub_envelope()) == []
    assert reader.calls == 1
    assert interpreter.calls == 1

    mission = service.coordinator.choose_slot(mission, slot)
    final_auths = service.authorize_appointment_finalize(
        patient_id,
        mission.id,
        summary="Support center appointment",
        time_zone="America/Santo_Domingo",
        include_followup_task=True,
    )
    # Same process-boundary proof for Calendar + Tasks authorizations.
    mission = service.load_mission(patient_id, mission.id)
    mission = service.coordinator.finalize_appointment(
        mission,
        service.grants(patient_id),
        summary="Support center appointment",
        time_zone="America/Santo_Domingo",
        create_followup_task=True,
    )

    assert mission.state == MissionState.COMPLETED
    assert mission.calendar_event_id == "calendar_event_1"
    assert mission.task_ids == ["task_1"]
    assert len(gmail.calls) == 1
    assert [call[0] for call in calendar.calls] == [
        GoogleAction.CALENDAR_FREEBUSY,
        GoogleAction.CALENDAR_CREATE_EVENT,
    ]
    assert len(tasks.calls) == 1
    assert all(authorizations.get(patient_id, item.id).consumed_at is not None for item in final_auths)

    completed_receipts = [item for item in receipts._values.values() if item.status == "completed"]
    actions = {item.action for item in completed_receipts}
    assert GoogleAction.MAPS_SEARCH_NEARBY in actions
    assert GoogleAction.CALENDAR_FREEBUSY in actions
    assert GoogleAction.GMAIL_SEND in actions
    assert GoogleAction.CALENDAR_CREATE_EVENT in actions
    assert GoogleAction.TASKS_CREATE in actions
    assert all(item.idempotency_key for item in completed_receipts)
    assert any(event.event_type == "mission.completed" for event in mission.public_events)
