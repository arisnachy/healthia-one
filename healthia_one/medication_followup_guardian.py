from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from healthia_one.autopilot_event_intents import stage_event_intent
from healthia_one.control import audit
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.models import (
    AgentStep,
    ChatMessage,
    HealthMission,
    MedicationCheckIn,
    MedicationPlan,
    MissionStatus,
    PatientState,
    RiskLevel,
)
from healthia_one.safety import assess_text


MISSION_TYPE = "medication_followup_guardian_checkin"
RULE_KEY_PREFIX = "medication_followup_guardian"
CONSENT_SIGNAL = "medication_followup"
# This is a HealthIA tracking cadence, not a prescription schedule. It only
# decides when an already-established patient check-in stream deserves a
# continuity task. It never decides whether a medication dose is clinically due.
FOLLOWUP_DUE_HOURS = 36

_DOSE_CHANGE_OR_ERROR_PATTERNS = (
    re.compile(
        r"\b(?:debo|puedo|deberia|debería|me tomo|tomo|tomé|tome|should i|can i|could i|i took)\b"
        r".{0,70}\b(?:dos|doble|duplic\w*|aument\w*|sub\w*|baj\w*|reduc\w*|disminu\w*|suspend\w*|dejar de tomar|"
        r"double|two|increase|decrease|reduce|stop)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:doble|duplic\w*|aument\w*|sub\w*|baj\w*|reduc\w*|disminu\w*|suspend\w*|dejar de tomar|"
        r"double|increase|decrease|reduce|stop)\b.{0,70}\b(?:dosis|dose|medicamento|medication|pastilla|pill)\b",
        re.I,
    ),
)
_ADVERSE_CONTEXT = re.compile(
    r"\b(?:efecto secundario|efecto adverso|reaccion|reacción|mareo|desmayo|erupcion|erupción|rash|hinchazon|hinchazón|"
    r"vomito|vómito|vomitos|vómitos|side effect|adverse effect|dizzy|fainted|swelling|vomiting)\b",
    re.I,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mission_type(medication_id: str) -> str:
    return f"{MISSION_TYPE}:{medication_id}"


def medication_action_or_error_context(note: str) -> bool:
    value = str(note or "").strip()
    if not value:
        return False
    return any(pattern.search(value) for pattern in _DOSE_CHANGE_OR_ERROR_PATTERNS)


def medication_adverse_context(note: str) -> bool:
    return bool(_ADVERSE_CONTEXT.search(str(note or "")))


def _authorized(state: PatientState, medication_id: str | None = None) -> bool:
    signals = set(state.consent.signal_types)
    rule_key = f"{RULE_KEY_PREFIX}:{medication_id or '*'}"
    return (
        state.consent.proactive_enabled
        and "medications" in signals
        and CONSENT_SIGNAL in signals
        and not any(rule_key.startswith(prefix) for prefix in state.consent.muted_rule_prefixes)
    )


def _active_plans(state: PatientState) -> list[MedicationPlan]:
    return [plan for plan in state.medication_plans if plan.active]


def _checkins(state: PatientState, medication_id: str) -> list[MedicationCheckIn]:
    return sorted(
        [item for item in state.medication_checkins if item.medication_id == medication_id],
        key=lambda item: item.recorded_at,
    )


def _open_mission(state: PatientState, medication_id: str) -> HealthMission | None:
    expected_type = _mission_type(medication_id)
    return next(
        (
            mission
            for mission in reversed(state.missions)
            if mission.mission_type == expected_type
            and mission.status in {
                MissionStatus.ACTIVE,
                MissionStatus.WAITING_PATIENT,
                MissionStatus.WAITING_PROFESSIONAL,
            }
        ),
        None,
    )


def _due_plan(state: PatientState, plan: MedicationPlan, *, now: datetime) -> tuple[bool, MedicationCheckIn | None]:
    if not _authorized(state, plan.id):
        return False, None
    history = _checkins(state, plan.id)
    if not history:
        # No implicit adherence surveillance. The patient must first establish a
        # check-in stream before HealthIA is allowed to pursue it autonomously.
        return False, None
    latest = history[-1]
    return latest.recorded_at <= now - timedelta(hours=FOLLOWUP_DUE_HOURS), latest


def medication_followup_due(state: PatientState, *, now: datetime | None = None) -> bool:
    current = now or utc_now()
    for plan in _active_plans(state):
        if not _authorized(state, plan.id):
            continue
        if _open_mission(state, plan.id) is not None:
            return True
        due, _ = _due_plan(state, plan, now=current)
        if due:
            return True
    return False


def _assessment(
    *,
    observation_id: str,
    medication_id: str,
    classification: str,
    risk_level: RiskLevel,
    summary: str,
    provenance: list[str],
) -> GuardianAssessment:
    return GuardianAssessment(
        observation_id=observation_id,
        metric="medication_followup",
        classification=classification,
        risk_level=risk_level,
        summary=summary,
        observed={"medication_id": medication_id},
        context={"rule_key": f"{RULE_KEY_PREFIX}:{medication_id}"},
        inference=(
            "The patient-established medication check-in stream has exceeded HealthIA's continuity tracking interval."
            if classification == "medication_followup_due"
            else "A persisted medication check-in arrived after the follow-up mission began."
        ),
        hypothesis="No adherence, diagnosis, medication safety, or treatment-effect conclusion is inferred by this mission.",
        confidence="high",
        notify_patient=True,
        requires_human_review=classification in {
            "medication_followup_safety_handoff",
            "medication_followup_review_handoff",
        },
        can_suppress_safety=False,
        provenance=list(dict.fromkeys(provenance)),
    )


def _stage(
    state: PatientState,
    mission: HealthMission,
    assessment: GuardianAssessment,
    *,
    event_kind: str,
    medication_id: str,
) -> str:
    raw = f"{mission.id}|{assessment.observation_id}|{event_kind}"
    signature = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    event = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key=f"medication_followup|{signature}",
        payload={
            "source": "guardian_context",
            "guardian_domain": "medication_followup",
            "mission_id": mission.id,
            "medication_id": medication_id,
            "guardian_assessment": assessment.model_dump(mode="json"),
            "notification_requested": True,
            "medication_followup_event": event_kind,
            "diagnosis_claimed": False,
            "adherence_claimed": False,
            "dose_instruction_given": False,
            "treatment_changed": False,
            "human_boundary": True,
        },
    )
    return event.id


def _open_due_mission(
    state: PatientState,
    plan: MedicationPlan,
    latest: MedicationCheckIn,
    *,
    now: datetime,
) -> dict[str, Any]:
    mission = HealthMission(
        patient_id=state.profile.id,
        title=f"Medication check-in: {plan.name}",
        mission_type=_mission_type(plan.id),
        status=MissionStatus.WAITING_PATIENT,
        risk_level=RiskLevel.INFO,
        created_at=now,
        updated_at=now,
        next_action=(
            f"Record the next check-in for {plan.name} as taken, late, skipped, or unknown. "
            "Do not change or compensate the prescribed dose based on this mission."
        ),
        evidence_ids=[latest.id],
        agent_plan=[
            AgentStep(
                agent="MEDSAFE",
                action="Detect a gap in the patient-established medication check-in stream",
                reason="Turn a continuity gap into a durable evidence-capture task without inferring a missed dose",
                status="completed",
            ),
            AgentStep(
                agent="NAVIGATOR",
                action="Wait for the next explicit medication check-in",
                reason="Resolve only when patient-reported evidence is durably present",
                status="running",
            ),
            AgentStep(
                agent="SENTINEL",
                action="Block dose changes and urgent-language shortcuts",
                reason="Autonomy must never become prescribing or suppress clinical safety",
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
                f"Your authorized HealthIA check-in tracking for {plan.name} has gone longer than its continuity interval. "
                "I opened a mission to capture the next check-in. This does not mean HealthIA believes you missed a dose, "
                "and it is not an instruction to take, repeat, double, skip, or change medication."
            ),
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            metadata={
                "autonomous_medication_followup": True,
                "medication_followup_due": True,
                "medication_id": plan.id,
                "previous_checkin_id": latest.id,
                "tracking_due_hours": FOLLOWUP_DUE_HOURS,
                "tracking_interval_not_prescription_schedule": True,
                "dose_instruction_given": False,
            },
        )
    )
    assessment = _assessment(
        observation_id=latest.id,
        medication_id=plan.id,
        classification="medication_followup_due",
        risk_level=RiskLevel.INFO,
        summary="A patient-established medication check-in stream is due for continuity follow-up.",
        provenance=[plan.id, latest.id],
    )
    event_id = _stage(state, mission, assessment, event_kind="due", medication_id=plan.id)
    audit(
        state,
        actor="healthia_medication_followup_guardian",
        action="open_medication_followup_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "medication_id": plan.id,
            "previous_checkin_id": latest.id,
            "tracking_due_hours": FOLLOWUP_DUE_HOURS,
            "tracking_interval_not_prescription_schedule": True,
            "dose_instruction_given": False,
            "adherence_claimed": False,
            "treatment_changed": False,
            "event_id": event_id,
        },
    )
    return {
        "status": "created",
        "mission_id": mission.id,
        "medication_id": plan.id,
        "previous_checkin_id": latest.id,
        "event_id": event_id,
    }


def _new_checkin_after_mission(state: PatientState, mission: HealthMission, medication_id: str) -> MedicationCheckIn | None:
    seen = set(mission.evidence_ids)
    candidates = [
        item
        for item in _checkins(state, medication_id)
        if item.recorded_at >= mission.created_at and item.id not in seen
    ]
    return candidates[-1] if candidates else None


def _append_human_gate_evidence(
    state: PatientState,
    mission: HealthMission,
    checkin: MedicationCheckIn,
    *,
    now: datetime,
) -> dict[str, Any]:
    if checkin.id not in mission.evidence_ids:
        mission.evidence_ids.append(checkin.id)
    mission.updated_at = now
    mission.next_action = (
        "Additional medication check-in evidence was captured, but this mission remains human-gated because an earlier check-in triggered safety or medication-change review."
    )
    receipt = audit(
        state,
        actor="healthia_medication_followup_guardian",
        action="append_medication_evidence_while_waiting_professional",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "checkin_id": checkin.id,
            "human_release_required": True,
            "dose_instruction_given": False,
            "clinical_resolution_claimed": False,
            "treatment_changed": False,
        },
    )
    if receipt.id not in mission.closure_evidence:
        mission.closure_evidence.append(receipt.id)
    return {
        "status": "review_handoff",
        "mission_id": mission.id,
        "checkin_id": checkin.id,
        "human_release_required": True,
        "receipt_id": receipt.id,
    }


def _handoff(
    state: PatientState,
    mission: HealthMission,
    plan: MedicationPlan,
    checkin: MedicationCheckIn,
    *,
    now: datetime,
    risk_level: RiskLevel,
    classification: str,
    reason: str,
    safety_message: str = "",
) -> dict[str, Any]:
    if checkin.id not in mission.evidence_ids:
        mission.evidence_ids.append(checkin.id)
    mission.status = MissionStatus.WAITING_PROFESSIONAL
    mission.risk_level = risk_level
    mission.updated_at = now
    mission.next_action = (
        "The medication check-in was captured, but HealthIA will not close this mission automatically. "
        "Human clinical or pharmacy review is required before the workflow can be released."
    )
    content = (
        f"I recorded your check-in for {plan.name}. {safety_message + ' ' if safety_message else ''}"
        "I am keeping this mission open for human review. HealthIA did not advise a replacement, extra, reduced, skipped, or stopped dose, "
        "and it did not change your treatment."
    )
    state.messages.append(
        ChatMessage(
            patient_id=state.profile.id,
            role="assistant",
            author="HealthIA Safety",
            content=content,
            risk_level=risk_level,
            mission_id=mission.id,
            metadata={
                "medication_followup_handoff": True,
                "medication_id": plan.id,
                "evidence_id": checkin.id,
                "reason": reason,
                "requires_human_review": True,
                "dose_instruction_given": False,
                "treatment_changed": False,
            },
        )
    )
    receipt = audit(
        state,
        actor="healthia_medication_followup_guardian",
        action="handoff_medication_followup_to_human",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "medication_id": plan.id,
            "checkin_id": checkin.id,
            "reason": reason,
            "risk_level": risk_level.value,
            "dose_instruction_given": False,
            "adherence_claimed": False,
            "clinical_resolution_claimed": False,
            "treatment_changed": False,
        },
    )
    if receipt.id not in mission.closure_evidence:
        mission.closure_evidence.append(receipt.id)
    assessment = _assessment(
        observation_id=checkin.id,
        medication_id=plan.id,
        classification=classification,
        risk_level=risk_level,
        summary="A medication check-in was captured but requires human review before workflow closure.",
        provenance=[plan.id, checkin.id, receipt.id],
    )
    event_id = _stage(state, mission, assessment, event_kind="human_handoff", medication_id=plan.id)
    return {
        "status": "review_handoff",
        "mission_id": mission.id,
        "checkin_id": checkin.id,
        "risk_level": risk_level.value,
        "reason": reason,
        "receipt_id": receipt.id,
        "event_id": event_id,
        "human_release_required": True,
    }


def _reconcile_checkin(
    state: PatientState,
    mission: HealthMission,
    plan: MedicationPlan,
    checkin: MedicationCheckIn,
    *,
    now: datetime,
) -> dict[str, Any]:
    if mission.status == MissionStatus.WAITING_PROFESSIONAL:
        return _append_human_gate_evidence(state, mission, checkin, now=now)

    safety = assess_text(checkin.note)
    if safety.must_stop_normal_flow:
        return _handoff(
            state,
            mission,
            plan,
            checkin,
            now=now,
            risk_level=RiskLevel.URGENT,
            classification="medication_followup_safety_handoff",
            reason="urgent_language",
            safety_message=safety.message,
        )

    if medication_action_or_error_context(checkin.note):
        return _handoff(
            state,
            mission,
            plan,
            checkin,
            now=now,
            risk_level=RiskLevel.WATCH,
            classification="medication_followup_review_handoff",
            reason="dose_change_or_medication_error_context",
        )

    if medication_adverse_context(checkin.note):
        return _handoff(
            state,
            mission,
            plan,
            checkin,
            now=now,
            risk_level=RiskLevel.WATCH,
            classification="medication_followup_review_handoff",
            reason="adverse_effect_context",
        )

    if checkin.id not in mission.evidence_ids:
        mission.evidence_ids.append(checkin.id)

    if checkin.status == "unknown":
        mission.status = MissionStatus.WAITING_PATIENT
        mission.updated_at = now
        mission.next_action = (
            f"The check-in for {plan.name} was recorded as unknown. The mission stays open until a taken, late, or skipped status is explicitly recorded."
        )
        receipt = audit(
            state,
            actor="healthia_medication_followup_guardian",
            action="keep_medication_followup_waiting_unknown",
            resource_type="health_mission",
            resource_id=mission.id,
            details={
                "medication_id": plan.id,
                "checkin_id": checkin.id,
                "status": checkin.status,
                "dose_instruction_given": False,
                "adherence_claimed": False,
                "treatment_changed": False,
            },
        )
        return {
            "status": "waiting",
            "mission_id": mission.id,
            "checkin_id": checkin.id,
            "receipt_id": receipt.id,
        }

    mission.status = MissionStatus.COMPLETED
    mission.risk_level = RiskLevel.INFO
    mission.updated_at = now
    mission.next_action = (
        "Check-in capture completed. This closes only the continuity task; it does not establish adherence, medication effectiveness, or treatment safety."
    )
    receipt = audit(
        state,
        actor="healthia_medication_followup_guardian",
        action="resolve_medication_followup_checkin_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "medication_id": plan.id,
            "checkin_id": checkin.id,
            "reported_status": checkin.status,
            "resolution": "medication_checkin_recorded",
            "dose_instruction_given": False,
            "compensation_advice_given": False,
            "adherence_claimed": False,
            "clinical_resolution_claimed": False,
            "treatment_changed": False,
        },
    )
    mission.closure_evidence = list(
        dict.fromkeys([*mission.closure_evidence, "medication_checkin_recorded", receipt.id])
    )
    status_copy = {
        "taken": "taken",
        "late": "late",
        "skipped": "skipped",
    }.get(checkin.status, "recorded")
    state.messages.append(
        ChatMessage(
            patient_id=state.profile.id,
            role="assistant",
            author="HealthIA Guardian",
            content=(
                f"I recorded your {plan.name} check-in as {status_copy} and closed the check-in capture mission. "
                "This is a record of what you reported, not a judgment of adherence or medication effectiveness. "
                + (
                    "Because you reported it as skipped, HealthIA is not telling you to compensate, double, or change a later dose. "
                    if checkin.status == "skipped"
                    else ""
                )
                + "No treatment was changed."
            ),
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            metadata={
                "autonomous_medication_followup": True,
                "medication_followup_resolved": True,
                "medication_id": plan.id,
                "evidence_id": checkin.id,
                "reported_status": checkin.status,
                "resolution_receipt_id": receipt.id,
                "dose_instruction_given": False,
                "compensation_advice_given": False,
                "adherence_claimed": False,
                "treatment_changed": False,
            },
        )
    )
    assessment = _assessment(
        observation_id=checkin.id,
        medication_id=plan.id,
        classification="medication_followup_checkin_resolved",
        risk_level=RiskLevel.INFO,
        summary="A new explicit medication check-in satisfied the evidence-capture mission.",
        provenance=[plan.id, checkin.id, receipt.id],
    )
    event_id = _stage(state, mission, assessment, event_kind="resolved", medication_id=plan.id)
    return {
        "status": "completed",
        "mission_id": mission.id,
        "checkin_id": checkin.id,
        "reported_status": checkin.status,
        "receipt_id": receipt.id,
        "event_id": event_id,
    }


def reconcile_medication_followup_guardian(
    state: PatientState,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Maintain medication check-in continuity without prescribing or inferring adherence."""
    current = now or utc_now()
    report: dict[str, Any] = {
        "created": [],
        "waiting": [],
        "completed": [],
        "review_handoff": [],
    }

    for plan in _active_plans(state):
        if not _authorized(state, plan.id):
            continue
        mission = _open_mission(state, plan.id)
        if mission is not None:
            checkin = _new_checkin_after_mission(state, mission, plan.id)
            if checkin is None:
                report["waiting"].append(
                    {"status": "waiting", "mission_id": mission.id, "medication_id": plan.id}
                )
                continue
            outcome = _reconcile_checkin(state, mission, plan, checkin, now=current)
            bucket = {
                "completed": "completed",
                "review_handoff": "review_handoff",
                "waiting": "waiting",
            }[outcome["status"]]
            report[bucket].append(outcome)
            continue

        due, latest = _due_plan(state, plan, now=current)
        if due and latest is not None:
            report["created"].append(_open_due_mission(state, plan, latest, now=current))

    return report
