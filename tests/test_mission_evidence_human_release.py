from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI

from healthia_one.bp_followup_guardian import CONSENT_SIGNAL, MISSION_TYPE, reconcile_bp_followup_guardian
from healthia_one.config import Settings
from healthia_one.fcm_device_api import build_fcm_device_router
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import plan_guardian_notification
from healthia_one.mission_evidence_api import link_document_to_mission, linked_to_mission
from healthia_one.models import (
    ClinicalDocument,
    DocumentCategory,
    HealthMission,
    MissionStatus,
    PatientState,
    RiskLevel,
    VitalRecord,
)
from healthia_one.service import HealthIAService
from healthia_one.store import MemoryStore


def _authorized_state() -> PatientState:
    state = PatientState()
    if CONSENT_SIGNAL not in state.consent.signal_types:
        state.consent.signal_types.append(CONSENT_SIGNAL)
    state.profile.care_plan.blood_pressure_due_days = 3
    return state


def _build_safety_handoff_state() -> tuple[PatientState, HealthMission, VitalRecord]:
    now = datetime.now(timezone.utc)
    state = _authorized_state()
    state.vitals.append(
        VitalRecord(
            measured_at=now - timedelta(days=5),
            systolic=138,
            diastolic=86,
        )
    )
    reconcile_bp_followup_guardian(state, now=now)
    mission = next(item for item in state.missions if item.mission_type == MISSION_TYPE)
    high = VitalRecord(
        measured_at=now + timedelta(seconds=1),
        systolic=170,
        diastolic=105,
    )
    state.vitals.append(high)
    reconcile_bp_followup_guardian(state, now=now + timedelta(seconds=1))
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    return state, mission, high


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


@pytest.mark.asyncio
async def test_explicit_link_rejects_unknown_document_or_mission() -> None:
    state, mission, _ = _build_safety_handoff_state()
    service = _service_with_state(state)

    with pytest.raises(LookupError):
        await link_document_to_mission(service, document_id="doc_missing", mission_id=mission.id)

    document = ClinicalDocument(
        title="Review note",
        filename="review.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
    )
    await service.add_document(document)
    with pytest.raises(LookupError):
        await link_document_to_mission(service, document_id=document.id, mission_id="mission_missing")


@pytest.mark.asyncio
async def test_wrong_document_category_can_be_linked_but_cannot_release_safety_gate() -> None:
    state, mission, _ = _build_safety_handoff_state()
    service = _service_with_state(state)
    document = ClinicalDocument(
        title="Insurance card",
        filename="insurance.pdf",
        category=DocumentCategory.INSURANCE,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    await service.add_document(document)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)

    saved = await service.snapshot()
    saved_mission = next(item for item in saved.missions if item.id == mission.id)
    saved_document = next(item for item in saved.documents if item.id == document.id)
    assert linked_to_mission(saved_document, mission.id) is True
    assert saved_mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert document.id not in saved_mission.evidence_ids


@pytest.mark.asyncio
async def test_pre_handoff_consultation_document_cannot_release_safety_gate() -> None:
    state, mission, _ = _build_safety_handoff_state()
    handoff = next(
        event
        for event in state.audit_events
        if event.action == "handoff_bp_followup_to_safety" and event.resource_id == mission.id
    )
    document = ClinicalDocument(
        title="Old consultation note",
        filename="old-review.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff.created_at - timedelta(seconds=1),
    )
    state.documents.append(document)
    service = _service_with_state(state)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)

    saved = await service.snapshot()
    saved_mission = next(item for item in saved.missions if item.id == mission.id)
    assert saved_mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert "documented_human_review_evidence_linked" not in saved_mission.closure_evidence


@pytest.mark.asyncio
async def test_post_handoff_consultation_evidence_closes_workflow_without_clinical_resolution_claim() -> None:
    state, mission, high = _build_safety_handoff_state()
    handoff = next(
        event
        for event in state.audit_events
        if event.action == "handoff_bp_followup_to_safety" and event.resource_id == mission.id
    )
    document = ClinicalDocument(
        title="Human review note",
        filename="human-review.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff.created_at + timedelta(seconds=1),
    )
    state.documents.append(document)
    service = _service_with_state(state)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)

    saved = await service.snapshot()
    saved_mission = next(item for item in saved.missions if item.id == mission.id)
    assert saved_mission.status == MissionStatus.COMPLETED
    assert high.id in saved_mission.evidence_ids
    assert document.id in saved_mission.evidence_ids
    assert "documented_human_review_evidence_linked" in saved_mission.closure_evidence
    receipt_id = next(
        item
        for item in saved_mission.closure_evidence
        if item.startswith("audit_")
        and any(
            event.id == item and event.action == "resolve_bp_followup_after_documented_review"
            for event in saved.audit_events
        )
    )
    receipt = next(event for event in saved.audit_events if event.id == receipt_id)
    assert receipt.details["resolution"] == "documented_human_review_evidence_linked"
    assert receipt.details["explicit_patient_link_required"] is True
    assert receipt.details["professional_authorship_verified"] is False
    assert receipt.details["clinical_resolution_claimed"] is False
    assert receipt.details["treatment_changed"] is False
    assert any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("bp_followup_event") == "human_review_documented"
        and event.details.get("status") == "emitted"
        for event in saved.audit_events
    )
    message = next(
        item
        for item in reversed(saved.messages)
        if item.metadata.get("bp_followup_human_review_documented")
    )
    assert message.metadata["clinical_resolution_claimed"] is False
    assert "not declaring the clinical situation resolved" in message.content


@pytest.mark.asyncio
async def test_discharge_document_can_satisfy_same_human_review_evidence_contract() -> None:
    state, mission, _ = _build_safety_handoff_state()
    handoff = next(
        event
        for event in state.audit_events
        if event.action == "handoff_bp_followup_to_safety" and event.resource_id == mission.id
    )
    document = ClinicalDocument(
        title="Discharge summary",
        filename="discharge.pdf",
        category=DocumentCategory.DISCHARGE,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff.created_at + timedelta(seconds=1),
    )
    state.documents.append(document)
    service = _service_with_state(state)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)

    saved = await service.snapshot()
    saved_mission = next(item for item in saved.missions if item.id == mission.id)
    assert saved_mission.status == MissionStatus.COMPLETED
    assert document.id in saved_mission.evidence_ids


@pytest.mark.asyncio
async def test_one_document_cannot_be_reassigned_to_a_second_open_mission() -> None:
    state, mission, _ = _build_safety_handoff_state()
    second = HealthMission(
        title="Other open mission",
        mission_type="other",
        status=MissionStatus.WAITING_PATIENT,
    )
    state.missions.append(second)
    document = ClinicalDocument(
        title="Review note",
        filename="review.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    state.documents.append(document)
    service = _service_with_state(state, autonomous_enabled=False)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)
    with pytest.raises(ValueError, match="already linked"):
        await link_document_to_mission(service, document_id=document.id, mission_id=second.id)


@pytest.mark.asyncio
async def test_runtime_kill_switch_allows_explicit_link_but_blocks_automatic_release() -> None:
    state, mission, _ = _build_safety_handoff_state()
    handoff = next(
        event
        for event in state.audit_events
        if event.action == "handoff_bp_followup_to_safety" and event.resource_id == mission.id
    )
    # Remove prior staged intents from the fixture so this test observes only the
    # effects of the explicit link under the disabled runtime.
    state.audit_events = [event for event in state.audit_events if event.action != "autopilot_event_intent"]
    document = ClinicalDocument(
        title="Human review note",
        filename="human-review.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff.created_at + timedelta(seconds=1),
    )
    state.documents.append(document)
    service = _service_with_state(state, autonomous_enabled=False)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)

    saved = await service.snapshot()
    saved_mission = next(item for item in saved.missions if item.id == mission.id)
    saved_document = next(item for item in saved.documents if item.id == document.id)
    assert linked_to_mission(saved_document, mission.id) is True
    assert saved_mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert not any(
        event.action == "resolve_bp_followup_after_documented_review"
        for event in saved.audit_events
    )
    assert not any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("bp_followup_event") == "human_review_documented"
        for event in saved.audit_events
    )


def test_composed_app_router_exposes_mission_evidence_paths_without_changing_fcm_paths() -> None:
    service = HealthIAService(Settings(store_backend="memory", llm_backend="mock"))
    app = FastAPI()
    app.include_router(build_fcm_device_router(service, service.settings))
    paths = {route.path for route in app.routes}

    assert "/api/missions/{mission_id}/evidence/documents/{document_id}" in paths
    assert "/api/missions/{mission_id}/evidence" in paths
    assert "/api/devices/fcm/register" in paths
    assert "/api/devices/fcm/ack" in paths


def test_documented_human_review_email_copy_preserves_truth_boundary() -> None:
    state = _authorized_state()
    state.profile.email = "ana@example.com"
    state.consent.signal_types.extend(["guardian_email", "guardian_email_auto_send"])
    assessment = GuardianAssessment(
        observation_id="bp_high",
        metric="blood_pressure_followup",
        classification="bp_followup_human_review_documented",
        summary="Human review evidence linked",
        notify_patient=True,
    )

    plan = plan_guardian_notification(state, assessment, mission_id="mission_bp")

    assert plan.email is not None
    assert plan.email.delivery_mode == "eligible_auto_send"
    assert "did not independently verify professional authorship" in plan.email.body
    assert "does not claim that your blood pressure or the clinical situation is resolved" in plan.email.body
    assert "did not change treatment" in plan.email.body
    assert plan.email.changes_treatment is False
    assert plan.email.diagnostic_claim is False
