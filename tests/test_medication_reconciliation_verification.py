from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from healthia_one.config import Settings
from healthia_one.fcm_device_api import build_fcm_device_router
from healthia_one.medication_followup_guardian import (
    CONSENT_SIGNAL,
    FOLLOWUP_DUE_HOURS,
    MISSION_TYPE as FOLLOWUP_MISSION_TYPE,
    reconcile_medication_followup_guardian,
)
from healthia_one.medication_reconciliation import (
    MISSION_TYPE,
    record_medication_reconciliation_response,
    reconcile_medication_reconciliation,
)
from healthia_one.medication_review_release import reconcile_medication_review_release
from healthia_one.mission_evidence_api import mission_tag
from healthia_one.models import (
    ClinicalDocument,
    DocumentCategory,
    HealthMission,
    MedicationCheckIn,
    MedicationPlan,
    MissionStatus,
    PatientState,
    RiskLevel,
)
from healthia_one.service import HealthIAService
from healthia_one.store import MemoryStore


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _authorized_state() -> tuple[PatientState, MedicationPlan]:
    state = PatientState()
    if CONSENT_SIGNAL not in state.consent.signal_types:
        state.consent.signal_types.append(CONSENT_SIGNAL)
    plan = MedicationPlan(
        name="Losartán",
        generic_name="losartan",
        strength="50 mg",
        dose_value=50,
        dose_unit="mg",
        route="oral",
        schedule="cada 24 horas",
        frequency_times_per_day=1,
        instructions="Seguir el esquema indicado por el profesional.",
        verification_status="professional_confirmed",
        active=True,
    )
    state.medication_plans.append(plan)
    return state, plan


def _followup_mission(state: PatientState, medication_id: str) -> HealthMission:
    return next(
        mission
        for mission in state.missions
        if mission.mission_type == f"{FOLLOWUP_MISSION_TYPE}:{medication_id}"
    )


def _reconciliation_mission(state: PatientState, medication_id: str) -> HealthMission:
    return next(
        mission
        for mission in state.missions
        if mission.mission_type.startswith(f"{MISSION_TYPE}:{medication_id}:")
    )


def _build_documented_review_state() -> tuple[PatientState, MedicationPlan, ClinicalDocument]:
    state, plan = _authorized_state()
    state.medication_checkins.append(
        MedicationCheckIn(
            medication_id=plan.id,
            recorded_at=NOW - timedelta(hours=FOLLOWUP_DUE_HOURS + 12),
            status="taken",
        )
    )
    reconcile_medication_followup_guardian(state, now=NOW)
    followup = _followup_mission(state, plan.id)
    state.medication_checkins.append(
        MedicationCheckIn(
            medication_id=plan.id,
            recorded_at=NOW + timedelta(minutes=5),
            status="late",
            note="Llegué tarde. ¿Puedo duplicar la dosis ahora?",
        )
    )
    reconcile_medication_followup_guardian(state, now=NOW + timedelta(minutes=5))
    assert followup.status == MissionStatus.WAITING_PROFESSIONAL
    handoff = next(
        event
        for event in state.audit_events
        if event.action == "handoff_medication_followup_to_human"
        and event.resource_id == followup.id
    )
    document = ClinicalDocument(
        title="Human medication review",
        filename="medication-review.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff.created_at + timedelta(seconds=1),
        tags=[mission_tag(followup.id)],
    )
    state.documents.append(document)
    release = reconcile_medication_review_release(
        state,
        now=handoff.created_at + timedelta(seconds=2),
    )
    assert release["completed"]
    assert followup.status == MissionStatus.COMPLETED
    return state, plan, document


def _service_with_state(state: PatientState, *, autonomous_enabled: bool = True) -> HealthIAService:
    service = HealthIAService(
        Settings(
            store_backend="memory",
            llm_backend="mock",
            proactive_enabled=autonomous_enabled,
        )
    )
    service.store = MemoryStore(state, autonomous_enabled=autonomous_enabled)
    return service


def test_documented_review_opens_one_reconciliation_for_exact_record_snapshot() -> None:
    state, plan, document = _build_documented_review_state()
    before = plan.model_dump(mode="json")

    first = reconcile_medication_reconciliation(state, now=NOW + timedelta(minutes=10))
    second = reconcile_medication_reconciliation(state, now=NOW + timedelta(minutes=11))

    assert len(first["created"]) == 1
    assert not second["created"]
    mission = _reconciliation_mission(state, plan.id)
    assert mission.status == MissionStatus.WAITING_PATIENT
    assert document.id in mission.evidence_ids
    opening = next(
        event
        for event in state.audit_events
        if event.action == "open_medication_reconciliation_verification"
        and event.resource_id == mission.id
    )
    assert opening.id in mission.evidence_ids
    assert opening.details["medication_id"] == plan.id
    assert opening.details["document_regimen_extracted"] is False
    assert opening.details["dose_instruction_given"] is False
    assert opening.details["medication_plan_changed"] is False
    assert plan.model_dump(mode="json") == before
    message = next(
        item
        for item in state.messages
        if item.mission_id == mission.id and item.metadata.get("medication_reconciliation")
    )
    assert "currently has this record" in message.content
    assert "does not authorize HealthIA to change your medication or dose" in message.content
    assert message.metadata["choices"] == ["unchanged", "changed", "unsure"]


def test_reconciliation_does_not_open_without_current_medication_followup_consent() -> None:
    state, plan, _ = _build_documented_review_state()
    state.consent.signal_types = [signal for signal in state.consent.signal_types if signal != CONSENT_SIGNAL]

    report = reconcile_medication_reconciliation(state, now=NOW + timedelta(minutes=10))

    assert not report["created"]
    assert not [m for m in state.missions if m.mission_type.startswith(f"{MISSION_TYPE}:{plan.id}:")]


@pytest.mark.asyncio
async def test_unchanged_closes_only_reconciliation_and_keeps_medication_plan_exact() -> None:
    state, plan, _ = _build_documented_review_state()
    reconcile_medication_reconciliation(state, now=NOW + timedelta(minutes=10))
    mission = _reconciliation_mission(state, plan.id)
    before = plan.model_dump(mode="json")
    service = _service_with_state(state)

    saved_mission = await record_medication_reconciliation_response(
        service,
        mission_id=mission.id,
        choice="unchanged",
        note="Sí, eso es lo que tengo registrado.",
    )

    saved = await service.snapshot()
    saved_plan = next(item for item in saved.medication_plans if item.id == plan.id)
    assert saved_mission.status == MissionStatus.COMPLETED
    assert "patient_confirmed_record_unchanged" in saved_mission.closure_evidence
    assert saved_plan.model_dump(mode="json") == before
    receipt = next(
        event
        for event in saved.audit_events
        if event.action == "confirm_medication_record_unchanged"
        and event.resource_id == mission.id
    )
    assert receipt.details["patient_confirmed_record_freshness"] is True
    assert receipt.details["professional_verification_upgraded"] is False
    assert receipt.details["dose_instruction_given"] is False
    assert receipt.details["medication_plan_changed"] is False
    assert receipt.details["treatment_changed"] is False


@pytest.mark.asyncio
async def test_changed_becomes_sticky_professional_review_without_inferred_regimen() -> None:
    state, plan, _ = _build_documented_review_state()
    reconcile_medication_reconciliation(state, now=NOW + timedelta(minutes=10))
    mission = _reconciliation_mission(state, plan.id)
    before = plan.model_dump(mode="json")
    service = _service_with_state(state)

    changed = await record_medication_reconciliation_response(
        service,
        mission_id=mission.id,
        choice="changed",
        note="El médico me dijo que hubo un cambio.",
    )

    saved = await service.snapshot()
    saved_plan = next(item for item in saved.medication_plans if item.id == plan.id)
    assert changed.status == MissionStatus.WAITING_PROFESSIONAL
    assert changed.risk_level == RiskLevel.WATCH
    assert saved_plan.model_dump(mode="json") == before
    receipt = next(
        event
        for event in saved.audit_events
        if event.action == "report_medication_record_changed"
        and event.resource_id == mission.id
    )
    assert receipt.details["record_may_be_stale"] is True
    assert receipt.details["new_regimen_inferred"] is False
    assert receipt.details["medication_plan_changed"] is False

    with pytest.raises(ValueError, match="human-gated"):
        await record_medication_reconciliation_response(
            service,
            mission_id=mission.id,
            choice="unchanged",
        )


@pytest.mark.asyncio
async def test_unsure_keeps_mission_open_and_can_later_confirm_same_snapshot() -> None:
    state, plan, _ = _build_documented_review_state()
    reconcile_medication_reconciliation(state, now=NOW + timedelta(minutes=10))
    mission = _reconciliation_mission(state, plan.id)
    before = plan.model_dump(mode="json")
    service = _service_with_state(state)

    unsure = await record_medication_reconciliation_response(
        service,
        mission_id=mission.id,
        choice="unsure",
        note="Lo voy a confirmar con la farmacia.",
    )
    assert unsure.status == MissionStatus.WAITING_PATIENT

    unchanged = await record_medication_reconciliation_response(
        service,
        mission_id=mission.id,
        choice="unchanged",
        note="Ya lo confirmé.",
    )
    saved = await service.snapshot()
    saved_plan = next(item for item in saved.medication_plans if item.id == plan.id)
    assert unchanged.status == MissionStatus.COMPLETED
    assert saved_plan.model_dump(mode="json") == before


@pytest.mark.asyncio
async def test_plan_drift_after_open_fails_closed_before_patient_answer() -> None:
    state, plan, _ = _build_documented_review_state()
    reconcile_medication_reconciliation(state, now=NOW + timedelta(minutes=10))
    mission = _reconciliation_mission(state, plan.id)
    plan.strength = "25 mg"
    service = _service_with_state(state, autonomous_enabled=False)

    with pytest.raises(ValueError, match="changed since reconciliation opened"):
        await record_medication_reconciliation_response(
            service,
            mission_id=mission.id,
            choice="unchanged",
        )

    saved = await service.snapshot()
    saved_mission = _reconciliation_mission(saved, plan.id)
    assert saved_mission.status == MissionStatus.WAITING_PATIENT
    assert next(item for item in saved.medication_plans if item.id == plan.id).strength == "25 mg"


@pytest.mark.asyncio
async def test_manual_answer_remains_available_if_runtime_is_disabled_after_mission_opened() -> None:
    state, plan, _ = _build_documented_review_state()
    reconcile_medication_reconciliation(state, now=NOW + timedelta(minutes=10))
    mission = _reconciliation_mission(state, plan.id)
    before = plan.model_dump(mode="json")
    service = _service_with_state(state, autonomous_enabled=False)

    result = await record_medication_reconciliation_response(
        service,
        mission_id=mission.id,
        choice="unchanged",
    )

    saved = await service.snapshot()
    assert result.status == MissionStatus.COMPLETED
    assert next(item for item in saved.medication_plans if item.id == plan.id).model_dump(mode="json") == before


@pytest.mark.asyncio
async def test_runtime_off_blocks_automatic_reconciliation_opening() -> None:
    state, plan, _ = _build_documented_review_state()
    service = _service_with_state(state, autonomous_enabled=False)

    await service.store.save(state)
    saved = await service.snapshot()

    assert not [m for m in saved.missions if m.mission_type.startswith(f"{MISSION_TYPE}:{plan.id}:")]


@pytest.mark.asyncio
async def test_wrong_mission_type_is_rejected_without_state_mutation() -> None:
    state, plan = _authorized_state()
    other = HealthMission(
        title="Other mission",
        mission_type="other",
        status=MissionStatus.WAITING_PATIENT,
        next_action="Wait",
    )
    state.missions.append(other)
    before = plan.model_dump(mode="json")
    service = _service_with_state(state, autonomous_enabled=False)

    with pytest.raises(ValueError, match="not a medication reconciliation"):
        await record_medication_reconciliation_response(
            service,
            mission_id=other.id,
            choice="unchanged",
        )

    saved = await service.snapshot()
    assert next(item for item in saved.medication_plans if item.id == plan.id).model_dump(mode="json") == before


def test_http_reconciliation_route_is_real_and_fcm_surface_is_preserved() -> None:
    state, plan, _ = _build_documented_review_state()
    reconcile_medication_reconciliation(state, now=NOW + timedelta(minutes=10))
    mission = _reconciliation_mission(state, plan.id)
    service = _service_with_state(state, autonomous_enabled=False)
    app = FastAPI()
    app.include_router(build_fcm_device_router(service, service.settings))

    with TestClient(app) as client:
        reconciliation_response = client.post(
            f"/api/missions/{mission.id}/medication-reconciliation",
            json={"choice": "unchanged", "note": "Confirmed"},
        )
        fcm_response = client.post(
            "/api/devices/fcm/register",
            json={
                "device_id": "android-test-device",
                "registration_token": "fcm-registration-token-1234567890",
            },
        )

    assert reconciliation_response.status_code == 200
    body = reconciliation_response.json()
    assert body["recorded"] is True
    assert body["mission"]["status"] == "completed"
    assert "does not infer or apply" in body["truth_boundary"]
    assert fcm_response.status_code == 401
    assert "dispositivo" in fcm_response.json()["detail"].lower()
