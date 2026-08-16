from typing import Any

import pytest

from healthia_one.google_constellation import GrantBundle, GoogleAction, GoogleGrant, GoogleService
from healthia_one.google_connector_runtime import ConnectorResult, GoogleActionExecutor, MemoryReceiptStore
from healthia_one.google_mission_runtime import (
    GmailReplySignal,
    GoogleHealthMissionCoordinator,
    MissionState,
    OfferedSlot,
)


def grant(bundle: GrantBundle) -> GoogleGrant:
    return GoogleGrant(patient_id="patient_demo", bundle=bundle)


class FakeConnector:
    def __init__(self, service: GoogleService) -> None:
        self.service = service
        self.calls: list[tuple[GoogleAction, dict[str, Any], str]] = []

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        self.calls.append((action, payload, idempotency_key))
        if action == GoogleAction.MAPS_SEARCH_NEARBY:
            return ConnectorResult(
                safe_summary="Found 2 nearby place candidates.",
                data={
                    "places": [
                        {"id": "place_a", "displayName": {"text": "Autism Support A"}, "formattedAddress": "Street A"},
                        {"id": "place_b", "displayName": {"text": "Autism Support B"}, "formattedAddress": "Street B"},
                    ]
                },
            )
        if action == GoogleAction.CALENDAR_FREEBUSY:
            return ConnectorResult(safe_summary="Checked availability.", data={"calendars": {"primary": {"busy": []}}})
        if action == GoogleAction.GMAIL_SEND:
            return ConnectorResult(
                resource_id="gmail_msg_1",
                safe_summary="Sent authorized inquiry.",
                data={"id": "gmail_msg_1", "threadId": "thread_1"},
                external_mutation=True,
            )
        if action == GoogleAction.CALENDAR_CREATE_EVENT:
            return ConnectorResult(
                resource_id="calendar_event_1",
                safe_summary="Created authorized calendar event.",
                data={"id": "calendar_event_1"},
                external_mutation=True,
            )
        if action == GoogleAction.TASKS_CREATE:
            return ConnectorResult(
                resource_id="task_1",
                safe_summary="Created preparation task.",
                data={"id": "task_1"},
                external_mutation=True,
            )
        raise AssertionError(f"Unexpected action {action}")


def runtime():
    maps = FakeConnector(GoogleService.MAPS)
    calendar = FakeConnector(GoogleService.CALENDAR)
    gmail = FakeConnector(GoogleService.GMAIL)
    tasks = FakeConnector(GoogleService.TASKS)
    executor = GoogleActionExecutor(
        connectors={
            GoogleService.MAPS: maps,
            GoogleService.CALENDAR: calendar,
            GoogleService.GMAIL: gmail,
            GoogleService.TASKS: tasks,
        },
        receipt_store=MemoryReceiptStore(),
    )
    return GoogleHealthMissionCoordinator(executor), maps, calendar, gmail, tasks


def test_one_patient_mission_crosses_maps_gmail_calendar_tasks_and_waits_for_event():
    coordinator, maps, calendar, gmail, tasks = runtime()
    grants = [
        grant(GrantBundle.MAPS_LOCATION),
        grant(GrantBundle.CALENDAR_READ),
        grant(GrantBundle.CALENDAR_WRITE),
        grant(GrantBundle.GMAIL_SEND),
        grant(GrantBundle.TASKS_WRITE),
    ]
    mission = coordinator.create_navigation_mission(
        patient_id="patient_demo",
        condition_or_need="autism support for son",
        provider_query="autism support center",
        lat=19.4517,
        lng=-70.6970,
    )

    mission = coordinator.discover(mission, grants)
    assert mission.state == MissionState.AWAITING_SELECTION
    assert len(mission.tool_outputs["place_candidates"]) == 2

    selected = mission.tool_outputs["place_candidates"][0]
    mission = coordinator.select_provider(mission, place=selected, provider_email="intake@example.org")
    mission = coordinator.check_availability(
        mission,
        grants,
        time_min="2026-08-10T08:00:00-04:00",
        time_max="2026-08-17T18:00:00-04:00",
        time_zone="America/Santo_Domingo",
    )

    # Gmail send cannot occur just because the agent has a send scope.
    mission = coordinator.contact_selected_provider(
        mission,
        grants,
        subject="Intake availability",
        body="Please share available intake slots and required documents.",
    )
    assert mission.state == MissionState.AWAITING_AUTHORIZATION
    assert len(gmail.calls) == 0

    coordinator.authorize_action(mission, GoogleAction.GMAIL_SEND, "authz_mail_1")
    mission = coordinator.contact_selected_provider(
        mission,
        grants,
        subject="Intake availability",
        body="Please share available intake slots and required documents.",
    )
    assert mission.state == MissionState.AWAITING_EXTERNAL_EVENT
    assert mission.gmail_thread_id == "thread_1"
    assert len(gmail.calls) == 1

    slot = OfferedSlot(
        start="2026-08-12T10:30:00-04:00",
        end="2026-08-12T11:30:00-04:00",
        time_zone="America/Santo_Domingo",
        source_message_id="gmail_reply_1",
    )
    mission = coordinator.ingest_gmail_reply(
        mission,
        GmailReplySignal(
            thread_id="thread_1",
            message_id="gmail_reply_1",
            history_id="9001",
            classification="appointment_offered",
            offered_slots=[slot],
            confidence=0.96,
            safe_excerpt="We can see you Wednesday at 10:30.",
        ),
    )
    assert mission.state == MissionState.SLOT_OFFERED

    mission = coordinator.choose_slot(mission, slot)
    coordinator.authorize_action(mission, GoogleAction.CALENDAR_CREATE_EVENT, "authz_calendar_1")
    coordinator.authorize_action(mission, GoogleAction.TASKS_CREATE, "authz_task_1")
    mission = coordinator.finalize_appointment(
        mission,
        grants,
        summary="Support center appointment",
        time_zone="America/Santo_Domingo",
    )

    assert mission.state == MissionState.COMPLETED
    assert mission.calendar_event_id == "calendar_event_1"
    assert mission.task_ids == ["task_1"]
    assert len(maps.calls) == 1
    assert [call[0] for call in calendar.calls] == [GoogleAction.CALENDAR_FREEBUSY, GoogleAction.CALENDAR_CREATE_EVENT]
    assert len(tasks.calls) == 1
    assert any(event.event_type == "mission.completed" for event in mission.public_events)


def test_ambiguous_reply_does_not_trigger_calendar_or_claim_approval():
    coordinator, _, calendar, _, _ = runtime()
    grants = [grant(GrantBundle.MAPS_LOCATION), grant(GrantBundle.GMAIL_SEND)]
    mission = coordinator.create_navigation_mission(
        patient_id="patient_demo",
        condition_or_need="community assistance",
        provider_query="community support",
        lat=19.45,
        lng=-70.69,
    )
    mission = coordinator.discover(mission, grants)
    mission = coordinator.select_provider(mission, place=mission.tool_outputs["place_candidates"][0], provider_email="help@example.org")
    coordinator.authorize_action(mission, GoogleAction.GMAIL_SEND, "authz_mail_2")
    mission = coordinator.contact_selected_provider(mission, grants, subject="Help", body="Please advise.")

    mission = coordinator.ingest_gmail_reply(
        mission,
        GmailReplySignal(
            thread_id="thread_1",
            message_id="reply_ambiguous",
            classification="approved",
            confidence=0.42,
            safe_excerpt="We received your note; someone will review it.",
        ),
    )

    assert mission.state == MissionState.AWAITING_EXTERNAL_EVENT
    assert mission.calendar_event_id == ""
    assert len(calendar.calls) == 0
    assert mission.public_events[-1].event_type == "gmail.reply_ambiguous"


def test_reply_from_unrelated_thread_is_rejected():
    coordinator, _, _, _, _ = runtime()
    grants = [grant(GrantBundle.MAPS_LOCATION), grant(GrantBundle.GMAIL_SEND)]
    mission = coordinator.create_navigation_mission(
        patient_id="patient_demo",
        condition_or_need="support",
        provider_query="support",
        lat=19.45,
        lng=-70.69,
    )
    mission = coordinator.discover(mission, grants)
    mission = coordinator.select_provider(mission, place=mission.tool_outputs["place_candidates"][0], provider_email="help@example.org")
    coordinator.authorize_action(mission, GoogleAction.GMAIL_SEND, "authz_mail_3")
    mission = coordinator.contact_selected_provider(mission, grants, subject="Help", body="Please advise.")

    with pytest.raises(PermissionError):
        coordinator.ingest_gmail_reply(
            mission,
            GmailReplySignal(
                thread_id="another_thread",
                message_id="reply_2",
                classification="appointment_offered",
                confidence=0.99,
            ),
        )
