from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from healthia_one.control import audit
from healthia_one.medication_followup_guardian import CONSENT_SIGNAL as MEDICATION_FOLLOWUP_CONSENT
from healthia_one.medication_followup_guardian import MISSION_TYPE as MEDICATION_FOLLOWUP_MISSION_TYPE
from healthia_one.models import AgentStep, ChatMessage, HealthMission, MissionStatus, PatientState, RiskLevel


MISSION_TYPE = "medication_reconciliation_verification"
SOURCE_RELEASE_ACTION = "resolve_medication_followup_after_documented_review"
OPEN_AUDIT_ACTION = "open_medication_reconciliation_verification"
CHOICE_UNCHANGED = "unchanged"
CHOICE_CHANGED = "changed"
CHOICE_UNSURE = "unsure"


class MedicationReconciliationRequest(BaseModel):
    choice: Literal["unchanged", "changed", "unsure"]
    note: str = Field(default="", max_length=500)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _plan_payload(plan) -> dict:
    """Canonical record snapshot; descriptive record data, never a dosing recommendation."""
    return plan.model_dump(mode="json")


def _plan_hash(plan) -> str:
    payload = json.dumps(_plan_payload(plan), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _mission_type(medication_id: str, release_receipt_id: str) -> str:
    return f"{MISSION_TYPE}:{medication_id}:{release_receipt_id}"


def _parse_mission_type(value: str) -> tuple[str, str] | None:
    prefix = f"{MISSION_TYPE}:"
    if not str(value).startswith(prefix):
        return None
    remainder = str(value)[len(prefix):]
    medication_id, separator, receipt_id = remainder.partition(":")
    if not separator or not medication_id or not receipt_id:
        return None
    return medication_id, receipt_id


def _authorized(state: PatientState) -> bool:
    signals = set(state.consent.signal_types)
    return (
        state.consent.proactive_enabled
        and "medications" in signals
        and MEDICATION_FOLLOWUP_CONSENT in signals
    )


def _source_mission(state: PatientState, mission_id: str):
    return next((mission for mission in state.missions if mission.id == mission_id), None)


def _plan(state: PatientState, medication_id: str):
    return next(
        (
            plan
            for plan in state.medication_plans
            if plan.id == medication_id and plan.patient_id == state.profile.id
        ),
        None,
    )


def _existing_mission(state: PatientState, medication_id: str, release_receipt_id: str):
    expected = _mission_type(medication_id, release_receipt_id)
    return next((mission for mission in state.missions if mission.mission_type == expected), None)


def _record_copy(plan) -> str:
    pieces = [plan.name]
    if plan.strength:
        pieces.append(plan.strength)
    if plan.route:
        pieces.append(f"route: {plan.route}")
    if plan.schedule:
        pieces.append(f"schedule on record: {plan.schedule}")
    if plan.instructions:
        pieces.append(f"recorded instructions: {plan.instructions}")
    return "; ".join(pieces)


def _open_reconciliation(
    state: PatientState,
    *,
    source_release,
    medication_id: str,
    document_ids: list[str],
    now: datetime,
) -> HealthMission | None:
    plan = _plan(state, medication_id)
    if plan is None:
        return None
    source = _source_mission(state, source_release.resource_id)
    if (
        source is None
        or source.patient_id != state.profile.id
        or not source.mission_type.startswith(f"{MEDICATION_FOLLOWUP_MISSION_TYPE}:")
        or source.status != MissionStatus.COMPLETED
    ):
        return None
    if _existing_mission(state, medication_id, source_release.id) is not None:
        return None

    snapshot_hash = _plan_hash(plan)
    evidence_ids = list(dict.fromkeys([*document_ids, source_release.id]))
    mission = HealthMission(
        patient_id=state.profile.id,
        title=f"Confirm current medication record: {plan.name}",
        mission_type=_mission_type(medication_id, source_release.id),
        status=MissionStatus.WAITING_PATIENT,
        risk_level=RiskLevel.INFO,
        created_at=now,
        updated_at=now,
        next_action=(
            "Confirm whether the medication record shown by HealthIA is unchanged, changed, or you are unsure. "
            "This verification does not authorize HealthIA to change a medication or dose."
        ),
        evidence_ids=evidence_ids,
        agent_plan=[
            AgentStep(
                agent="MEDSAFE",
                action="Freeze the current medication-record snapshot for reconciliation",
                reason="The patient must answer about the exact record version they can see",
                status="completed",
            ),
            AgentStep(
                agent="NAVIGATOR",
                action="Wait for an explicit unchanged, changed, or unsure response",
                reason="Do not infer regimen changes from a clinical document",
                status="running",
            ),
            AgentStep(
                agent="SENTINEL",
                action="Prevent automatic medication mutation",
                reason="Reconciliation verifies record freshness; it does not prescribe or execute treatment changes",
                status="running",
            ),
        ],
    )
    state.missions.append(mission)
    opening = audit(
        state,
        actor="healthia_medication_reconciliation",
        action=OPEN_AUDIT_ACTION,
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "medication_id": medication_id,
            "source_medication_mission_id": source.id,
            "source_release_receipt_id": source_release.id,
            "document_ids": document_ids,
            "plan_snapshot_hash": snapshot_hash,
            "plan_snapshot": _plan_payload(plan),
            "document_regimen_extracted": False,
            "dose_instruction_given": False,
            "medication_plan_changed": False,
            "treatment_changed": False,
        },
    )
    if opening.id not in mission.evidence_ids:
        mission.evidence_ids.append(opening.id)
    state.messages.append(
        ChatMessage(
            patient_id=state.profile.id,
            role="assistant",
            author="HealthIA Guardian",
            content=(
                "I captured documented human-review evidence, but I will not treat that document as a medication order. "
                f"For reconciliation only, HealthIA currently has this record: {_record_copy(plan)}. "
                "Is that record still unchanged, has it changed, or are you unsure? "
                "Your answer verifies whether the record may be stale; it does not authorize HealthIA to change your medication or dose."
            ),
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            metadata={
                "medication_reconciliation": True,
                "medication_id": medication_id,
                "source_release_receipt_id": source_release.id,
                "plan_snapshot_hash": snapshot_hash,
                "choices": [CHOICE_UNCHANGED, CHOICE_CHANGED, CHOICE_UNSURE],
                "document_regimen_extracted": False,
                "dose_instruction_given": False,
                "medication_plan_changed": False,
                "treatment_changed": False,
            },
        )
    )
    return mission


def reconcile_medication_reconciliation(
    state: PatientState,
    *,
    now: datetime | None = None,
) -> dict:
    """Open one verification mission per documented medication-review release."""
    report = {"created": [], "skipped": []}
    if not _authorized(state):
        return report
    current = now or utc_now()
    releases = [
        event
        for event in state.audit_events
        if event.action == SOURCE_RELEASE_ACTION and event.outcome == "success"
    ]
    for release in releases:
        medication_id = str(release.details.get("medication_id") or "").strip()
        document_ids_raw = release.details.get("document_ids") or []
        document_ids = [str(item) for item in document_ids_raw if str(item).strip()]
        if not medication_id:
            report["skipped"].append({"release_receipt_id": release.id, "reason": "missing_medication_id"})
            continue
        existing = _existing_mission(state, medication_id, release.id)
        if existing is not None:
            continue
        mission = _open_reconciliation(
            state,
            source_release=release,
            medication_id=medication_id,
            document_ids=document_ids,
            now=current,
        )
        if mission is None:
            report["skipped"].append({"release_receipt_id": release.id, "reason": "source_or_plan_not_verifiable"})
            continue
        report["created"].append(
            {
                "mission_id": mission.id,
                "medication_id": medication_id,
                "source_release_receipt_id": release.id,
            }
        )
    return report


def _opening_audit(state: PatientState, mission_id: str):
    return next(
        (
            event
            for event in reversed(state.audit_events)
            if event.action == OPEN_AUDIT_ACTION
            and event.resource_id == mission_id
            and event.outcome == "success"
        ),
        None,
    )


async def record_medication_reconciliation_response(
    service,
    *,
    mission_id: str,
    choice: Literal["unchanged", "changed", "unsure"],
    note: str = "",
):
    """Persist an explicit reconciliation answer without mutating MedicationPlan."""
    async with service._mutation_lock:
        state = await service.store.load()
        mission = next((item for item in state.missions if item.id == mission_id), None)
        if mission is None or mission.patient_id != state.profile.id:
            raise LookupError("Medication reconciliation mission not found for authenticated patient")
        parsed = _parse_mission_type(mission.mission_type)
        if parsed is None:
            raise ValueError("Mission is not a medication reconciliation verification mission")
        medication_id, source_release_receipt_id = parsed
        if mission.status in {MissionStatus.COMPLETED, MissionStatus.CANCELLED}:
            raise ValueError("Closed medication reconciliation missions cannot accept responses")
        if mission.status == MissionStatus.WAITING_PROFESSIONAL:
            raise ValueError("Medication reconciliation is human-gated and cannot be reversed by another patient response")

        plan = _plan(state, medication_id)
        if plan is None:
            raise ValueError("Medication record no longer exists; reconciliation cannot continue automatically")
        opening = _opening_audit(state, mission.id)
        if opening is None:
            raise ValueError("Medication reconciliation provenance is missing")
        expected_hash = str(opening.details.get("plan_snapshot_hash") or "")
        current_hash = _plan_hash(plan)
        if not expected_hash or current_hash != expected_hash:
            raise ValueError("Medication record changed since reconciliation opened; review the current record before responding")

        before = _plan_payload(plan)
        current = utc_now()
        response_note = str(note or "").strip()
        if choice == CHOICE_UNCHANGED:
            mission.status = MissionStatus.COMPLETED
            mission.risk_level = RiskLevel.INFO
            mission.updated_at = current
            mission.next_action = (
                "Reconciliation closed because the patient explicitly confirmed that the displayed medication record is unchanged. "
                "No medication field or dose was modified."
            )
            receipt = audit(
                state,
                actor="patient",
                action="confirm_medication_record_unchanged",
                resource_type="health_mission",
                resource_id=mission.id,
                details={
                    "medication_id": medication_id,
                    "source_release_receipt_id": source_release_receipt_id,
                    "choice": choice,
                    "note": response_note,
                    "plan_snapshot_hash": current_hash,
                    "patient_confirmed_record_freshness": True,
                    "professional_verification_upgraded": False,
                    "dose_instruction_given": False,
                    "medication_plan_changed": False,
                    "treatment_changed": False,
                },
            )
            mission.closure_evidence = list(
                dict.fromkeys([*mission.closure_evidence, "patient_confirmed_record_unchanged", receipt.id])
            )
            message = (
                "Recorded: you explicitly confirmed that the medication record shown by HealthIA is unchanged. "
                "I closed the reconciliation task only. I did not change the medication, dose, schedule, or verification status."
            )
        elif choice == CHOICE_CHANGED:
            mission.status = MissionStatus.WAITING_PROFESSIONAL
            mission.risk_level = RiskLevel.WATCH
            mission.updated_at = current
            mission.next_action = (
                "The patient reported that the medication record has changed. Keep the existing record visible as potentially stale until a verified regimen update is captured; do not infer the new drug, dose, schedule, or instructions."
            )
            receipt = audit(
                state,
                actor="patient",
                action="report_medication_record_changed",
                resource_type="health_mission",
                resource_id=mission.id,
                details={
                    "medication_id": medication_id,
                    "source_release_receipt_id": source_release_receipt_id,
                    "choice": choice,
                    "note": response_note,
                    "record_may_be_stale": True,
                    "new_regimen_inferred": False,
                    "dose_instruction_given": False,
                    "medication_plan_changed": False,
                    "treatment_changed": False,
                },
            )
            if receipt.id not in mission.closure_evidence:
                mission.closure_evidence.append(receipt.id)
            message = (
                "Recorded: you reported that this medication record has changed. I am keeping it in human review as potentially stale. "
                "HealthIA did not infer the new medication, dose, schedule, or instructions and did not change treatment."
            )
        else:
            mission.status = MissionStatus.WAITING_PATIENT
            mission.risk_level = RiskLevel.INFO
            mission.updated_at = current
            mission.next_action = (
                "The patient is unsure whether the displayed medication record is still current. Verify the regimen with a clinician, pharmacy, or trusted source and then return to this reconciliation task."
            )
            receipt = audit(
                state,
                actor="patient",
                action="report_medication_record_unsure",
                resource_type="health_mission",
                resource_id=mission.id,
                details={
                    "medication_id": medication_id,
                    "source_release_receipt_id": source_release_receipt_id,
                    "choice": choice,
                    "note": response_note,
                    "record_freshness_confirmed": False,
                    "new_regimen_inferred": False,
                    "dose_instruction_given": False,
                    "medication_plan_changed": False,
                    "treatment_changed": False,
                },
            )
            if receipt.id not in mission.closure_evidence:
                mission.closure_evidence.append(receipt.id)
            message = (
                "Recorded: you are unsure whether this medication record is still current. I will keep the reconciliation task open. "
                "HealthIA did not guess a new regimen and did not change treatment."
            )

        after = _plan_payload(plan)
        if after != before:
            raise RuntimeError("Medication reconciliation attempted to mutate MedicationPlan")
        state.messages.append(
            ChatMessage(
                patient_id=state.profile.id,
                role="assistant",
                author="HealthIA Guardian",
                content=message,
                risk_level=mission.risk_level,
                mission_id=mission.id,
                metadata={
                    "medication_reconciliation": True,
                    "medication_id": medication_id,
                    "choice": choice,
                    "response_receipt_id": receipt.id,
                    "new_regimen_inferred": False,
                    "dose_instruction_given": False,
                    "medication_plan_changed": False,
                    "treatment_changed": False,
                },
            )
        )
        await service.store.save(state)
        saved_mission = next(item for item in state.missions if item.id == mission.id)

    await service.broker.publish({"type": "state", "section": "missions"})
    await service.broker.publish({"type": "state", "section": "medications"})
    return saved_mission


def build_medication_reconciliation_router(service) -> APIRouter:
    router = APIRouter(prefix="/api/missions", tags=["missions"])

    @router.post("/{mission_id}/medication-reconciliation")
    async def medication_reconciliation_response(
        mission_id: str,
        payload: MedicationReconciliationRequest,
    ) -> dict:
        try:
            mission = await record_medication_reconciliation_response(
                service,
                mission_id=mission_id,
                choice=payload.choice,
                note=payload.note,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "recorded": True,
            "mission": mission.model_dump(mode="json"),
            "truth_boundary": (
                "This endpoint records the patient's reconciliation answer about the displayed medication record. "
                "It does not infer or apply a medication, dose, schedule, instruction, or treatment change."
            ),
        }

    return router
