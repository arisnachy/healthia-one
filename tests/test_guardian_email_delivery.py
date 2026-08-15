from __future__ import annotations

from healthia_one.config import Settings
from healthia_one.google_connector_runtime import ConnectorResult
from healthia_one.google_constellation import GoogleAction, GoogleService
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.google_oauth_credentials import GoogleOAuthConnection
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_email_delivery import GuardianEmailDispatcher
from healthia_one.models import HealthMission, MissionStatus, PatientState, RiskLevel


class FakeGmailConnector:
    service = GoogleService.GMAIL

    def __init__(self) -> None:
        self.calls: list[tuple[GoogleAction, dict, str]] = []

    def execute(self, action, payload, *, idempotency_key):
        self.calls.append((action, dict(payload), idempotency_key))
        assert action == GoogleAction.GMAIL_SEND
        return ConnectorResult(
            resource_id="gmail_message_1",
            safe_summary="Sent one exact Guardian patient update.",
            external_mutation=True,
        )


def _assessment(**updates) -> GuardianAssessment:
    value = GuardianAssessment(
        observation_id="device_guardian_email_1",
        metric="heart_rate",
        classification="recurring_context_pattern",
        risk_level=RiskLevel.WATCH,
        summary="A repeated heart-rate pattern was detected around the same time and WORK context.",
        observed={"heart_rate_bpm": 132, "resting_baseline_bpm": 84},
        context={"location_context": "work", "time_hour_local_source": 10},
        inference="The pattern is associated with this recurring context and time window.",
        hypothesis="Causality is not established.",
        confidence="moderate",
        repeated_pattern=True,
        notify_patient=True,
        requires_human_review=True,
    )
    return value.model_copy(update=updates)


def _state(*, auto_send: bool = True) -> PatientState:
    state = PatientState()
    state.profile.email = "ana@example.com"
    # 00:00 -> 00:00 means no quiet-hours interval; tests stay deterministic
    # regardless of when GitHub Actions happens to run them.
    state.consent.quiet_hours_start = "00:00"
    state.consent.quiet_hours_end = "00:00"
    state.missions = [
        HealthMission(
            id="mission_guardian_email",
            patient_id=state.profile.id,
            title="Review a recurring physiological pattern",
            mission_type="guardian_recurring_context_pattern",
            status=MissionStatus.WAITING_PATIENT,
            risk_level=RiskLevel.WATCH,
            next_action="Ask the patient for missing context.",
        )
    ]
    if auto_send:
        state.consent.signal_types.extend(["guardian_email", "guardian_email_auto_send"])
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


def test_guardian_email_auto_send_reaches_gmail_with_exact_patient_recipient() -> None:
    dispatcher, fake, constellation = _dispatcher()
    state = _state()

    result = dispatcher.dispatch(
        state,
        _assessment(),
        event_id="event_guardian_email_1",
        mission_id="mission_guardian_email",
    )

    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["recipient_is_patient_profile"] is True
    assert len(fake.calls) == 1
    action, payload, _ = fake.calls[0]
    assert action == GoogleAction.GMAIL_SEND
    assert payload["to"] == ["ana@example.com"]
    assert "association, not a diagnosis" in payload["body"]
    assert "No medication or treatment was changed" in payload["body"]
    assert payload["healthia_consent_basis"] == ["guardian_email", "guardian_email_auto_send"]
    grants = constellation.grants(state.profile.id)
    assert any(grant.mission_id == "mission_guardian_email" for grant in grants)


def test_guardian_email_redelivery_is_idempotent_and_does_not_send_twice() -> None:
    dispatcher, fake, _ = _dispatcher()
    state = _state()

    first = dispatcher.dispatch(
        state,
        _assessment(),
        event_id="event_guardian_email_same",
        mission_id="mission_guardian_email",
    )
    second = dispatcher.dispatch(
        state,
        _assessment(),
        event_id="event_guardian_email_same",
        mission_id="mission_guardian_email",
    )

    assert first["status"] == "sent"
    assert second["status"] == "recovered_existing"
    assert second["recovered"] == 1
    assert len(fake.calls) == 1


def test_guardian_email_does_not_send_without_standing_auto_send_consent() -> None:
    dispatcher, fake, constellation = _dispatcher()
    state = _state(auto_send=False)

    result = dispatcher.dispatch(
        state,
        _assessment(),
        event_id="event_guardian_email_no_consent",
        mission_id="mission_guardian_email",
    )

    assert result["status"] == "skipped_auto_send_not_consented"
    assert result["sent"] == 0
    assert fake.calls == []
    assert constellation.grants(state.profile.id) == []


def test_guardian_email_fails_closed_if_precise_location_enters_assessment() -> None:
    dispatcher, fake, _ = _dispatcher()
    state = _state()
    assessment = _assessment(context={"location_context": "work", "latitude": 19.45, "longitude": -70.69})

    try:
        dispatcher.dispatch(
            state,
            assessment,
            event_id="event_guardian_email_precise_location",
            mission_id="mission_guardian_email",
        )
    except PermissionError as exc:
        assert "precise location" in str(exc)
    else:
        raise AssertionError("Precise location must fail closed before Gmail delivery")

    assert fake.calls == []


def test_guardian_email_skips_cleanly_when_google_account_is_not_connected() -> None:
    settings = Settings(store_backend="memory", data_path=".healthia-one/test-email-no-google.json")
    constellation = build_google_constellation_service(settings)
    fake = FakeGmailConnector()
    constellation.runtime.raw_executor.connectors[GoogleService.GMAIL] = fake
    dispatcher = GuardianEmailDispatcher(settings, constellation=constellation)

    result = dispatcher.dispatch(
        _state(),
        _assessment(),
        event_id="event_guardian_email_no_google",
        mission_id="mission_guardian_email",
    )

    assert result["status"] == "skipped_google_account_not_connected"
    assert result["sent"] == 0
    assert fake.calls == []
