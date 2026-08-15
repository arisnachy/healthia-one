from __future__ import annotations

import pytest

from healthia_one.config import Settings
from healthia_one.control import audit
from healthia_one.medication_reconciliation import (
    OPEN_AUDIT_ACTION,
    _mission_type,
    _plan_hash,
    record_medication_reconciliation_response,
)
from healthia_one.models import HealthMission, MedicationPlan, MissionStatus, PatientState, RiskLevel
from healthia_one.service import HealthIAService
from healthia_one.store import MemoryStore


def _service_with_open_reconciliation() -> tuple[HealthIAService, MedicationPlan, HealthMission]:
    state = PatientState()
    plan = MedicationPlan(
        name="Losartán",
        strength="50 mg",
        dose_value=50,
        dose_unit="mg",
        route="oral",
        schedule="cada 24 horas",
        verification_status="professional_confirmed",
    )
    state.medication_plans.append(plan)
    release_receipt_id = "audit_release_test"
    mission = HealthMission(
        title="Confirm current medication record",
        mission_type=_mission_type(plan.id, release_receipt_id),
        status=MissionStatus.WAITING_PATIENT,
        next_action="Confirm unchanged, changed, or unsure.",
    )
    state.missions.append(mission)
    audit(
        state,
        actor="healthia_medication_reconciliation",
        action=OPEN_AUDIT_ACTION,
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "medication_id": plan.id,
            "source_release_receipt_id": release_receipt_id,
            "plan_snapshot_hash": _plan_hash(plan),
        },
    )
    service = HealthIAService(
        Settings(store_backend="memory", llm_backend="mock", proactive_enabled=False)
    )
    service.store = MemoryStore(state, autonomous_enabled=False)
    return service, plan, mission


@pytest.mark.asyncio
async def test_urgent_free_text_overrides_unchanged_choice_and_never_mutates_plan() -> None:
    service, plan, mission = _service_with_open_reconciliation()
    before = plan.model_dump(mode="json")

    result = await record_medication_reconciliation_response(
        service,
        mission_id=mission.id,
        choice="unchanged",
        note="Sigue igual, pero ahora tengo dolor fuerte en el pecho.",
    )

    saved = await service.snapshot()
    saved_plan = next(item for item in saved.medication_plans if item.id == plan.id)
    assert result.status == MissionStatus.WAITING_PROFESSIONAL
    assert result.risk_level == RiskLevel.URGENT
    assert saved_plan.model_dump(mode="json") == before
    receipt = next(
        event
        for event in saved.audit_events
        if event.action == "handoff_medication_reconciliation_response"
        and event.resource_id == mission.id
    )
    assert receipt.details["structured_choice"] == "unchanged"
    assert receipt.details["structured_choice_overridden_by_safety"] is True
    assert receipt.details["reason"] == "urgent_language"
    assert receipt.details["medication_plan_changed"] is False
    assert receipt.details["treatment_changed"] is False


@pytest.mark.asyncio
async def test_double_dose_context_overrides_unchanged_choice_and_stays_human_gated() -> None:
    service, plan, mission = _service_with_open_reconciliation()
    before = plan.model_dump(mode="json")

    result = await record_medication_reconciliation_response(
        service,
        mission_id=mission.id,
        choice="unchanged",
        note="Sí, sigue igual, pero hoy tomé doble dosis por error.",
    )

    saved = await service.snapshot()
    saved_plan = next(item for item in saved.medication_plans if item.id == plan.id)
    assert result.status == MissionStatus.WAITING_PROFESSIONAL
    assert result.risk_level == RiskLevel.WATCH
    assert saved_plan.model_dump(mode="json") == before
    receipt = next(
        event
        for event in saved.audit_events
        if event.action == "handoff_medication_reconciliation_response"
        and event.resource_id == mission.id
    )
    assert receipt.details["structured_choice_overridden_by_safety"] is True
    assert receipt.details["reason"] == "dose_change_or_medication_error_context"
    assert receipt.details["new_regimen_inferred"] is False
    assert receipt.details["dose_instruction_given"] is False

    with pytest.raises(ValueError, match="human-gated"):
        await record_medication_reconciliation_response(
            service,
            mission_id=mission.id,
            choice="unchanged",
            note="Ahora estoy bien.",
        )
