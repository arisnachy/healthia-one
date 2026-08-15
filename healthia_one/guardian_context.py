from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any

from pydantic import BaseModel, Field

from healthia_one.models import (
    AgentStep,
    ChatMessage,
    DeviceMetric,
    DeviceObservation,
    HealthMission,
    MissionStatus,
    PatientState,
    RiskLevel,
)


SEMANTIC_LOCATION_VALUES = {"home", "work", "gym", "outdoor", "commuting", "unknown"}
EXERTION_ACTIVITIES = {"running", "cycling", "walking", "workout", "exercise"}
REST_ACTIVITIES = {"still", "resting", "sleeping", "unknown"}


class GuardianAssessment(BaseModel):
    observation_id: str
    metric: str
    classification: str
    risk_level: RiskLevel = RiskLevel.INFO
    summary: str
    observed: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    inference: str = ""
    hypothesis: str = ""
    confidence: str = "low"
    repeated_pattern: bool = False
    notify_patient: bool = False
    requires_human_review: bool = False
    can_suppress_safety: bool = False
    provenance: list[str] = Field(default_factory=list)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "enabled", "active"}


def _semantic_location(metadata: dict[str, Any]) -> str:
    # Location is a separate privacy boundary. The bridge must attest that the
    # patient authorized semantic place context; a bare location label alone is
    # not enough. Raw coordinates are never required by Guardian.
    if not _truthy(metadata.get("semantic_location_authorized")):
        return "unknown"
    value = str(metadata.get("location_context") or "unknown").strip().lower()
    if value not in SEMANTIC_LOCATION_VALUES:
        return "unknown"
    return value


def _activity(metadata: dict[str, Any]) -> str:
    value = str(metadata.get("activity_type") or "unknown").strip().lower()
    return value or "unknown"


def _exercise_active(metadata: dict[str, Any]) -> bool:
    return _truthy(metadata.get("exercise_session_active"))


def _same_time_bucket(a_hour: int, b_hour: int, width_hours: int = 2) -> bool:
    delta = abs(a_hour - b_hour)
    delta = min(delta, 24 - delta)
    return delta <= width_hours


def _resting_hr_baseline(history: list[DeviceObservation]) -> float | None:
    values: list[float] = []
    for item in history:
        if item.metric != DeviceMetric.HEART_RATE:
            continue
        activity = _activity(item.metadata)
        if activity not in REST_ACTIVITIES:
            continue
        if _exercise_active(item.metadata):
            continue
        if 30 <= item.value <= 220:
            values.append(float(item.value))
    if len(values) < 3:
        return None
    return round(mean(values[-30:]), 1)


def _repeated_context_pattern(
    history: list[DeviceObservation],
    record: DeviceObservation,
    *,
    baseline: float | None,
) -> tuple[bool, int]:
    if record.metric != DeviceMetric.HEART_RATE or baseline is None:
        return False, 0
    location = _semantic_location(record.metadata)
    activity = _activity(record.metadata)
    if location == "unknown" or activity not in REST_ACTIVITIES:
        return False, 0
    threshold = max(baseline + 15.0, baseline * 1.20)
    matches = 0
    for item in history:
        if item.metric != DeviceMetric.HEART_RATE:
            continue
        if _semantic_location(item.metadata) != location:
            continue
        if _activity(item.metadata) not in REST_ACTIVITIES:
            continue
        if not _same_time_bucket(item.observed_at.hour, record.observed_at.hour):
            continue
        if float(item.value) >= threshold:
            matches += 1
    return matches >= 3, matches


def assess_device_context(
    state: PatientState,
    record: DeviceObservation,
    *,
    history: list[DeviceObservation] | None = None,
) -> GuardianAssessment | None:
    """Interpret one device signal in context without overriding safety.

    Guardian runs only when the patient has proactive device monitoring enabled.
    It separates observation, context, inference and hypothesis so correlation is
    never silently promoted to causation.
    """
    if not state.consent.proactive_enabled or "device_data" not in state.consent.signal_types:
        return None
    if record.metric not in {DeviceMetric.HEART_RATE, DeviceMetric.BLOOD_PRESSURE}:
        return None

    prior = list(history if history is not None else state.device_observations)
    metadata = dict(record.metadata or {})
    location = _semantic_location(metadata)
    activity = _activity(metadata)
    exercise_active = _exercise_active(metadata)
    baseline = _resting_hr_baseline(prior)
    repeated, repeated_count = _repeated_context_pattern(prior, record, baseline=baseline)

    context = {
        "activity_type": activity,
        "exercise_session_active": exercise_active,
        "location_context": location,
        "semantic_location_authorized": location != "unknown",
        "time_hour_local_source": record.observed_at.hour,
        "observed_at": record.observed_at.isoformat(),
    }
    for key in ("hrv_rmssd_ms", "sleep_minutes", "stress_score", "work_context"):
        if key in metadata:
            context[key] = metadata[key]

    # Privacy boundary: do not copy raw coordinates into Guardian output.
    precise_location_ignored = any(key in metadata for key in ("latitude", "longitude", "lat", "lng"))
    if precise_location_ignored:
        context["precise_location_ignored"] = True

    if record.metric == DeviceMetric.BLOOD_PRESSURE:
        exertion = exercise_active or activity in EXERTION_ACTIVITIES or location == "gym"
        return GuardianAssessment(
            observation_id=record.id,
            metric=record.metric.value,
            classification="blood_pressure_context_review",
            risk_level=RiskLevel.WATCH,
            summary=(
                "Blood pressure was captured with exertion context; resting confirmation may be useful."
                if exertion
                else "Blood pressure was captured without a clear exertion context."
            ),
            observed={"systolic": record.value, "diastolic": record.secondary_value, "unit": record.unit},
            context=context,
            inference=(
                "The measurement may have been influenced by recent physical effort."
                if exertion
                else "No exercise explanation is established from the available context."
            ),
            hypothesis="Context can explain variability but does not invalidate a safety threshold.",
            confidence="moderate" if exertion else "low",
            notify_patient=False,
            requires_human_review=False,
            can_suppress_safety=False,
            provenance=[record.id],
        )

    exertion = exercise_active or activity in EXERTION_ACTIVITIES or location == "gym"
    observed = {"heart_rate_bpm": record.value}
    if baseline is not None:
        observed["resting_baseline_bpm"] = baseline

    if exertion:
        return GuardianAssessment(
            observation_id=record.id,
            metric=record.metric.value,
            classification="likely_exertion_related",
            risk_level=RiskLevel.INFO,
            summary="Heart-rate rise is temporally consistent with recorded physical exertion context.",
            observed=observed,
            context=context,
            inference="The current context supports exertion as a plausible explanation for the rise.",
            hypothesis="Exercise is a plausible explanation, not a diagnosis or proof of safety.",
            confidence="moderate",
            notify_patient=False,
            requires_human_review=False,
            can_suppress_safety=False,
            provenance=[record.id],
        )

    materially_above_baseline = baseline is not None and record.value >= max(baseline + 20.0, baseline * 1.30)
    if repeated and materially_above_baseline:
        location_label = location.upper()
        return GuardianAssessment(
            observation_id=record.id,
            metric=record.metric.value,
            classification="recurring_context_pattern",
            risk_level=RiskLevel.WATCH,
            summary=f"A repeated heart-rate pattern was detected around the same time and {location_label} context.",
            observed=observed,
            context={**context, "similar_prior_events": repeated_count},
            inference="The pattern is associated with this recurring context and time window.",
            hypothesis=(
                "Work, sleep, caffeine, emotional stress, medication timing or another factor could contribute; "
                "causality is not established."
            ),
            confidence="moderate",
            repeated_pattern=True,
            notify_patient=True,
            requires_human_review=True,
            can_suppress_safety=False,
            provenance=[record.id],
        )

    if materially_above_baseline and activity in REST_ACTIVITIES:
        return GuardianAssessment(
            observation_id=record.id,
            metric=record.metric.value,
            classification="unexpected_for_rest_context",
            risk_level=RiskLevel.WATCH,
            summary="Heart rate is materially above the patient's recent resting baseline without a recorded exercise context.",
            observed=observed,
            context=context,
            inference="The rise is not explained by the currently available activity context.",
            hypothesis="More context is needed before assigning a cause.",
            confidence="moderate",
            notify_patient=True,
            requires_human_review=True,
            can_suppress_safety=False,
            provenance=[record.id],
        )

    return GuardianAssessment(
        observation_id=record.id,
        metric=record.metric.value,
        classification="context_insufficient",
        risk_level=RiskLevel.INFO,
        summary="The signal was stored, but the available context is insufficient for a stronger interpretation.",
        observed=observed,
        context=context,
        inference="No contextual cause was established.",
        hypothesis="Continue longitudinal observation.",
        confidence="low",
        notify_patient=False,
        requires_human_review=False,
        can_suppress_safety=False,
        provenance=[record.id],
    )


def assess_guardian_batch(
    state: PatientState,
    records: list[DeviceObservation],
    *,
    history: list[DeviceObservation] | None = None,
) -> list[GuardianAssessment]:
    prior = list(history if history is not None else state.device_observations)
    assessments: list[GuardianAssessment] = []
    for record in sorted(records, key=lambda item: item.observed_at):
        assessment = assess_device_context(state, record, history=prior)
        if assessment is not None:
            assessments.append(assessment)
        prior.append(record)
    return assessments


def _mission_text(assessment: GuardianAssessment) -> tuple[str, str]:
    if assessment.classification == "recurring_context_pattern":
        title = "Review a recurring physiological pattern"
        next_action = (
            "Ask the patient what was happening around this time (work demand, caffeine, sleep, symptoms, medication timing or another factor) "
            "without treating the association as a diagnosis."
        )
        return title, next_action
    title = "Review an unexpected resting-context signal"
    next_action = (
        "Confirm current symptoms and context, then compare with the longitudinal record before deciding whether clinical review is needed."
    )
    return title, next_action


def apply_guardian_autonomy(
    state: PatientState,
    assessments: list[GuardianAssessment],
) -> dict[str, list[str]]:
    """Convert meaningful Guardian assessments into durable work without a chat prompt.

    This function runs inside the same patient-state transaction as Health Connect
    ingestion. It may create/update a patient mission and emit a durable Autopilot
    outbox event. It never changes treatment or suppresses the deterministic safety
    layer.
    """
    created_mission_ids: list[str] = []
    updated_mission_ids: list[str] = []
    event_ids: list[str] = []

    if not state.consent.proactive_enabled:
        return {"created_mission_ids": [], "updated_mission_ids": [], "event_ids": []}

    for assessment in assessments:
        if not (assessment.notify_patient or assessment.requires_human_review):
            continue

        mission_type = f"guardian_{assessment.classification}"
        open_mission = next(
            (
                item
                for item in state.missions
                if item.mission_type == mission_type
                and item.status in {MissionStatus.ACTIVE, MissionStatus.WAITING_PATIENT, MissionStatus.WAITING_PROFESSIONAL}
            ),
            None,
        )
        title, next_action = _mission_text(assessment)
        created = False
        if open_mission is None:
            mission = HealthMission(
                patient_id=state.profile.id,
                title=title,
                mission_type=mission_type,
                status=MissionStatus.WAITING_PATIENT,
                risk_level=assessment.risk_level,
                next_action=next_action,
                evidence_ids=list(dict.fromkeys(assessment.provenance)),
                agent_plan=[
                    AgentStep(
                        agent="GUARDIAN",
                        action="Interpret authorized device signal in context",
                        reason="Avoid treating an isolated wearable value as the whole clinical story",
                        status="completed",
                    ),
                    AgentStep(
                        agent="HISTORIA",
                        action="Compare with the patient's longitudinal baseline",
                        reason="Use the Clinical Twin context before escalating an unexplained pattern",
                        status="completed",
                    ),
                    AgentStep(
                        agent="KIRA",
                        action="Pause at the human boundary",
                        reason="The possible cause is not established and patient context is required",
                        status="blocked",
                    ),
                ],
            )
            state.missions.append(mission)
            state.messages.append(
                ChatMessage(
                    patient_id=state.profile.id,
                    role="assistant",
                    author="HealthIA Guardian",
                    content=(
                        f"{assessment.summary} I found an association, not a confirmed cause. "
                        "I prepared a short context review and paused because I need your input before going further."
                    ),
                    risk_level=assessment.risk_level,
                    mission_id=mission.id,
                    metadata={
                        "autonomous_guardian": True,
                        "guardian_assessment": assessment.model_dump(mode="json"),
                        "requires_human_review": True,
                        "treatment_changed": False,
                    },
                )
            )
            created_mission_ids.append(mission.id)
            created = True
        else:
            mission = open_mission
            for evidence_id in assessment.provenance:
                if evidence_id not in mission.evidence_ids:
                    mission.evidence_ids.append(evidence_id)
            mission.updated_at = state.updated_at
            updated_mission_ids.append(mission.id)

        # Use the already verified Autopilot outbox/Eventarc contract. The event
        # type remains patient_state_changed; payload.source narrows it to Guardian
        # so no new event schema is invented just for this wave.
        try:
            from healthia_one.opportunity_integration import enqueue_event

            event = enqueue_event(
                state,
                "patient_state_changed",
                dedupe_key=f"guardian|{assessment.observation_id}|{assessment.classification}|{mission.id}",
                payload={
                    "source": "guardian_context",
                    "mission_id": mission.id,
                    "mission_created": created,
                    "guardian_assessment": assessment.model_dump(mode="json"),
                    "notification_requested": bool(assessment.notify_patient),
                    "treatment_changed": False,
                    "human_boundary": True,
                },
            )
            event_ids.append(event.id)
        except Exception:
            # State persistence and safety must not fail merely because the async
            # outbox transport is unavailable. The caller can surface zero events
            # and cloud proof must fail closed until the outbox is healthy.
            continue

    return {
        "created_mission_ids": created_mission_ids,
        "updated_mission_ids": updated_mission_ids,
        "event_ids": event_ids,
    }


def guardian_pattern_summary(assessments: list[GuardianAssessment]) -> dict[str, Any]:
    counts = Counter(item.classification for item in assessments)
    return {
        "assessment_count": len(assessments),
        "classifications": dict(counts),
        "patient_notifications_needed": sum(1 for item in assessments if item.notify_patient),
        "human_review_needed": sum(1 for item in assessments if item.requires_human_review),
        "safety_can_be_suppressed": False,
    }
