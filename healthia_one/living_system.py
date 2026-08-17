from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from healthia_one.models import (
    AgentStep,
    AnatomyState,
    ClinicalEventEdge,
    DeviceMetric,
    DeviceObservation,
    EvaluationBudget,
    EvaluationSession,
    HealthConnectSyncBatch,
    HealthMission,
    HealthObligation,
    LivingTwinEvent,
    MedicationExpectation,
    MissionStatus,
    OrganSystemState,
    PatientBaseline,
    PatientState,
    RiskLevel,
    TwinDeviation,
    TwinTrajectory,
    VitalRecord,
    utc_now,
)
from healthia_one.devices import ingest_health_connect_batch
from healthia_one.twin import LIVING_TWIN_EVENT_SEQUENCE, advance_twin_version, clinical_twin_summary


EVALUATION_PATIENT_ID = "patient_eval_living"
SYNTHETIC_NAMESPACES = {"patient_demo", EVALUATION_PATIENT_ID, "judge_demo", "synthetic_judge"}


def _require_synthetic(state: PatientState) -> None:
    if state.profile.id not in SYNTHETIC_NAMESPACES and not state.profile.id.startswith("judge_"):
        raise PermissionError("Living System evaluation is restricted to an isolated synthetic patient")


def _require_session(state: PatientState, session_id: str, *, now: datetime) -> EvaluationSession:
    session = state.evaluation_session
    if session is None or session.id != session_id:
        raise PermissionError("Evaluation session not found")
    if session.patient_namespace != state.profile.id:
        raise PermissionError("Evaluation session namespace mismatch")
    if now >= session.expires_at:
        session.status = "expired"
        raise PermissionError("Evaluation session expired")
    if session.status in {"expired", "closed", "exhausted"}:
        raise PermissionError(f"Evaluation session is {session.status}")
    return session


def arm_evaluation(
    state: PatientState,
    *,
    now: datetime | None = None,
    session_minutes: int = 30,
    max_runs: int = 2,
    max_sessions: int = 2,
    release_sha: str = "local",
    runtime_revision: str = "local",
) -> EvaluationSession:
    _require_synthetic(state)
    current = now or utc_now()
    budget = state.evaluation_budget
    if budget is not None and budget.release_sha != release_sha:
        prior_session_id = state.evaluation_session.id if state.evaluation_session else ""
        state.twin_version = 1
        state.twin_parent_version = None
        state.twin_source_event_ids = []
        state.living_twin_events = []
        state.device_observations = []
        state.device_connections = []
        state.synced_external_ids = []
        state.vitals = [
            item
            for item in state.vitals
            if item.id != f"vital_receipt_{prior_session_id}"
            and item.source.source_id != "healthia.synthetic.evaluation"
        ]
        state.weights = [item for item in state.weights if item.source.source_id != "healthia.synthetic.evaluation"]
        state.activity = [item for item in state.activity if item.source.source_id != "healthia.synthetic.evaluation"]
        state.missions = [item for item in state.missions if not item.id.startswith("mission_living_")]
        state.organ_system_states = []
        state.anatomy_states = []
        state.medication_expectations = []
        state.baselines = []
        state.trajectories = []
        state.deviations = []
        state.clinical_event_edges = []
        state.obligations = []
        state.evaluation_session = None
    if budget is None or budget.release_sha != release_sha:
        budget = EvaluationBudget(
            release_sha=release_sha,
            max_sessions=max(1, min(max_sessions, 5)),
            max_runs=max(1, min(max_runs, 5)),
            updated_at=current,
        )
        state.evaluation_budget = budget
    existing = state.evaluation_session
    if (
        existing is not None
        and current < existing.expires_at
        and existing.status != "expired"
        and existing.release_sha == release_sha
    ):
        return existing
    if budget.sessions_created >= budget.max_sessions:
        if existing is not None:
            existing.status = "exhausted"
        raise PermissionError("Evaluation session budget exhausted for this release")
    budget.sessions_created += 1
    budget.updated_at = current
    state.evaluation_session = EvaluationSession(
        patient_namespace=state.profile.id,
        issued_at=current,
        expires_at=current + timedelta(minutes=max(1, min(session_minutes, 120))),
        max_runs=max(1, min(max_runs, 5)),
        release_sha=release_sha,
        runtime_revision=runtime_revision,
    )
    state.living_twin_events = []
    return state.evaluation_session


def _event(
    state: PatientState,
    session: EvaluationSession,
    event_type: str,
    actor: str,
    *,
    now: datetime,
    policy_decision: str = "not_applicable",
    status: str = "completed",
    evidence_ids: list[str] | None = None,
    source_event_ids: list[str] | None = None,
) -> LivingTwinEvent:
    event = LivingTwinEvent(
        id=f"twin_event_{session.id}_{event_type}",
        event_type=event_type,
        patient_namespace=state.profile.id,
        correlation_id=session.correlation_id or session.id,
        mission_id=session.mission_id,
        actor=actor,
        policy_decision=policy_decision,
        evidence_ids=evidence_ids or [],
        source_event_ids=source_event_ids or [],
        status=status,
        occurred_at=now,
    )
    if not any(item.id == event.id for item in state.living_twin_events):
        state.living_twin_events.append(event)
    return event


def _seed_longitudinal_breadth(state: PatientState, *, now: datetime) -> None:
    patient_id = state.profile.id
    if not any(item.id == "anatomy_gallbladder_removed" for item in state.anatomy_states):
        state.anatomy_states.append(
            AnatomyState(
                id="anatomy_gallbladder_removed",
                patient_id=patient_id,
                body_structure="gallbladder",
                status="removed",
                modification="synthetic laparoscopic cholecystectomy",
                procedure_id="procedure_cholecystectomy_2021",
                effective_at=now - timedelta(days=365 * 5),
                evidence_ids=["synthetic_discharge_2021"],
            )
        )
    if state.medication_plans and not state.medication_expectations:
        medication = state.medication_plans[0]
        state.medication_expectations.append(
            MedicationExpectation(
                id="med_expectation_bp_monitoring",
                patient_id=patient_id,
                medication_id=medication.id,
                expected_outcome="blood-pressure response documented for professional review",
                monitoring_metric="blood_pressure",
                review_due_at=now + timedelta(days=30),
                evidence_ids=[medication.id],
            )
        )
    if not state.organ_system_states:
        state.organ_system_states.extend(
            [
                OrganSystemState(
                    id="system_cardiovascular",
                    patient_id=patient_id,
                    system="cardiovascular",
                    status="watch",
                    summary="Correlated synthetic signals require confirmation, not diagnosis.",
                    trajectory="uncertain",
                    confidence=0.68,
                    evidence_ids=[],
                ),
                OrganSystemState(
                    id="system_metabolic_functional",
                    patient_id=patient_id,
                    system="metabolic_functional",
                    status="watch",
                    summary="Weight and activity changed together over the synthetic observation window.",
                    trajectory="uncertain",
                    confidence=0.64,
                    evidence_ids=[],
                ),
            ]
        )


def _ingest_synthetic_signal_bundle(state: PatientState, session: EvaluationSession, *, now: datetime) -> list[str]:
    records = [
        DeviceObservation(
            id=f"device_{session.id}_bp",
            patient_id=state.profile.id,
            external_id=f"{session.id}:bp",
            metric=DeviceMetric.BLOOD_PRESSURE,
            observed_at=now,
            value=142,
            secondary_value=88,
            unit="mmHg",
            source_package="healthia.synthetic.evaluation",
            source_name="Synthetic evaluation fixture",
            device_manufacturer="HealthIA",
            device_model="Living System",
            device_type="synthetic_fixture",
            recording_method="evaluation",
            metadata={"synthetic": True, "evaluation_session_id": session.id},
        ),
        DeviceObservation(
            id=f"device_{session.id}_weight",
            patient_id=state.profile.id,
            external_id=f"{session.id}:weight",
            metric=DeviceMetric.WEIGHT,
            observed_at=now,
            value=80.0,
            unit="kg",
            source_package="healthia.synthetic.evaluation",
            source_name="Synthetic evaluation fixture",
            device_manufacturer="HealthIA",
            device_model="Living System",
            device_type="synthetic_fixture",
            recording_method="evaluation",
            metadata={"synthetic": True, "evaluation_session_id": session.id},
        ),
        DeviceObservation(
            id=f"device_{session.id}_heart_rate",
            patient_id=state.profile.id,
            external_id=f"{session.id}:heart-rate",
            metric=DeviceMetric.HEART_RATE,
            observed_at=now,
            value=78,
            unit="bpm",
            source_package="healthia.synthetic.evaluation",
            source_name="Synthetic evaluation fixture",
            device_manufacturer="HealthIA",
            device_model="Living System",
            device_type="synthetic_fixture",
            recording_method="evaluation",
            metadata={"synthetic": True, "evaluation_session_id": session.id},
        ),
        DeviceObservation(
            id=f"device_{session.id}_steps",
            patient_id=state.profile.id,
            external_id=f"{session.id}:steps",
            metric=DeviceMetric.STEPS,
            observed_at=now,
            value=3200,
            unit="count",
            source_package="healthia.synthetic.evaluation",
            source_name="Synthetic evaluation fixture",
            device_manufacturer="HealthIA",
            device_model="Living System",
            device_type="synthetic_fixture",
            recording_method="evaluation",
            metadata={"synthetic": True, "evaluation_session_id": session.id},
        ),
    ]
    ingest_health_connect_batch(
        state,
        HealthConnectSyncBatch(
            device_id=f"synthetic-evaluation:{session.id}",
            source_package="healthia.synthetic.evaluation",
            synced_at=now,
            background_read=False,
            granted_metrics=[
                DeviceMetric.BLOOD_PRESSURE,
                DeviceMetric.WEIGHT,
                DeviceMetric.HEART_RATE,
                DeviceMetric.STEPS,
            ],
            records=records,
        ),
    )
    return [item.id for item in records]


def run_living_scenario(state: PatientState, session_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    _require_synthetic(state)
    current = now or utc_now()
    session = _require_session(state, session_id, now=current)
    if session.status in {"waiting_human", "completed"}:
        return living_system_snapshot(state)
    if session.runs_used >= session.max_runs:
        session.status = "exhausted"
        raise PermissionError("Evaluation run budget exhausted")
    budget = state.evaluation_budget
    if budget is None or budget.release_sha != session.release_sha:
        raise PermissionError("Evaluation release budget is unavailable")
    if budget.runs_used >= budget.max_runs:
        session.status = "exhausted"
        raise PermissionError("Evaluation global run budget exhausted for this release")
    session.status = "active"
    session.runs_used += 1
    budget.runs_used += 1
    budget.updated_at = current
    session.correlation_id = f"living_correlation_{session.id}_{session.runs_used}"
    source_ids = _ingest_synthetic_signal_bundle(state, session, now=current)

    _seed_longitudinal_breadth(state, now=current)
    if state.organ_system_states:
        state.organ_system_states[0].evidence_ids = source_ids[:1] + source_ids[2:3]
        if len(state.organ_system_states) > 1:
            state.organ_system_states[1].evidence_ids = source_ids[1:2] + source_ids[3:4]
    _event(state, session, "event_received", "ONE_SENSE", now=current, status="accepted", source_event_ids=source_ids)
    _event(state, session, "policy_checked", "ONE_SAFETY", now=current, policy_decision="allowed", evidence_ids=["consent_device_data"])

    normalized = _event(
        state,
        session,
        "observation_normalized",
        "ONE_SENSE",
        now=current,
        policy_decision="allowed",
        source_event_ids=source_ids,
        evidence_ids=source_ids,
    )
    advance_twin_version(
        state,
        normalized,
        changed_fields=["observations", "organ_system_state", "baseline", "trajectory"],
    )
    _event(state, session, "twin_versioned", "ONE_TWIN", now=current, evidence_ids=[normalized.id])

    baseline_specs = [
        ("systolic_bp", 126.0, "mmHg", 12),
        ("weight", 78.2, "kg", 10),
        ("resting_heart_rate", 68.0, "bpm", 14),
        ("daily_steps", 6500.0, "count", 14),
    ]
    existing_baselines = {item.metric for item in state.baselines}
    for metric, value, unit, sample_count in baseline_specs:
        if metric not in existing_baselines:
            state.baselines.append(
                PatientBaseline(
                    id=f"baseline_{metric}",
                    patient_id=state.profile.id,
                    metric=metric,
                    value=value,
                    unit=unit,
                    window_start=current - timedelta(days=30),
                    window_end=current - timedelta(days=4),
                    sample_count=sample_count,
                    confidence=0.9,
                    source_event_ids=[f"history_{metric}"],
                )
            )
    _event(state, session, "baseline_compared", "ONE_TWIN", now=current, evidence_ids=[item.id for item in state.baselines])

    observed = [
        ("systolic_bp", 142.0, 126.0, "mmHg", "higher", source_ids[0]),
        ("weight", 80.0, 78.2, "kg", "higher", source_ids[1]),
        ("resting_heart_rate", 78.0, 68.0, "bpm", "higher", source_ids[2]),
        ("daily_steps", 3200.0, 6500.0, "count", "lower", source_ids[3]),
    ]
    existing_deviations = {item.id for item in state.deviations}
    for metric, value, baseline, unit, direction, evidence_id in observed:
        deviation_id = f"deviation_{session.id}_{metric}"
        if deviation_id not in existing_deviations:
            state.deviations.append(
                TwinDeviation(
                    id=deviation_id,
                    patient_id=state.profile.id,
                    metric=metric,
                    observed_value=value,
                    baseline_value=baseline,
                    unit=unit,
                    direction=direction,
                    magnitude=value - baseline,
                    confidence=0.72,
                    status="correlated",
                    evidence_ids=[evidence_id],
                    detected_at=current,
                )
            )
        if not any(item.metric == metric for item in state.trajectories):
            state.trajectories.append(
                TwinTrajectory(
                    id=f"trajectory_{metric}",
                    patient_id=state.profile.id,
                    metric=metric,
                    direction="worsening" if direction == "higher" or metric == "daily_steps" else "uncertain",
                    slope=value - baseline,
                    unit=f"{unit}/window",
                    window_start=current - timedelta(days=4),
                    window_end=current,
                    confidence=0.66,
                    evidence_ids=[evidence_id],
                )
            )
    _event(state, session, "signals_correlated", "ONE_GUARDIAN", now=current, evidence_ids=source_ids)
    _event(state, session, "deviation_detected", "ONE_GUARDIAN", now=current, evidence_ids=[item.id for item in state.deviations])
    _event(state, session, "guardian_investigation_opened", "ONE_GUARDIAN", now=current, evidence_ids=source_ids)

    mission_id = f"mission_living_{session.id}"
    session.mission_id = mission_id
    mission = next((item for item in state.missions if item.id == mission_id), None)
    if mission is None:
        mission = HealthMission(
            id=mission_id,
            patient_id=state.profile.id,
            title="Confirm correlated change with a canonical blood-pressure measurement",
            mission_type="living_system_bp_continuity",
            status=MissionStatus.WAITING_PATIENT,
            risk_level=RiskLevel.WATCH,
            created_at=current,
            updated_at=current,
            next_action="Patient provides a correctly performed repeat measurement; no diagnosis or medication change.",
            evidence_ids=source_ids,
            agent_plan=[
                AgentStep(agent="ONE SENSE", action="validate synthetic source and units", reason="Identity and provenance precede interpretation", status="completed"),
                AgentStep(agent="ONE TWIN", action="version longitudinal state", reason="The Twin is canonical memory", status="completed"),
                AgentStep(agent="ONE GUARDIAN", action="open a bounded investigation", reason="Four weak signals changed together", status="completed"),
                AgentStep(agent="ONE SAFETY", action="require human measurement", reason="Clinical authority remains human", status="blocked"),
                AgentStep(agent="ONE VERIFY", action="wait for canonical receipt", reason="A mission cannot close from narration", status="planned"),
            ],
        )
        state.missions.append(mission)
    session.mission_id = mission.id
    _event(state, session, "mission_opened", "ONE_GUARDIAN", now=current, evidence_ids=mission.evidence_ids)

    if not any(item.id == f"obligation_{mission.id}" for item in state.obligations):
        state.obligations.append(
            HealthObligation(
                id=f"obligation_{mission.id}",
                patient_id=state.profile.id,
                reason="Correlated synthetic change requires confirmation before interpretation.",
                required_action="Record a canonical repeat blood-pressure measurement.",
                due_at=current + timedelta(days=1),
                status="waiting",
                evidence_ids=source_ids,
                closure_condition="repeat VitalRecord persisted and linked to mission verification receipt",
            )
        )
    if not any(item.id == f"edge_{mission.id}" for item in state.clinical_event_edges):
        state.clinical_event_edges.append(
            ClinicalEventEdge(
                id=f"edge_{mission.id}",
                patient_id=state.profile.id,
                source_event_id=normalized.id,
                target_entity_id=mission.id,
                relation="creates_obligation",
                confidence=0.72,
                evidence_ids=source_ids,
            )
        )
    _event(state, session, "human_boundary", "ONE_SAFETY", now=current, policy_decision="human_required", status="blocked", evidence_ids=[mission.id])
    session.status = "waiting_human"
    state.updated_at = current
    return living_system_snapshot(state)


def complete_living_scenario(
    state: PatientState,
    session_id: str,
    *,
    systolic: int,
    diastolic: int,
    pulse: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or utc_now()
    session = _require_session(state, session_id, now=current)
    if session.status != "waiting_human" or not session.mission_id:
        raise ValueError("Evaluation scenario is not waiting for human evidence")
    mission = next((item for item in state.missions if item.id == session.mission_id), None)
    if mission is None:
        raise ValueError("Evaluation mission not found")
    measurement = VitalRecord(
        id=f"vital_receipt_{session.id}",
        patient_id=state.profile.id,
        measured_at=current,
        systolic=systolic,
        diastolic=diastolic,
        pulse=pulse,
        source={"source_type": "synthetic_judge_entry", "source_id": session.id, "verified": False},
    )
    if not any(item.id == measurement.id for item in state.vitals):
        state.vitals.append(measurement)
    _event(state, session, "bounded_action_executed", "ONE_SENSE", now=current, policy_decision="allowed", evidence_ids=[measurement.id])
    _event(state, session, "receipt_recorded", "ONE_VERIFY", now=current, evidence_ids=[measurement.id])

    mission.status = MissionStatus.COMPLETED
    mission.updated_at = current
    mission.next_action = "Synthetic evidence receipt persisted; professional interpretation remains separate."
    mission.closure_evidence = list(dict.fromkeys([*mission.closure_evidence, measurement.id]))
    for step in mission.agent_plan:
        if step.agent in {"ONE SAFETY", "ONE VERIFY"}:
            step.status = "completed"
    for obligation in state.obligations:
        if obligation.id == f"obligation_{mission.id}":
            obligation.status = "completed"
            obligation.updated_at = current
            obligation.evidence_ids = list(dict.fromkeys([*obligation.evidence_ids, measurement.id]))
    _event(state, session, "mission_verified", "ONE_VERIFY", now=current, evidence_ids=[measurement.id, mission.id])
    learned = _event(
        state,
        session,
        "twin_updated_from_verified_outcome",
        "ONE_TWIN",
        now=current,
        evidence_ids=[measurement.id],
        source_event_ids=[measurement.id],
    )
    advance_twin_version(state, learned, changed_fields=["observations", "active_missions", "obligations", "future_detector_state"])
    session.status = "completed"
    session.completed_at = current
    state.updated_at = current
    return living_system_snapshot(state)


def living_system_snapshot(state: PatientState) -> dict[str, Any]:
    events = [item.model_dump(mode="json") for item in state.living_twin_events]
    event_types = [item["event_type"] for item in events]
    mission = None
    if state.evaluation_session and state.evaluation_session.mission_id:
        mission = next((item for item in state.missions if item.id == state.evaluation_session.mission_id), None)
    return {
        "synthetic": True,
        "model_calls": 0,
        "session": state.evaluation_session.model_dump(mode="json") if state.evaluation_session else None,
        "budget": state.evaluation_budget.model_dump(mode="json") if state.evaluation_budget else None,
        "twin": clinical_twin_summary(state),
        "events": events,
        "event_types": event_types,
        "expected_event_sequence": list(LIVING_TWIN_EVENT_SEQUENCE),
        "mission": mission.model_dump(mode="json") if mission else None,
        "truth_boundary": (
            "This deterministic synthetic evaluation demonstrates continuity and verification, not diagnosis, treatment, or medication change."
        ),
    }
