from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from healthia_one.bp_followup_guardian import CONSENT_SIGNAL as BP_CONSENT, MISSION_TYPE as BP_MISSION_TYPE
from healthia_one.config import Settings
from healthia_one.gmail_composite_bridge import GmailCompositeEventBridge
from healthia_one.gmail_mission_events import (
    GmailMessageChange,
    GmailWatchState,
    MemoryGmailWatchStore,
)
from healthia_one.google_constellation import GoogleAction, GoogleService
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.google_connector_runtime import ConnectorResult
from healthia_one.google_oauth_credentials import GoogleOAuthConnection
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_email_delivery import GuardianEmailDispatcher
from healthia_one.guardian_email_reply import (
    GUARDIAN_EMAIL_REPLY_CONSENT,
    GuardianEmailReplyHandler,
    GuardianEmailReplyOutcome,
    MemoryGuardianEmailThreadStore,
    save_guardian_email_thread_link,
)
from healthia_one.models import HealthMission, MissionStatus, PatientConsent, PatientState, RiskLevel, VitalRecord
from healthia_one.service import HealthIAService
from healthia_one.store import MemoryStore


PATIENT_ID = "patient_demo"
PATIENT_EMAIL = "ana@example.com"


def _gmail_message(message_id: str, snippet: str, sender: str = PATIENT_EMAIL) -> dict:
    return {
        "id": message_id,
        "threadId": "thread_guardian_bp",
        "snippet": snippet,
        "payload": {
            "headers": [
                {"name": "From", "value": f"Ana <{sender}>"},
                {"name": "Subject", "value": "Re: HealthIA needs one measurement"},
            ]
        },
    }


def _gmail_thread(*messages: dict) -> dict:
    return {"id": "thread_guardian_bp", "messages": list(messages)}


def _authorized_bp_state() -> PatientState:
    state = PatientState()
    state.profile.email = PATIENT_EMAIL
    state.profile.care_plan.blood_pressure_due_days = 3
    state.consent.quiet_hours_start = "00:00"
    state.consent.quiet_hours_end = "00:00"
    for signal in (
        BP_CONSENT,
        "guardian_email",
        "guardian_email_auto_send",
        GUARDIAN_EMAIL_REPLY_CONSENT,
    ):
        if signal not in state.consent.signal_types:
            state.consent.signal_types.append(signal)
    return state


async def _open_bp_mission() -> tuple[HealthIAService, MemoryGuardianEmailThreadStore, str]:
    state = _authorized_bp_state()
    service = HealthIAService(Settings(store_backend="memory", llm_backend="mock", proactive_enabled=True))
    service.store = MemoryStore(state, autonomous_enabled=True)
    old = VitalRecord(
        measured_at=datetime.now(timezone.utc) - timedelta(days=5),
        systolic=138,
        diastolic=86,
    )
    await service.add_vital(old)
    opened = await service.snapshot()
    mission = next(item for item in opened.missions if item.mission_type == BP_MISSION_TYPE)
    assert mission.status == MissionStatus.WAITING_PATIENT
    threads = MemoryGuardianEmailThreadStore()
    save_guardian_email_thread_link(
        threads,
        patient_id=PATIENT_ID,
        mission_id=mission.id,
        thread_id="thread_guardian_bp",
        provider_message_id="healthia_sent_1",
        event_id="event_bp_due",
    )
    return service, threads, mission.id


@pytest.mark.asyncio
async def test_exact_patient_reply_records_bp_through_canonical_service_and_closes_mission() -> None:
    service, threads, mission_id = await _open_bp_mission()
    handler = GuardianEmailReplyHandler(service=service, thread_store=threads)

    outcome = await handler.handle(
        PATIENT_ID,
        _gmail_thread(_gmail_message("m1", "BP 128/80")),
        message_id="m1",
        history_id="101",
        thread_id="thread_guardian_bp",
    )

    assert outcome is not None
    assert outcome.action == "blood_pressure_recorded_from_email"
    final = await service.snapshot()
    mission = next(item for item in final.missions if item.id == mission_id)
    assert mission.status == MissionStatus.COMPLETED
    captured = next(item for item in final.vitals if item.id == outcome.evidence_id)
    assert (captured.systolic, captured.diastolic) == (128, 80)
    assert captured.source.source_type == "patient_email_reply"
    assert captured.source.source_id == "gmail:m1"
    assert captured.source.verified is False
    assert captured.id in mission.evidence_ids


@pytest.mark.asyncio
async def test_priority_bp_email_reply_uses_existing_safety_handoff_and_later_safe_reply_cannot_release_it() -> None:
    service, threads, mission_id = await _open_bp_mission()
    handler = GuardianEmailReplyHandler(service=service, thread_store=threads)

    first = await handler.handle(
        PATIENT_ID,
        _gmail_thread(_gmail_message("m_high", "BP 170/105")),
        message_id="m_high",
        history_id="101",
        thread_id="thread_guardian_bp",
    )
    assert first is not None
    after_high = await service.snapshot()
    mission = next(item for item in after_high.missions if item.id == mission_id)
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert mission.risk_level == RiskLevel.PRIORITY

    second = await handler.handle(
        PATIENT_ID,
        _gmail_thread(
            _gmail_message("m_high", "BP 170/105"),
            _gmail_message("m_safe", "BP 128/80"),
        ),
        message_id="m_safe",
        history_id="102",
        thread_id="thread_guardian_bp",
    )
    assert second is not None
    final = await service.snapshot()
    mission = next(item for item in final.missions if item.id == mission_id)
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert not any(item == "new_bp_measurement_present" for item in mission.closure_evidence)
    assert any(vital.systolic == 128 and vital.diastolic == 80 for vital in final.vitals)


@pytest.mark.asyncio
async def test_redelivered_same_gmail_message_is_exactly_once_for_clinical_data() -> None:
    service, threads, _ = await _open_bp_mission()
    handler = GuardianEmailReplyHandler(service=service, thread_store=threads)
    thread = _gmail_thread(_gmail_message("m_once", "BP 128/80"))

    first = await handler.handle(
        PATIENT_ID,
        thread,
        message_id="m_once",
        history_id="101",
        thread_id="thread_guardian_bp",
    )
    count_after_first = len((await service.snapshot()).vitals)
    second = await handler.handle(
        PATIENT_ID,
        thread,
        message_id="m_once",
        history_id="101",
        thread_id="thread_guardian_bp",
    )

    assert first is not None
    assert second is None
    assert len((await service.snapshot()).vitals) == count_after_first


@pytest.mark.asyncio
async def test_wrong_sender_unlinked_thread_or_missing_reply_consent_cannot_create_vital() -> None:
    service, threads, mission_id = await _open_bp_mission()
    handler = GuardianEmailReplyHandler(service=service, thread_store=threads)
    before = len((await service.snapshot()).vitals)

    wrong_sender = await handler.handle(
        PATIENT_ID,
        _gmail_thread(_gmail_message("m_wrong", "BP 128/80", sender="other@example.com")),
        message_id="m_wrong",
        history_id="101",
        thread_id="thread_guardian_bp",
    )
    assert wrong_sender is None

    unlinked = await handler.handle(
        PATIENT_ID,
        {"id": "other_thread", "messages": [_gmail_message("m_unlinked", "BP 128/80")]},
        message_id="m_unlinked",
        history_id="102",
        thread_id="other_thread",
    )
    assert unlinked is None

    state = await service.snapshot()
    state.consent.signal_types = [item for item in state.consent.signal_types if item != GUARDIAN_EMAIL_REPLY_CONSENT]
    await service.store.save(state)
    no_consent = await handler.handle(
        PATIENT_ID,
        _gmail_thread(_gmail_message("m_no_consent", "BP 128/80")),
        message_id="m_no_consent",
        history_id="103",
        thread_id="thread_guardian_bp",
    )
    assert no_consent is None
    final = await service.snapshot()
    assert len(final.vitals) == before
    assert next(item for item in final.missions if item.id == mission_id).status == MissionStatus.WAITING_PATIENT


@pytest.mark.asyncio
async def test_quoted_example_or_free_text_is_captured_but_never_inferred_as_bp() -> None:
    service, threads, mission_id = await _open_bp_mission()
    handler = GuardianEmailReplyHandler(service=service, thread_store=threads)
    before = len((await service.snapshot()).vitals)

    outcome = await handler.handle(
        PATIENT_ID,
        _gmail_thread(
            _gmail_message(
                "m_quote",
                "Thanks, I will do it later. On the previous message HealthIA said: BP 128/80",
            )
        ),
        message_id="m_quote",
        history_id="101",
        thread_id="thread_guardian_bp",
    )

    assert outcome is not None
    assert outcome.action == "reply_captured_no_clinical_inference"
    final = await service.snapshot()
    assert len(final.vitals) == before
    assert next(item for item in final.missions if item.id == mission_id).status == MissionStatus.WAITING_PATIENT
    message = next(item for item in reversed(final.messages) if item.metadata.get("gmail_message_id") == "m_quote")
    assert message.metadata["structured_action_applied"] is False


@pytest.mark.asyncio
async def test_completed_mission_rejects_stale_thread_measurement() -> None:
    service, threads, mission_id = await _open_bp_mission()
    handler = GuardianEmailReplyHandler(service=service, thread_store=threads)
    await handler.handle(
        PATIENT_ID,
        _gmail_thread(_gmail_message("m_close", "BP 128/80")),
        message_id="m_close",
        history_id="101",
        thread_id="thread_guardian_bp",
    )
    before = len((await service.snapshot()).vitals)

    stale = await handler.handle(
        PATIENT_ID,
        _gmail_thread(_gmail_message("m_stale", "BP 126/78")),
        message_id="m_stale",
        history_id="102",
        thread_id="thread_guardian_bp",
    )

    assert stale is None
    final = await service.snapshot()
    assert len(final.vitals) == before
    assert next(item for item in final.missions if item.id == mission_id).status == MissionStatus.COMPLETED


def test_guardian_email_reply_permission_is_nested_under_email_and_auto_send() -> None:
    replies_only = PatientConsent(signal_types=[GUARDIAN_EMAIL_REPLY_CONSENT])
    assert GUARDIAN_EMAIL_REPLY_CONSENT not in replies_only.signal_types

    base_and_reply = PatientConsent(signal_types=["guardian_email", GUARDIAN_EMAIL_REPLY_CONSENT])
    assert base_and_reply.signal_types == ["guardian_email"]

    fully_authorized = PatientConsent(
        signal_types=["guardian_email", "guardian_email_auto_send", GUARDIAN_EMAIL_REPLY_CONSENT]
    )
    assert GUARDIAN_EMAIL_REPLY_CONSENT in fully_authorized.signal_types


def test_thread_binding_cannot_be_reassigned_to_another_mission() -> None:
    store = MemoryGuardianEmailThreadStore()
    save_guardian_email_thread_link(
        store,
        patient_id=PATIENT_ID,
        mission_id="mission_1",
        thread_id="thread_1",
        provider_message_id="sent_1",
        event_id="event_1",
    )
    with pytest.raises(PermissionError):
        save_guardian_email_thread_link(
            store,
            patient_id=PATIENT_ID,
            mission_id="mission_2",
            thread_id="thread_1",
            provider_message_id="sent_2",
            event_id="event_2",
        )


class _Reader:
    def __init__(self, *, change: GmailMessageChange, latest: str, thread: dict):
        self.change = change
        self.latest = latest
        self.thread_payload = thread

    def added_messages(self, start_history_id):
        return [self.change], self.latest

    def thread(self, thread_id):
        return self.thread_payload


class _Resolver:
    def __init__(self, mission=None):
        self.mission = mission

    def waiting_by_thread(self, patient_id, thread_id):
        return self.mission


class _Coordinator:
    def ingest_gmail_reply(self, mission, signal):
        raise AssertionError("Administrative coordinator must not run for a Guardian-only thread")


class _Interpreter:
    def interpret(self, mission, thread, *, message_id, history_id):
        raise AssertionError("Administrative interpreter must not run for a Guardian-only thread")


class _GuardianHandler:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome
        self.error = error
        self.calls = 0

    async def handle(self, patient_id, gmail_thread, *, message_id, history_id, thread_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.outcome


def _envelope(history: str = "101") -> dict:
    payload = json.dumps({"emailAddress": PATIENT_EMAIL, "historyId": history}).encode("utf-8")
    data = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return {"message": {"data": data, "messageId": "pubsub_1", "publishTime": "2026-08-15T22:00:00Z"}}


@pytest.mark.asyncio
async def test_composite_bridge_advances_one_shared_cursor_after_guardian_success() -> None:
    watches = MemoryGmailWatchStore()
    watches.save(GmailWatchState(patient_id=PATIENT_ID, email_address=PATIENT_EMAIL, history_id="100"))
    outcome = GuardianEmailReplyOutcome(
        id="mission_bp",
        mission_id="mission_bp",
        thread_id="thread_guardian_bp",
        message_id="m1",
        action="blood_pressure_recorded_from_email",
        mission_status="completed",
        evidence_id="vital_1",
    )
    guardian = _GuardianHandler(outcome=outcome)
    reader = _Reader(
        change=GmailMessageChange(message_id="m1", thread_id="thread_guardian_bp", history_id="101"),
        latest="103",
        thread=_gmail_thread(_gmail_message("m1", "BP 128/80")),
    )
    bridge = GmailCompositeEventBridge(
        watch_store=watches,
        mission_resolver=_Resolver(None),
        coordinator=_Coordinator(),
        history_reader_factory=lambda patient_id: reader,
        interpreter=_Interpreter(),
        guardian_reply_handler=guardian,
    )

    resumed = await bridge.process(PATIENT_ID, _envelope("102"))

    assert resumed == [outcome]
    assert guardian.calls == 1
    assert watches.load(PATIENT_ID).history_id == "103"


@pytest.mark.asyncio
async def test_composite_bridge_failure_keeps_old_cursor_for_pubsub_retry() -> None:
    watches = MemoryGmailWatchStore()
    watches.save(GmailWatchState(patient_id=PATIENT_ID, email_address=PATIENT_EMAIL, history_id="100"))
    guardian = _GuardianHandler(error=RuntimeError("synthetic guardian failure"))
    reader = _Reader(
        change=GmailMessageChange(message_id="m1", thread_id="thread_guardian_bp", history_id="101"),
        latest="105",
        thread=_gmail_thread(_gmail_message("m1", "BP 128/80")),
    )
    bridge = GmailCompositeEventBridge(
        watch_store=watches,
        mission_resolver=_Resolver(None),
        coordinator=_Coordinator(),
        history_reader_factory=lambda patient_id: reader,
        interpreter=_Interpreter(),
        guardian_reply_handler=guardian,
    )

    with pytest.raises(RuntimeError, match="synthetic guardian failure"):
        await bridge.process(PATIENT_ID, _envelope("105"))
    assert watches.load(PATIENT_ID).history_id == "100"


class _ReplyableGmailConnector:
    service = GoogleService.GMAIL

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, action, payload, *, idempotency_key):
        self.calls += 1
        assert action == GoogleAction.GMAIL_SEND
        return ConnectorResult(
            resource_id="gmail_message_1",
            safe_summary="Sent Guardian email.",
            evidence_ids=["gmail_thread:thread_guardian_bp"],
            data={"id": "gmail_message_1", "threadId": "thread_guardian_bp"},
            external_mutation=True,
        )


def _bp_due_assessment() -> GuardianAssessment:
    return GuardianAssessment(
        observation_id="bp_old",
        metric="blood_pressure_followup",
        classification="bp_followup_due",
        risk_level=RiskLevel.WATCH,
        summary="A blood-pressure follow-up measurement is due.",
        notify_patient=True,
    )


def _email_dispatch_state() -> PatientState:
    state = _authorized_bp_state()
    state.missions = [
        HealthMission(
            id="mission_guardian_email",
            patient_id=PATIENT_ID,
            title="Capture blood pressure",
            mission_type=BP_MISSION_TYPE,
            status=MissionStatus.WAITING_PATIENT,
            risk_level=RiskLevel.WATCH,
            next_action="Capture a new blood-pressure measurement.",
        )
    ]
    return state


def test_completed_gmail_receipt_can_rebuild_reply_thread_link_without_resend() -> None:
    settings = Settings(store_backend="memory", data_path=".healthia-one/test-wave14-email.json")
    constellation = build_google_constellation_service(settings)
    connector = _ReplyableGmailConnector()
    constellation.runtime.raw_executor.connectors[GoogleService.GMAIL] = connector
    constellation.runtime.oauth_connection_store.save(
        GoogleOAuthConnection(
            patient_id=PATIENT_ID,
            google_account="healthia-connected@example.com",
            google_subject="google_subject_wave14",
            granted_scopes=["https://www.googleapis.com/auth/gmail.send"],
            secret_version_resource="projects/test/secrets/oauth/versions/1",
        )
    )
    first_store = MemoryGuardianEmailThreadStore()
    first_dispatcher = GuardianEmailDispatcher(
        settings,
        constellation=constellation,
        thread_store=first_store,
    )
    state = _email_dispatch_state()

    first = first_dispatcher.dispatch(
        state,
        _bp_due_assessment(),
        event_id="event_bp_email_same",
        mission_id="mission_guardian_email",
    )
    assert first["status"] == "sent"
    assert first["reply_thread_linked"] is True
    assert connector.calls == 1

    # Simulate a process restart/crash where the action receipt is durable but the
    # thread-link write must be reconstructed. A new empty store represents that
    # missing side effect; the same event must not send Gmail again.
    recovered_store = MemoryGuardianEmailThreadStore()
    second_dispatcher = GuardianEmailDispatcher(
        settings,
        constellation=constellation,
        thread_store=recovered_store,
    )
    second = second_dispatcher.dispatch(
        state,
        _bp_due_assessment(),
        event_id="event_bp_email_same",
        mission_id="mission_guardian_email",
    )

    assert second["status"] == "recovered_existing"
    assert second["reply_thread_linked"] is True
    assert second["gmail_thread_id"] == "thread_guardian_bp"
    assert connector.calls == 1
    link = recovered_store.load_by_thread(PATIENT_ID, "thread_guardian_bp")
    assert link is not None and link.mission_id == "mission_guardian_email"
