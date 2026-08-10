import base64
import json

import pytest

from healthia_one.gmail_mission_events import (
    GeminiAdministrativeReplyInterpreter,
    GmailMessageChange,
    GmailMissionEventBridge,
    GmailPushNotification,
    GmailWatchState,
    MemoryGmailWatchStore,
    decode_gmail_pubsub_push,
)
from healthia_one.google_mission_runtime import (
    GmailReplySignal,
    GoogleHealthMission,
    GoogleHealthMissionCoordinator,
    MemoryMissionStore,
    MissionKind,
    MissionState,
    OfferedSlot,
)


class DummyExecutor:
    def execute(self, request, grants):
        raise AssertionError("No external tool execution is expected while ingesting an already-arrived Gmail event")


class Reader:
    def __init__(self, changes, latest="101", thread=None):
        self.changes = changes
        self.latest = latest
        self.thread_payload = thread or {"id": "thread_1", "messages": []}
        self.added_calls = []
        self.thread_calls = []

    def added_messages(self, start_history_id):
        self.added_calls.append(start_history_id)
        return list(self.changes), self.latest

    def thread(self, thread_id):
        self.thread_calls.append(thread_id)
        return self.thread_payload


class Resolver:
    def __init__(self, mission=None):
        self.mission = mission
        self.calls = []

    def waiting_by_thread(self, patient_id, thread_id):
        self.calls.append((patient_id, thread_id))
        if self.mission and self.mission.gmail_thread_id == thread_id:
            return self.mission
        return None


class Interpreter:
    def __init__(self, signal=None, error=None):
        self.signal = signal
        self.error = error
        self.calls = 0

    def interpret(self, mission, gmail_thread, *, message_id, history_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.signal or GmailReplySignal(
            thread_id=mission.gmail_thread_id,
            message_id=message_id,
            history_id=history_id,
            classification="other",
            confidence=0.2,
        )


def envelope(email="patient@example.com", history="101", message_id="pubsub_1"):
    payload = json.dumps({"emailAddress": email, "historyId": history}).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return {"message": {"data": encoded, "messageId": message_id, "publishTime": "2026-08-09T17:00:00Z"}}


def waiting_mission():
    return GoogleHealthMission(
        patient_id="patient_demo",
        kind=MissionKind.CARE_NAVIGATION,
        title="Arrange support",
        state=MissionState.AWAITING_EXTERNAL_EVENT,
        gmail_thread_id="thread_1",
        provider_email="center@example.org",
    )


def bridge(*, reader, resolver, interpreter, watch_history="100", email="patient@example.com"):
    watches = MemoryGmailWatchStore()
    watches.save(GmailWatchState(patient_id="patient_demo", email_address=email, history_id=watch_history))
    coordinator = GoogleHealthMissionCoordinator(DummyExecutor(), store=MemoryMissionStore())
    result = GmailMissionEventBridge(
        watch_store=watches,
        mission_resolver=resolver,
        coordinator=coordinator,
        history_reader_factory=lambda patient_id: reader,
        interpreter=interpreter,
    )
    return result, watches


def test_pubsub_decoder_requires_mailbox_and_numeric_history_id():
    decoded = decode_gmail_pubsub_push(envelope())
    assert decoded.email_address == "patient@example.com"
    assert decoded.history_id == "101"
    assert decoded.pubsub_message_id == "pubsub_1"

    with pytest.raises(ValueError):
        decode_gmail_pubsub_push({"message": {"data": ""}})

    invalid = base64.urlsafe_b64encode(json.dumps({"emailAddress": "a@b.com", "historyId": "x"}).encode()).decode()
    with pytest.raises(ValueError):
        decode_gmail_pubsub_push({"message": {"data": invalid}})


def test_mailbox_mismatch_is_rejected_before_history_read():
    reader = Reader([])
    event_bridge, watches = bridge(reader=reader, resolver=Resolver(), interpreter=Interpreter())
    with pytest.raises(PermissionError):
        event_bridge.process("patient_demo", envelope(email="other@example.com"))
    assert reader.added_calls == []
    assert watches.load("patient_demo").history_id == "100"


def test_duplicate_or_old_notification_is_noop():
    reader = Reader([])
    event_bridge, watches = bridge(reader=reader, resolver=Resolver(), interpreter=Interpreter(), watch_history="101")
    assert event_bridge.process("patient_demo", envelope(history="101")) == []
    assert reader.added_calls == []
    assert watches.load("patient_demo").history_id == "101"


def test_unrelated_mail_thread_is_ignored_but_cursor_advances_after_successful_scan():
    reader = Reader([GmailMessageChange(message_id="m1", thread_id="unrelated", history_id="101")], latest="102")
    resolver = Resolver(None)
    event_bridge, watches = bridge(reader=reader, resolver=resolver, interpreter=Interpreter())
    assert event_bridge.process("patient_demo", envelope(history="102")) == []
    assert resolver.calls == [("patient_demo", "unrelated")]
    assert reader.thread_calls == []
    assert watches.load("patient_demo").history_id == "102"


def test_exact_linked_thread_resumes_only_that_waiting_mission():
    mission = waiting_mission()
    slot = OfferedSlot(
        start="2026-08-12T10:30:00-04:00",
        end="2026-08-12T11:30:00-04:00",
        time_zone="America/Santo_Domingo",
        source_message_id="m1",
    )
    signal = GmailReplySignal(
        thread_id="thread_1",
        message_id="m1",
        history_id="101",
        classification="appointment_offered",
        offered_slots=[slot],
        confidence=0.95,
    )
    reader = Reader([GmailMessageChange(message_id="m1", thread_id="thread_1", history_id="101")], latest="101")
    interpreter = Interpreter(signal=signal)
    event_bridge, watches = bridge(reader=reader, resolver=Resolver(mission), interpreter=interpreter)
    resumed = event_bridge.process("patient_demo", envelope(history="101"))
    assert len(resumed) == 1
    assert resumed[0].state == MissionState.SLOT_OFFERED
    assert resumed[0].offered_slots == [slot]
    assert interpreter.calls == 1
    assert watches.load("patient_demo").history_id == "101"


def test_interpreter_failure_does_not_advance_history_cursor_or_partially_resume():
    mission = waiting_mission()
    reader = Reader([GmailMessageChange(message_id="m1", thread_id="thread_1", history_id="101")], latest="105")
    event_bridge, watches = bridge(
        reader=reader,
        resolver=Resolver(mission),
        interpreter=Interpreter(error=RuntimeError("synthetic interpreter failure")),
    )
    with pytest.raises(RuntimeError, match="synthetic interpreter failure"):
        event_bridge.process("patient_demo", envelope(history="105"))
    assert watches.load("patient_demo").history_id == "100"
    assert mission.state == MissionState.AWAITING_EXTERNAL_EVENT


def test_low_confidence_reply_keeps_mission_waiting_and_advances_processed_cursor():
    mission = waiting_mission()
    signal = GmailReplySignal(
        thread_id="thread_1",
        message_id="m1",
        history_id="101",
        classification="approved",
        safe_excerpt="We received your message and will review it.",
        confidence=0.4,
    )
    reader = Reader([GmailMessageChange(message_id="m1", thread_id="thread_1", history_id="101")], latest="101")
    event_bridge, watches = bridge(reader=reader, resolver=Resolver(mission), interpreter=Interpreter(signal=signal))
    resumed = event_bridge.process("patient_demo", envelope(history="101"))
    assert resumed[0].state == MissionState.AWAITING_EXTERNAL_EVENT
    assert resumed[0].public_events[-1].event_type == "gmail.reply_ambiguous"
    assert watches.load("patient_demo").history_id == "101"


def test_explicit_iso_appointment_offer_is_parsed_from_exact_new_message_without_llm():
    class Settings:
        llm_backend = "disabled"
        adk_ready = False

    mission = waiting_mission()
    interpreter = GeminiAdministrativeReplyInterpreter(Settings())
    signal = interpreter.interpret(
        mission,
        {
            "id": "thread_1",
            "messages": [
                {"id": "old", "snippet": "APPOINTMENT OFFERED. Start: 2026-01-01T01:00:00-04:00. End: 2026-01-01T02:00:00-04:00. Time zone: America/Santo_Domingo."},
                {"id": "m1", "snippet": "APPOINTMENT OFFERED. Start: 2026-08-12T10:30:00-04:00. End: 2026-08-12T11:00:00-04:00. Time zone: America/Santo_Domingo."},
            ],
        },
        message_id="m1",
        history_id="101",
    )

    assert signal.classification == "appointment_offered"
    assert signal.confidence == 1.0
    assert signal.offered_slots[0].start == "2026-08-12T10:30:00-04:00"
    assert signal.offered_slots[0].source_message_id == "m1"
