from __future__ import annotations

from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, Field

from healthia_one.guardian_context import GuardianAssessment
from healthia_one.models import DeviceMetric, DeviceObservation, PatientState


class GuardianInvestigationCheck(BaseModel):
    name: str
    status: Literal["supports_context", "does_not_explain", "insufficient", "neutral"]
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


class GuardianContextInvestigation(BaseModel):
    observation_id: str
    classification: str
    checks: list[GuardianInvestigationCheck] = Field(default_factory=list)
    contextual_contributors: list[str] = Field(default_factory=list)
    missing_context_questions: list[str] = Field(default_factory=list)
    causality_established: bool = False
    diagnosis_made: bool = False
    treatment_changed: bool = False
    confidence: Literal["low", "moderate", "high"] = "low"
    safe_summary: str = ""


def _metadata_series(history: list[DeviceObservation], key: str, *, limit: int = 30) -> list[float]:
    values: list[float] = []
    for item in history:
        raw = (item.metadata or {}).get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    return values[-limit:]


def _relative_low(current: float, baseline: float) -> bool:
    return current < (baseline * 0.75)


def _recent_medication_context(state: PatientState, assessment: GuardianAssessment) -> GuardianInvestigationCheck:
    active_med_ids = {item.id for item in state.medication_plans if item.active}
    if not active_med_ids:
        return GuardianInvestigationCheck(
            name="medication_context",
            status="neutral",
            summary="No active medication plan is recorded, so medication timing was not used as an explanation.",
        )

    observed_at_raw = assessment.context.get("observed_at")
    try:
        from datetime import datetime

        observed_at = datetime.fromisoformat(str(observed_at_raw))
    except Exception:
        observed_at = None

    checkins = [item for item in state.medication_checkins if item.medication_id in active_med_ids]
    checkins.sort(key=lambda item: item.recorded_at)
    recent = None
    if observed_at is not None:
        candidates = [
            item
            for item in checkins
            if item.recorded_at <= observed_at and (observed_at - item.recorded_at).total_seconds() <= 36 * 3600
        ]
        if candidates:
            recent = candidates[-1]
    elif checkins:
        recent = checkins[-1]

    if recent is None:
        return GuardianInvestigationCheck(
            name="medication_context",
            status="insufficient",
            summary="Active medication is recorded, but there is no recent check-in close enough to this signal to explain the pattern.",
        )
    if recent.status in {"late", "skipped", "unknown"}:
        return GuardianInvestigationCheck(
            name="medication_context",
            status="supports_context",
            summary=(
                f"A recent medication check-in is '{recent.status}'. This is a context clue only; it does not prove that medication timing caused the signal change."
            ),
            evidence_ids=[recent.id],
        )
    return GuardianInvestigationCheck(
        name="medication_context",
        status="neutral",
        summary="The nearest recorded medication check-in was marked taken; no medication-timing explanation is established.",
        evidence_ids=[recent.id],
    )


def investigate_guardian_context(
    state: PatientState,
    assessment: GuardianAssessment,
    *,
    history: list[DeviceObservation] | None = None,
) -> GuardianContextInvestigation:
    """Investigate available longitudinal context before asking the patient.

    The engine is intentionally association-first, not diagnostic. HRV, sleep,
    work context and medication timing can strengthen a *context review* but can
    never establish stress, a disease, or a medication effect by themselves.
    """
    prior = list(history if history is not None else state.device_observations)
    checks: list[GuardianInvestigationCheck] = []
    contributors: list[str] = []

    activity = str(assessment.context.get("activity_type") or "unknown").lower()
    exercise_active = bool(assessment.context.get("exercise_session_active"))
    if exercise_active or activity in {"running", "walking", "cycling", "workout", "exercise"}:
        checks.append(
            GuardianInvestigationCheck(
                name="exercise_context",
                status="supports_context",
                summary="Authorized exercise/activity context is present near the signal.",
                evidence_ids=list(assessment.provenance),
            )
        )
        contributors.append("recorded_physical_exertion")
    else:
        checks.append(
            GuardianInvestigationCheck(
                name="exercise_context",
                status="does_not_explain",
                summary="No authorized exercise session or exertion activity was recorded around this signal.",
                evidence_ids=list(assessment.provenance),
            )
        )

    hrv_current = assessment.context.get("hrv_rmssd_ms")
    hrv_history = _metadata_series(prior, "hrv_rmssd_ms")
    if hrv_current is not None and len(hrv_history) >= 3:
        current = float(hrv_current)
        baseline = float(median(hrv_history))
        if _relative_low(current, baseline):
            checks.append(
                GuardianInvestigationCheck(
                    name="hrv_context",
                    status="supports_context",
                    summary=(
                        f"HRV RMSSD is below its recent personal context ({current:.1f} ms vs median {baseline:.1f} ms). "
                        "HRV is nonspecific and is not treated as a stress diagnosis."
                    ),
                    evidence_ids=list(assessment.provenance),
                )
            )
            contributors.append("hrv_below_recent_personal_context")
        else:
            checks.append(
                GuardianInvestigationCheck(
                    name="hrv_context",
                    status="neutral",
                    summary="Available HRV is not markedly below its recent personal context.",
                    evidence_ids=list(assessment.provenance),
                )
            )
    elif hrv_current is not None:
        checks.append(
            GuardianInvestigationCheck(
                name="hrv_context",
                status="insufficient",
                summary="HRV is available for this signal, but there are not enough prior authorized HRV observations for a personal baseline.",
                evidence_ids=list(assessment.provenance),
            )
        )
    else:
        checks.append(
            GuardianInvestigationCheck(
                name="hrv_context",
                status="insufficient",
                summary="No authorized HRV context was available near this signal.",
            )
        )

    sleep_current = assessment.context.get("sleep_minutes")
    sleep_history = _metadata_series(prior, "sleep_minutes")
    if sleep_current is not None and len(sleep_history) >= 3:
        current_sleep = float(sleep_current)
        baseline_sleep = float(median(sleep_history))
        if current_sleep < max(baseline_sleep * 0.75, baseline_sleep - 90):
            checks.append(
                GuardianInvestigationCheck(
                    name="sleep_context",
                    status="supports_context",
                    summary=(
                        f"Recent sleep duration is below the patient's recent context ({current_sleep:.0f} vs median {baseline_sleep:.0f} minutes). "
                        "This is a possible contributor, not proof of cause."
                    ),
                    evidence_ids=list(assessment.provenance),
                )
            )
            contributors.append("sleep_below_recent_personal_context")
        else:
            checks.append(
                GuardianInvestigationCheck(
                    name="sleep_context",
                    status="neutral",
                    summary="Recent sleep duration is not markedly below its recent personal context.",
                    evidence_ids=list(assessment.provenance),
                )
            )
    elif sleep_current is not None:
        checks.append(
            GuardianInvestigationCheck(
                name="sleep_context",
                status="insufficient",
                summary="Sleep duration is available, but there is not enough longitudinal sleep context for comparison.",
                evidence_ids=list(assessment.provenance),
            )
        )
    else:
        checks.append(
            GuardianInvestigationCheck(
                name="sleep_context",
                status="insufficient",
                summary="No authorized recent sleep context was available for this signal.",
            )
        )

    location = str(assessment.context.get("location_context") or "unknown").lower()
    if assessment.repeated_pattern and location != "unknown":
        checks.append(
            GuardianInvestigationCheck(
                name="time_place_pattern",
                status="supports_context",
                summary=(
                    f"Similar deviations have recurred in the same coarse '{location}' context and time window. "
                    "This establishes an association only."
                ),
                evidence_ids=list(assessment.provenance),
            )
        )
        contributors.append(f"recurring_{location}_time_association")
    else:
        checks.append(
            GuardianInvestigationCheck(
                name="time_place_pattern",
                status="insufficient",
                summary="No repeated authorized time/place association is established yet.",
            )
        )

    medication_check = _recent_medication_context(state, assessment)
    checks.append(medication_check)
    if medication_check.status == "supports_context":
        contributors.append("medication_timing_requires_review")

    missing = [
        "Were you having symptoms at that time (palpitations, dizziness, chest discomfort, shortness of breath, headache or something else)?",
        "Had you recently used caffeine, nicotine, an energy drink, a decongestant or another stimulant?",
        "How stressed or emotionally activated did you feel at that moment, if at all?",
        "Was there illness, fever, dehydration, pain or unusually poor sleep that day?",
    ]
    if medication_check.status == "insufficient":
        missing.append("Was the usual medication taken on schedule around this event?")

    if assessment.classification == "likely_exertion_related":
        confidence: Literal["low", "moderate", "high"] = "moderate"
        safe_summary = "Available context supports physical exertion as a plausible explanation; Guardian does not use that context to override safety thresholds."
    elif len(contributors) >= 2 and assessment.repeated_pattern:
        confidence = "moderate"
        safe_summary = (
            "Guardian found multiple contextual associations worth reviewing, but none establishes a medical or psychological cause. "
            "The remaining questions belong to the patient/human review boundary."
        )
    else:
        confidence = "low"
        safe_summary = (
            "Guardian checked the available longitudinal context but did not establish a cause. The signal remains a review item, not a diagnosis."
        )

    return GuardianContextInvestigation(
        observation_id=assessment.observation_id,
        classification=assessment.classification,
        checks=checks,
        contextual_contributors=list(dict.fromkeys(contributors)),
        missing_context_questions=missing,
        causality_established=False,
        diagnosis_made=False,
        treatment_changed=False,
        confidence=confidence,
        safe_summary=safe_summary,
    )
