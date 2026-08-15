from __future__ import annotations

import re
import unicodedata
from typing import Any

from healthia_one.autopilot_event_intents import stage_event_intent
from healthia_one.control import audit
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.models import (
    AgentStep,
    ChatMessage,
    HealthMission,
    HealthResult,
    MissionStatus,
    PatientState,
    RiskLevel,
)


MISSION_TYPE = "result_guardian_losartan_monitoring_context"
RULE_KEY = "result_guardian:losartan_monitoring_context"

# This rule intentionally checks only whether relevant evidence is visible in the
# patient's HealthIA record. It does not interpret the values, diagnose kidney
# disease, decide that therapy is unsafe, or recommend a medication change.
# Clinical basis: current losartan labeling advises monitoring renal function and
# serum potassium in susceptible patients. HealthIA turns a missing-record context
# gap into a patient-owned follow-up mission and closes it only when evidence is
# actually present.
RENAL_ALIASES = (
    "creatinina",
    "creatinine",
    "serum creatinine",
    "egfr",
    "estimated glomerular filtration rate",
    "glomerular filtration rate",
    "tfg",
    "tasa de filtracion glomerular",
)
POTASSIUM_ALIASES = (
    "potasio",
    "potassium",
    "serum potassium",
    "k+",
)
LOSARTAN_ALIASES = ("losartan", "losartan potassium", "losartan potasico")
LAB_HINTS = (
    "lab",
    "laboratorio",
    "laboratory",
    "analitica",
    "analytical",
    "quimica",
    "chemistry",
    "metabolic",
    "renal",
    "kidney",
)


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.casefold().replace("+", " plus ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _matches(value: Any, aliases: tuple[str, ...]) -> bool:
    haystack = f" {_normalize(value)} "
    return any(f" {_normalize(alias)} " in haystack for alias in aliases)


def _active_losartan(state: PatientState) -> bool:
    for plan in state.medication_plans:
        if not plan.active:
            continue
        material = " ".join((plan.name, plan.generic_name, plan.original_text))
        if _matches(material, LOSARTAN_ALIASES):
            return True
    return any(_matches(item, LOSARTAN_ALIASES) for item in state.profile.medications)


def _looks_laboratory(result: HealthResult) -> bool:
    material = f"{result.panel} {result.filename}"
    if any(hint in _normalize(material) for hint in LAB_HINTS):
        return True
    item_names = " ".join(item.name for item in result.items)
    return _matches(item_names, RENAL_ALIASES) or _matches(item_names, POTASSIUM_ALIASES)


def _evidence_groups(state: PatientState) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {"renal_function": [], "potassium": []}
    for result in state.results:
        if result.status != "parsed":
            continue
        for item in result.items:
            if _matches(item.name, RENAL_ALIASES) and result.id not in groups["renal_function"]:
                groups["renal_function"].append(result.id)
            if _matches(item.name, POTASSIUM_ALIASES) and result.id not in groups["potassium"]:
                groups["potassium"].append(result.id)
    return groups


def _missing_groups(groups: dict[str, list[str]]) -> list[str]:
    return [name for name in ("renal_function", "potassium") if not groups.get(name)]


def _document_ids_for_results(state: PatientState, result_ids: list[str]) -> list[str]:
    wanted = set(result_ids)
    return [document.id for document in state.documents if document.related_result_id in wanted]


def _open_mission(state: PatientState) -> HealthMission | None:
    return next(
        (
            mission
            for mission in state.missions
            if mission.mission_type == MISSION_TYPE
            and mission.status in {
                MissionStatus.ACTIVE,
                MissionStatus.WAITING_PATIENT,
                MissionStatus.WAITING_PROFESSIONAL,
            }
        ),
        None,
    )


def _event_assessment(
    *,
    result: HealthResult,
    classification: str,
    summary: str,
    risk_level: RiskLevel,
    missing: list[str],
    provenance: list[str],
) -> GuardianAssessment:
    return GuardianAssessment(
        observation_id=result.id,
        metric="clinical_result",
        classification=classification,
        risk_level=risk_level,
        summary=summary,
        observed={
            "result_id": result.id,
            "panel": result.panel,
            "filename": result.filename,
        },
        context={
            "registered_treatment": "losartan",
            "missing_evidence_groups": list(missing),
            "rule_key": RULE_KEY,
        },
        inference=(
            "HealthIA found a record-completeness gap relevant to the registered treatment. "
            "This does not establish harm, a diagnosis, or a need to change therapy."
            if classification == "result_monitoring_context_gap"
            else
            "The evidence requested by the open HealthIA mission is now present in the patient record."
        ),
        hypothesis=(
            "The patient may already have the missing laboratory evidence outside HealthIA; uploading or confirming it can resolve the gap."
            if classification == "result_monitoring_context_gap"
            else
            "No additional inference is required to close this evidence-completeness mission."
        ),
        confidence="high",
        notify_patient=True,
        requires_human_review=False,
        can_suppress_safety=False,
        provenance=list(dict.fromkeys(provenance)),
    )


def _stage_notification(
    state: PatientState,
    *,
    mission: HealthMission,
    assessment: GuardianAssessment,
    event_kind: str,
) -> str:
    event = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key=f"result_guardian|{event_kind}|{assessment.observation_id}|{mission.id}",
        payload={
            # Reuse the established Guardian patient-contact worker. The durable
            # assessment carries a result-specific classification, while the
            # existing push/Gmail authorization, receipt and dedupe boundaries
            # remain unchanged.
            "source": "guardian_context",
            "guardian_domain": "clinical_result",
            "mission_id": mission.id,
            "guardian_assessment": assessment.model_dump(mode="json"),
            "notification_requested": True,
            "result_guardian_event": event_kind,
            "treatment_changed": False,
            "diagnosis_claimed": False,
            "human_boundary": True,
        },
    )
    return event.id


def _close_if_resolved(state: PatientState, *, trigger_result: HealthResult | None) -> dict[str, Any] | None:
    mission = _open_mission(state)
    if mission is None:
        return None

    groups = _evidence_groups(state)
    missing = _missing_groups(groups)
    if missing:
        collected = list(dict.fromkeys(groups["renal_function"] + groups["potassium"]))
        for evidence_id in collected:
            if evidence_id not in mission.evidence_ids:
                mission.evidence_ids.append(evidence_id)
        labels = {
            "renal_function": "renal-function evidence",
            "potassium": "potassium evidence",
        }
        mission.next_action = "Still waiting for " + " and ".join(labels[item] for item in missing) + "."
        return {"status": "waiting", "mission_id": mission.id, "missing": missing}

    matched_result_ids = list(dict.fromkeys(groups["renal_function"] + groups["potassium"]))
    matched_document_ids = _document_ids_for_results(state, matched_result_ids)
    for evidence_id in [*matched_result_ids, *matched_document_ids]:
        if evidence_id not in mission.evidence_ids:
            mission.evidence_ids.append(evidence_id)

    mission.status = MissionStatus.COMPLETED
    mission.updated_at = state.updated_at
    mission.next_action = (
        "Mission closed automatically: the record now contains renal-function and potassium evidence. "
        "No medication or treatment was changed."
    )
    receipt = audit(
        state,
        actor="healthia_result_guardian",
        action="resolve_monitoring_context_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "rule_key": RULE_KEY,
            "matched_result_ids": matched_result_ids,
            "matched_document_ids": matched_document_ids,
            "diagnosis_claimed": False,
            "treatment_changed": False,
            "resolution": "required_evidence_present",
        },
    )
    mission.closure_evidence = list(
        dict.fromkeys([
            *mission.closure_evidence,
            "renal_function_evidence_present",
            "potassium_evidence_present",
            receipt.id,
        ])
    )
    state.messages.append(
        ChatMessage(
            patient_id=state.profile.id,
            role="assistant",
            author="HealthIA Guardian",
            content=(
                "I matched the new laboratory evidence to your open follow-up mission. "
                "The record now contains both renal-function and potassium evidence, so I closed that mission automatically. "
                "This is a continuity update, not a diagnosis, and I did not change your treatment."
            ),
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            metadata={
                "autonomous_result_guardian": True,
                "mission_resolved": True,
                "resolution_receipt_id": receipt.id,
                "treatment_changed": False,
            },
        )
    )

    source = trigger_result or next(
        (item for item in reversed(state.results) if item.id in matched_result_ids),
        state.results[-1] if state.results else None,
    )
    event_id = ""
    if source is not None:
        assessment = _event_assessment(
            result=source,
            classification="result_monitoring_context_resolved",
            summary="HealthIA received the evidence that an open monitoring-context mission was waiting for and closed the mission.",
            risk_level=RiskLevel.INFO,
            missing=[],
            provenance=[*matched_result_ids, *matched_document_ids, receipt.id],
        )
        event_id = _stage_notification(
            state,
            mission=mission,
            assessment=assessment,
            event_kind="resolved",
        )
    return {
        "status": "completed",
        "mission_id": mission.id,
        "receipt_id": receipt.id,
        "event_id": event_id,
        "matched_result_ids": matched_result_ids,
        "matched_document_ids": matched_document_ids,
    }


def _create_or_update_gap_mission(state: PatientState, result: HealthResult) -> dict[str, Any] | None:
    if not state.consent.proactive_enabled or "results" not in set(state.consent.signal_types):
        return None
    if any(RULE_KEY.startswith(prefix) for prefix in state.consent.muted_rule_prefixes):
        return None
    if not _active_losartan(state) or not _looks_laboratory(result):
        return None

    groups = _evidence_groups(state)
    missing = _missing_groups(groups)
    if not missing:
        return None

    mission = _open_mission(state)
    created = mission is None
    if mission is None:
        mission = HealthMission(
            patient_id=state.profile.id,
            title="Complete monitoring context for registered losartan treatment",
            mission_type=MISSION_TYPE,
            status=MissionStatus.WAITING_PATIENT,
            risk_level=RiskLevel.WATCH,
            next_action=(
                "Upload or confirm an existing laboratory result containing the missing renal-function and potassium evidence. "
                "If you do not have it, open HealthIA to plan the next safe step with a professional."
            ),
            evidence_ids=[result.id],
            agent_plan=[
                AgentStep(
                    agent="RESULT GUARDIAN",
                    action="Compare the new result with treatment-relevant evidence already visible in the record",
                    reason="Detect a missing monitoring-context gap without interpreting it as a diagnosis",
                    status="completed",
                ),
                AgentStep(
                    agent="HISTORIA",
                    action="Keep the evidence request attached to the longitudinal record",
                    reason="The mission should survive chat boundaries and future sessions",
                    status="completed",
                ),
                AgentStep(
                    agent="KIRA",
                    action="Wait for verifiable evidence and close only when it actually arrives",
                    reason="Do not claim resolution from a reminder, assumption, or treatment change",
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
                    "I stored your new laboratory result and checked it against the treatment context you authorized. "
                    "The HealthIA record still does not contain all of the renal-function and potassium evidence relevant to the registered losartan follow-up. "
                    "I opened a mission so this gap does not get lost. This is not a diagnosis, and I did not change your medication."
                ),
                risk_level=RiskLevel.WATCH,
                mission_id=mission.id,
                metadata={
                    "autonomous_result_guardian": True,
                    "monitoring_context_gap": True,
                    "missing_evidence_groups": missing,
                    "treatment_changed": False,
                },
            )
        )
    elif result.id not in mission.evidence_ids:
        mission.evidence_ids.append(result.id)

    mission.updated_at = state.updated_at
    assessment = _event_assessment(
        result=result,
        classification="result_monitoring_context_gap",
        summary=(
            "A newly stored laboratory result leaves an open monitoring-context gap: "
            + ", ".join(missing)
            + "."
        ),
        risk_level=RiskLevel.WATCH,
        missing=missing,
        provenance=[result.id, *_document_ids_for_results(state, [result.id])],
    )
    event_id = _stage_notification(
        state,
        mission=mission,
        assessment=assessment,
        event_kind="created" if created else "updated",
    )
    audit(
        state,
        actor="healthia_result_guardian",
        action="open_monitoring_context_mission" if created else "update_monitoring_context_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "rule_key": RULE_KEY,
            "trigger_result_id": result.id,
            "missing_evidence_groups": missing,
            "event_id": event_id,
            "diagnosis_claimed": False,
            "treatment_changed": False,
        },
    )
    return {
        "status": "created" if created else "updated",
        "mission_id": mission.id,
        "event_id": event_id,
        "missing": missing,
    }


def reconcile_result_guardian(state: PatientState) -> dict[str, Any]:
    """Reconcile new result evidence into one autonomous, evidence-closed mission.

    This is intentionally a pure PatientState mutation. It performs no network or
    provider mutation. The StateStore calls it before the canonical state commit;
    any staged notification intent therefore becomes visible to Eventarc only
    after the mission/context that caused it is durable.
    """
    report: dict[str, Any] = {
        "new_result_ids": [],
        "opened": [],
        "resolved": [],
    }

    # Resolve first. Arrival of the evidence requested by an existing mission
    # should close that mission rather than create another one.
    new_candidates = [
        result
        for result in state.results
        if result.status == "parsed" and result.uploaded_at > state.updated_at
    ]
    trigger = new_candidates[-1] if new_candidates else None
    resolution = _close_if_resolved(state, trigger_result=trigger)
    if resolution and resolution.get("status") == "completed":
        report["resolved"].append(resolution)

    for result in sorted(new_candidates, key=lambda item: item.uploaded_at):
        report["new_result_ids"].append(result.id)
        # A result that just completed the open mission must not also create a new
        # copy of the same gap mission.
        if resolution and resolution.get("status") == "completed":
            audit(
                state,
                actor="healthia_result_guardian",
                action="assess_result_for_autonomous_followup",
                resource_type="results",
                resource_id=result.id,
                details={"outcome": "resolved_existing_mission", "rule_key": RULE_KEY},
            )
            continue
        opened = _create_or_update_gap_mission(state, result)
        audit(
            state,
            actor="healthia_result_guardian",
            action="assess_result_for_autonomous_followup",
            resource_type="results",
            resource_id=result.id,
            details={
                "outcome": opened["status"] if opened else "no_action",
                "rule_key": RULE_KEY,
                "treatment_changed": False,
            },
        )
        if opened:
            report["opened"].append(opened)

    return report
