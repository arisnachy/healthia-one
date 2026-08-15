from __future__ import annotations

from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import plan_guardian_notification
from healthia_one.models import PatientState, RiskLevel


def _assessment() -> GuardianAssessment:
    return GuardianAssessment(
        observation_id="device_1",
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


def test_guardian_writes_patient_email_draft_without_claiming_diagnosis() -> None:
    state = PatientState()
    state.profile.email = "ana@example.com"

    plan = plan_guardian_notification(state, _assessment(), mission_id="mission_guardian")

    assert plan.email is not None
    assert plan.email.recipient == "ana@example.com"
    assert plan.email.delivery_mode == "draft_only"
    assert plan.email.diagnostic_claim is False
    assert plan.email.changes_treatment is False
    assert plan.email.contains_precise_location is False
    assert "association, not a diagnosis" in plan.email.body
    assert "No medication or treatment was changed" in plan.email.body


def test_guardian_email_requires_explicit_auto_send_signal_opt_in() -> None:
    state = PatientState()
    state.profile.email = "ana@example.com"
    state.consent.signal_types.extend(["guardian_email", "guardian_email_auto_send"])

    plan = plan_guardian_notification(state, _assessment(), mission_id="mission_guardian")

    assert plan.email is not None
    assert plan.email.delivery_mode == "eligible_auto_send"
    assert plan.email.consent_basis == ["guardian_email", "guardian_email_auto_send"]


def test_guardian_notification_does_not_request_email_when_assessment_should_not_interrupt() -> None:
    state = PatientState()
    state.profile.email = "ana@example.com"
    assessment = _assessment().model_copy(update={"notify_patient": False})

    plan = plan_guardian_notification(state, assessment, mission_id="mission_guardian")

    assert plan.in_app is False
    assert plan.email is None


def test_guardian_email_id_is_stable_for_same_patient_mission_and_assessment() -> None:
    state = PatientState()
    state.profile.email = "ana@example.com"
    first = plan_guardian_notification(state, _assessment(), mission_id="mission_guardian")
    second = plan_guardian_notification(state, _assessment(), mission_id="mission_guardian")

    assert first.email is not None and second.email is not None
    assert first.email.id == second.email.id
