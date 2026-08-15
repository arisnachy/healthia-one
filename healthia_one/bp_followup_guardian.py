from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from healthia_one.autopilot_event_intents import stage_event_intent
from healthia_one.control import audit
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.models import (
    AgentStep,
    ChatMessage,
    HealthMission,
    MissionStatus,
    PatientState,
    RiskLevel,
    VitalRecord,
)
from healthia_one.safety import assess_vital


MISSION_TYPE = "bp_followup_guardian_measurement"
RULE_KEY = "bp_followup_guardian:measurement"
CONSENT_SIGNAL = "bp_followup"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _blood_pressures(state: PatientState) -> list[VitalRecord]:
    return sorted(
        [
            vital
            for vital in state.vitals
            if vital.systolic is not None and vital.diastolic is not None
        ],
        key=lambda item: item.measured_at,
    )


def _open_mission(state: PatientState) -> HealthMission | None:
    return next(
        (
            mission
            for mission in reversed(state.missions)
            if mission.mission_type == MISSION_TYPE
            and mission.status in {
                MissionStatus.ACTIVE,
                MissionStatus.WAITING_PATIENT,
                MissionStatus.WAITING_PROFESSIONAL,
            }
        ),
        None,
    )


def _authorized(state: PatientState) -> bool:
    signals = set(state.consent.signal_types)
    return (
        state.consent.proactive_enabled
        and "vitals" in signals
        and CONSENT_SIGNAL in signals
        and not any(RULE_KEY.startswith(prefix) for prefix in state.consent.muted_rule_prefixes)
    )


def _due(state: PatientState, *, now: datetime) -> tuple[bool, VitalRecord | None]:
    readings = _blood_pressures(state)
    if not readings:
        # This Guardian follows an established monitoring stream. It does not
        # create a monitoring plan merely because a patient has no BP data.
        return False, None
    latest = readings[-1]
    due_days = max(int(state.profile.care_plan.blood_pressure_due_days), 1)
    return latest.measured_at <= now - timedelta(days=due_days), latest


def bp_followup_due(state: PatientState, *, now: datetime | None = None) -> bool:
    if not _authorized(state):
        return False
    current = now or utc_now()
    open_mission = _open_mission(state)
    if open_mission is not None:
        return True
    due, _ = _due(state, now=current)
    return due


def _assessment(
    *,
    vital: VitalRecord,
    classification: str,
    risk_level: RiskLevel,
    provenance: list[str],
) -> GuardianAssessment:
    return GuardianAssessment(
        observation_id=vital.id,
        metric="blood_pressure_followup",
        classification=classification,
        risk_level=risk_level,
        summary=(
            "The registered blood-pressure follow-up interval has elapsed without a newer measurement."
            if classification == "bp_followup_due"
            else (
                "A new blood-pressure measurement satisfies the data-capture mission but triggered the deterministic safety layer."
                if classification == "bp_followup_safety_handoff"
                else "A new blood-pressure measurement satisfied the open follow-up mission."
            )
        ),
        observed={
            "vital_id": vital.id,
            "measured_at": vital.measured_at.isoformat(),
            "systolic": vital.systolic,
            "diastolic": vital.diastolic,
        },
        context={"rule_key": RULE_KEY},
        inference=(
            "The monitoring interval in the patient-owned care plan is overdue."
            if classification == "bp_followup_due"
            else "A persisted blood-pressure reading arrived after the follow-up mission began."
        ),
        hypothesis=(
            "The patient may be able to provide a new measurement manually or through an authorized Health Connect source."
            if classification == "bp_followup_due"
            else "No clinical cause is inferred from the measurement by this mission."
        ),
        confidence="high",
        notify_patient=True,
        requires_human_review=classification == "bp_followup_safety_handoff",
        can_suppress_safety=False,
        provenance=list(dict.fromkeys(provenance)),
    )


def _stage(
    state: PatientState,
    mission: HealthMission,
    assessment: GuardianAssessment,
    *,
    event_kind: str,
) -> str:
    raw = f"{mission.id}|{assessment.observation_id}|{event_kind}"
    signature = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    event = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key=f"bp_followup|{signature}",
        payload={
            "source": "guardian_context",
            "guardian_domain": "blood_pressure_followup",
            "mission_id": mission.id,
            "guardian_assessment": assessment.model_dump(mode="json"),
            "notification_requested": True,
            "bp_followup_event": event_kind,
            "diagnosis_claimed": False,
            "treatment_changed": False,
            "safety_can_be_suppressed": False,
            "human_boundary": True,
        },
    )
    return event.id


def _ensure_safety_handoff_message(
    state: PatientState,
    mission: HealthMission,
    vital: VitalRecord,
    decision,
) -> None:
    if any(
        message.metadata.get("bp_followup_safety_handoff")
        and message.metadata.get("evidence_id") == vital.id
        for message in state.messages
    ):
        return
    # Device ingestion may already have emitted its authoritative deterministic
    # safety message. If so, attach the mission to the existing evidence instead
    # of duplicating the warning copy.
    existing_device_alert = next(
        (
            message
            for message in reversed(state.messages)
            if message.metadata.get("device_safety_alert")
            and message.metadata.get("evidence_id") == vital.id
        ),
        None,
    )
    if existing_device_alert is not None:
        existing_device_alert.mission_id = mission.id
        existing_device_alert.metadata["bp_followup_safety_handoff"] = True
        return
    state.messages.append(
        ChatMessage(
            patient_id=state.profile.id,
            role="assistant",
            author="HealthIA Safety",
            content=(
                f"{decision.message} The follow-up mission captured this measurement but remains open for human review; "
                "HealthIA did not mark the clinical situation as resolved or change treatment."
            ),
            risk_level=decision.level,
            mission_id=mission.id,
            metadata={
                "bp_followup_safety_handoff": True,
                "evidence_id": vital.id,
                "requires_human_review": True,
                "treatment_changed": False,
            },
        )
    )


def _open_due_mission(
    state: PatientState,
    latest: VitalRecord,
    *,
    now: datetime,
) -> dict[str, Any]:
    mission = HealthMission(
        patient_id=state.profile.id,
        title="Complete blood-pressure follow-up",
        mission_type=MISSION_TYPE,
        status=MissionStatus.WAITING_PATIENT,
        risk_level=RiskLevel.INFO,
        created_at=now,
        updated_at=now,
        next_action="Record a new blood-pressure measurement using your usual correct technique or an authorized connected source.",
        evidence_ids=[latest.id],
        agent_plan=[
            AgentStep(
                agent="BP FOLLOW-UP GUARDIAN",
                action="Detect that the patient-owned blood-pressure monitoring interval elapsed",
                reason="Turn a stale measurement stream into a durable follow-up task",
                status="completed",
            ),
            AgentStep(
                agent="VITA",
                action="Wait for a new manual or authorized device measurement",
                reason="Resolve with observed evidence rather than a reminder acknowledgement",
                status="running",
            ),
            AgentStep(
                agent="BASTION",
                action="Run deterministic vital-sign safety thresholds before mission closure",
                reason="A newly captured reading must never suppress an urgent or priority signal",
                status="running",
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
                "Your authorized blood-pressure follow-up interval has elapsed since the last recorded measurement. "
                "I opened a mission that will stay active until a new blood-pressure reading actually reaches your HealthIA record."
            ),
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            metadata={
                "autonomous_bp_followup": True,
                "bp_followup_due": True,
                "previous_bp_id": latest.id,
            },
        )
    )
    assessment = _assessment(
        vital=latest,
        classification="bp_followup_due",
        risk_level=RiskLevel.INFO,
        provenance=[latest.id],
    )
    event_id = _stage(state, mission, assessment, event_kind="due")
    audit(
        state,
        actor="healthia_bp_followup_guardian",
        action="open_bp_followup_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "previous_bp_id": latest.id,
            "event_id": event_id,
            "diagnosis_claimed": False,
            "treatment_changed": False,
        },
    )
    return {"status": "created", "mission_id": mission.id, "event_id": event_id, "previous_bp_id": latest.id}


def _new_reading_after_mission(state: PatientState, mission: HealthMission) -> VitalRecord | None:
    candidates = [
        vital
        for vital in _blood_pressures(state)
        if vital.measured_at >= mission.created_at and vital.id not in set(mission.evidence_ids)
    ]
    return candidates[-1] if candidates else None


def _reconcile_open_mission(
    state: PatientState,
    mission: HealthMission,
    vital: VitalRecord,
    *,
    now: datetime,
) -> dict[str, Any]:
    if vital.id not in mission.evidence_ids:
        mission.evidence_ids.append(vital.id)
    decision = assess_vital(vital)
    if decision.level in {RiskLevel.PRIORITY, RiskLevel.URGENT}:
        mission.status = MissionStatus.WAITING_PROFESSIONAL
        mission.risk_level = decision.level
        mission.updated_at = now
        mission.next_action = (
            "The requested measurement was captured, but deterministic safety escalation is active. Follow the safety guidance and obtain human clinical review."
        )
        _ensure_safety_handoff_message(state, mission, vital, decision)
        receipt = audit(
            state,
            actor="healthia_bp_followup_guardian",
            action="handoff_bp_followup_to_safety",
            resource_type="health_mission",
            resource_id=mission.id,
            details={
                "vital_id": vital.id,
                "risk_level": decision.level.value,
                "measurement_captured": True,
                "clinical_resolution_claimed": False,
                "treatment_changed": False,
            },
        )
        if receipt.id not in mission.closure_evidence:
            mission.closure_evidence.append(receipt.id)
        assessment = _assessment(
            vital=vital,
            classification="bp_followup_safety_handoff",
            risk_level=decision.level,
            provenance=[vital.id, receipt.id],
        )
        event_id = _stage(state, mission, assessment, event_kind="safety_handoff")
        return {
            "status": "safety_handoff",
            "mission_id": mission.id,
            "vital_id": vital.id,
            "risk_level": decision.level.value,
            "receipt_id": receipt.id,
            "event_id": event_id,
        }

    mission.status = MissionStatus.COMPLETED
    mission.risk_level = RiskLevel.INFO
    mission.updated_at = now
    mission.next_action = (
        "Measurement-capture mission closed automatically because a new blood-pressure reading is durably present. "
        "This does not mean the blood pressure is clinically controlled."
    )
    receipt = audit(
        state,
        actor="healthia_bp_followup_guardian",
        action="resolve_bp_followup_measurement_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "vital_id": vital.id,
            "resolution": "new_bp_measurement_present",
            "clinical_control_claimed": False,
            "diagnosis_claimed": False,
            "treatment_changed": False,
        },
    )
    mission.closure_evidence = list(dict.fromkeys([
        *mission.closure_evidence,
        "new_bp_measurement_present",
        receipt.id,
    ]))
    state.messages.append(
        ChatMessage(
            patient_id=state.profile.id,
            role="assistant",
            author="HealthIA Guardian",
            content=(
                "I received a new blood-pressure measurement and closed the measurement-capture mission automatically. "
                "That confirms the follow-up data arrived; it does not declare your blood pressure controlled and no treatment was changed."
            ),
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            metadata={
                "autonomous_bp_followup": True,
                "bp_followup_measurement_resolved": True,
                "evidence_id": vital.id,
                "resolution_receipt_id": receipt.id,
                "clinical_control_claimed": False,
            },
        )
    )
    assessment = _assessment(
        vital=vital,
        classification="bp_followup_measurement_resolved",
        risk_level=RiskLevel.INFO,
        provenance=[vital.id, receipt.id],
    )
    event_id = _stage(state, mission, assessment, event_kind="resolved")
    return {
        "status": "completed",
        "mission_id": mission.id,
        "vital_id": vital.id,
        "receipt_id": receipt.id,
        "event_id": event_id,
    }


def reconcile_bp_followup_guardian(state: PatientState, *, now: datetime | None = None) -> dict[str, Any]:
    """Maintain one autonomous BP measurement-capture loop with safety precedence."""
    current = now or utc_now()
    report: dict[str, Any] = {"created": [], "waiting": [], "completed": [], "safety_handoff": []}
    if not _authorized(state):
        return report

    mission = _open_mission(state)
    if mission is not None:
        reading = _new_reading_after_mission(state, mission)
        if reading is None:
            report["waiting"].append({"status": "waiting", "mission_id": mission.id})
            return report
        outcome = _reconcile_open_mission(state, mission, reading, now=current)
        report["safety_handoff" if outcome["status"] == "safety_handoff" else "completed"].append(outcome)
        return report

    due, latest = _due(state, now=current)
    if due and latest is not None:
        report["created"].append(_open_due_mission(state, latest, now=current))
    return report
