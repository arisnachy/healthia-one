from __future__ import annotations

from healthia_one.config import Settings
from healthia_one.google_connector_runtime import ConnectorResult
from healthia_one.google_constellation import GoogleAction, GoogleService
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.google_oauth_credentials import GoogleOAuthConnection
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_email_delivery import GuardianEmailDispatcher
from healthia_one.models import HealthMission, MissionStatus, PatientState


class FakeGmailConnector:
    service = GoogleService.GMAIL

    def __init__(self) -> None:
        self.calls: list[tuple[GoogleAction, dict, str]] = []

    def execute(self, action, payload, *, idempotency_key):
        self.calls.append((action, dict(payload), idempotency_key))
        assert action == GoogleAction.GMAIL_SEND
        return ConnectorResult(
            resource_id="gmail_message_1",
            safe_summary="Sent one exact HealthIA BP follow-up.",
            external_mutation=True,
            evidence_ids=["gmail_thread:thread_bp_mainline"],
        )


def _assessment(**updates) -> GuardianAssessment:
    value = GuardianAssessment(
        observation_id="bp_due_1",
        metric="blood_pressure_followup",
        classification="bp_followup_due",
        summary="Blood-pressure follow-up is due.",
        notify_patient=True,
    )
    return value.model_copy(update=updates)


def _state(*, auto_send: bool = True) -> PatientState:
    state = PatientState()
    state.profile.email = "ana@example.com"
    state.consent.proactive_enabled = True
    state.consent.quiet_hours_start = "00:00"
    state.consent.quiet_hours_end = "00:00"
    state.missions = [
        HealthMission(
            id="mission_bp",
            patient_id=state.profile.id,
            title="Capture the next blood-pressure reading",
            mission_type="bp_followup_guardian_measurement",
            status=MissionStatus.WAITING_PATIENT,
            next_action="Wait for a new blood-pressure measurement.",
        )
    ]
    state.consent.signal_types.extend(["bp_followup", "guardian_email"])
    if auto_send:
        state.consent.signal_types.append("guardian_email_auto_send")
    return state


def _dispatcher():
    settings = Settings(store_backend="memory", data_path=".healthia-one/test-email.json")
    constellation = build_google_constellation_service(settings)
    fake = FakeGmailConnector()
    constellation.runtime.raw_executor.connectors[GoogleService.GMAIL] = fake
    constellation.runtime.oauth_connection_store.save(
        GoogleOAuthConnection(
            patient_id="patient_demo",
            google_account="healthia-connected@example.com",
            google_subject="google_subject_1",
            granted_scopes=["https://www.googleapis.com/auth/gmail.send"],
            secret_version_resource="projects/test/secrets/oauth/versions/1",
        )
    )
    return GuardianEmailDispatcher(settings, constellation=constellation), fake, constellation


def test_bp_guardian_email_auto_send_reaches_exact_patient_recipient() -> None:
    dispatcher, fake, constellation = _dispatcher()
    state = _state()
    result = dispatcher.dispatch(state, _assessment(), event_id="event_bp_1", mission_id="mission_bp")
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["recipient_is_patient_profile"] is True
    assert len(fake.calls) == 1
    action, payload, _ = fake.calls[0]
    assert action == GoogleAction.GMAIL_SEND
    assert payload["to"] == ["ana@example.com"]
    assert "not a diagnosis" in payload["body"]
    assert "No medication or treatment was changed" in payload["body"]
    assert payload["healthia_consent_basis"] == ["guardian_email", "guardian_email_auto_send"]
    assert any(grant.mission_id == "mission_bp" for grant in constellation.grants(state.profile.id))


def test_bp_guardian_email_is_idempotent() -> None:
    dispatcher, fake, _ = _dispatcher()
    state = _state()
    first = dispatcher.dispatch(state, _assessment(), event_id="event_bp_same", mission_id="mission_bp")
    second = dispatcher.dispatch(state, _assessment(), event_id="event_bp_same", mission_id="mission_bp")
    assert first["status"] == "sent"
    assert second["status"] == "recovered_existing"
    assert len(fake.calls) == 1


def test_bp_guardian_email_never_sends_without_standing_auto_send_consent() -> None:
    dispatcher, fake, constellation = _dispatcher()
    result = dispatcher.dispatch(_state(auto_send=False), _assessment(), event_id="event_bp_no_consent", mission_id="mission_bp")
    assert result["status"] == "skipped_auto_send_not_consented"
    assert result["sent"] == 0
    assert fake.calls == []
    assert constellation.grants("patient_demo") == []


def test_bp_guardian_email_fails_closed_on_precise_location() -> None:
    dispatcher, fake, _ = _dispatcher()
    assessment = _assessment(context={"latitude": 19.45, "longitude": -70.69})
    try:
        dispatcher.dispatch(_state(), assessment, event_id="event_bp_location", mission_id="mission_bp")
    except PermissionError as exc:
        assert "precise location" in str(exc)
    else:
        raise AssertionError("Precise location must fail closed before Gmail delivery")
    assert fake.calls == []


def test_unpromoted_guardian_classification_cannot_generate_mainline_email() -> None:
    dispatcher, fake, _ = _dispatcher()
    result = dispatcher.dispatch(
        _state(),
        _assessment(classification="recurring_context_pattern", metric="heart_rate"),
        event_id="event_not_promoted",
        mission_id="mission_bp",
    )
    assert result["status"] == "skipped_no_patient_email"
    assert fake.calls == []
