from __future__ import annotations

from datetime import datetime, timedelta, timezone

from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_investigation import investigate_guardian_context
from healthia_one.models import DeviceMetric, DeviceObservation, MedicationCheckIn, PatientState, RiskLevel
from healthia_one.service import seed_state


def _history_with_hrv_sleep(now: datetime) -> list[DeviceObservation]:
    return [
        DeviceObservation(
            external_id=f"ctx-{index}",
            metric=DeviceMetric.HEART_RATE,
            observed_at=now - timedelta(days=4 - index),
            value=78 + index,
            unit="bpm",
            metadata={
                "activity_type": "still",
                "hrv_rmssd_ms": hrv,
                "sleep_minutes": sleep,
            },
        )
        for index, (hrv, sleep) in enumerate(((48, 430), (50, 445), (52, 420), (49, 440)))
    ]


def _assessment(now: datetime, **context_updates) -> GuardianAssessment:
    context = {
        "activity_type": "still",
        "exercise_session_active": False,
        "location_context": "work",
        "semantic_location_authorized": True,
        "time_hour_local_source": 10,
        "observed_at": now.isoformat(),
        "hrv_rmssd_ms": 24,
        "sleep_minutes": 285,
        "similar_prior_events": 4,
    }
    context.update(context_updates)
    return GuardianAssessment(
        observation_id="device_current",
        metric="heart_rate",
        classification="recurring_context_pattern",
        risk_level=RiskLevel.WATCH,
        summary="Repeated work-time heart-rate pattern.",
        observed={"heart_rate_bpm": 132, "resting_baseline_bpm": 78},
        context=context,
        inference="The pattern is associated with this recurring context and time window.",
        hypothesis="Causality is not established.",
        confidence="moderate",
        repeated_pattern=True,
        notify_patient=True,
        requires_human_review=True,
        provenance=["device_current"],
    )


def test_guardian_investigates_sleep_hrv_and_work_association_without_calling_it_stress() -> None:
    now = datetime.now(timezone.utc)
    state = PatientState()
    history = _history_with_hrv_sleep(now)

    investigation = investigate_guardian_context(state, _assessment(now), history=history)

    assert "hrv_below_recent_personal_context" in investigation.contextual_contributors
    assert "sleep_below_recent_personal_context" in investigation.contextual_contributors
    assert "recurring_work_time_association" in investigation.contextual_contributors
    assert investigation.causality_established is False
    assert investigation.diagnosis_made is False
    assert investigation.treatment_changed is False
    assert "none establishes" in investigation.safe_summary.lower()
    assert all("stress diagnosis" not in check.summary.lower() or "not" in check.summary.lower() for check in investigation.checks)


def test_guardian_marks_exercise_as_plausible_context_but_never_as_proof_of_safety() -> None:
    now = datetime.now(timezone.utc)
    state = PatientState()
    assessment = _assessment(
        now,
        activity_type="running",
        exercise_session_active=True,
        location_context="gym",
        hrv_rmssd_ms=None,
        sleep_minutes=None,
    ).model_copy(
        update={
            "classification": "likely_exertion_related",
            "repeated_pattern": False,
            "notify_patient": False,
            "requires_human_review": False,
        }
    )

    investigation = investigate_guardian_context(state, assessment, history=[])

    assert "recorded_physical_exertion" in investigation.contextual_contributors
    assert investigation.confidence == "moderate"
    assert "does not use that context to override safety thresholds" in investigation.safe_summary
    assert investigation.causality_established is False


def test_guardian_checks_recent_medication_timing_but_does_not_attribute_cause() -> None:
    now = datetime.now(timezone.utc)
    state = seed_state()
    medication_id = state.medication_plans[0].id
    state.medication_checkins.append(
        MedicationCheckIn(
            medication_id=medication_id,
            recorded_at=now - timedelta(hours=2),
            status="skipped",
        )
    )

    investigation = investigate_guardian_context(state, _assessment(now), history=_history_with_hrv_sleep(now))

    medication_check = next(check for check in investigation.checks if check.name == "medication_context")
    assert medication_check.status == "supports_context"
    assert "does not prove" in medication_check.summary
    assert "medication_timing_requires_review" in investigation.contextual_contributors
    assert investigation.treatment_changed is False


def test_guardian_asks_for_human_context_after_exhausting_available_signals() -> None:
    now = datetime.now(timezone.utc)
    state = PatientState()

    investigation = investigate_guardian_context(state, _assessment(now), history=[])

    questions = " ".join(investigation.missing_context_questions).lower()
    assert "symptoms" in questions
    assert "caffeine" in questions
    assert "stressed" in questions
    assert "dehydration" in questions
    assert investigation.causality_established is False
