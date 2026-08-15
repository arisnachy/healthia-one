from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from healthia_one.config import Settings
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import plan_guardian_notification
from healthia_one.medication_followup_guardian import (
    CONSENT_SIGNAL,
    FOLLOWUP_DUE_HOURS,
    MISSION_TYPE,
    reconcile_medication_followup_guardian,
)
from healthia_one.medication_review_release import reconcile_medication_review_release
from healthia_one.mission_evidence_api import link_document_to_mission, linked_to_mission, mission_tag
from healthia_one.models import (
    ClinicalDocument,
    DocumentCategory,
    MedicationCheckIn,
    MedicationPlan,
    MissionStatus,
    PatientState,
)
from healthia_one.service import HealthIAService
from healthia_one.store import MemoryStore


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _build_handoff_state() -> tuple[PatientState, MedicationPlan]:
    state = PatientState()
    if CONSENT_SIGNAL not in state.consent.signal_types:
        state.consent.signal_types.append(CONSENT_SIGNAL)
    plan = MedicationPlan(
        name="Losartán",
        strength="50 mg",
        dose_value=50,
        dose_unit="mg",
        schedule="cada 24 horas",
        frequency_times_per_day=1,
        instructions="Seguir únicamente el esquema indicado por el profesional.",
        verification_status="professional_confirmed",
    )
    state.medication_plans.append(plan)
    state.medication_checkins.append(
        MedicationCheckIn(
            medication_id=plan.id,
            recorded_at=NOW - timedelta(hours=FOLLOWUP_DUE_HOURS + 12),
            status="taken",
        )
    )
    reconcile_medication_followup_guardian(state, now=NOW)
    mission = _mission(state, plan.id)
    checkin = MedicationCheckIn(
        medication_id=plan.id,
        recorded_at=NOW + timedelta(minutes=5),
        status="late",
        note="Llegué tarde. ¿Puedo duplicar la dosis ahora?",
    )
    state.medication_checkins.append(checkin)
    reconcile_medication_followup_guardian(state, now=NOW + timedelta(minutes=5))
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    return state, plan


def _mission(state: PatientState, medication_id: str):
    return next(
        item
        for item in state.missions
        if item.mission_type == f"{MISSION_TYPE}:{medication_id}"
    )


def _handoff_at(state: PatientState, mission_id: str) -> datetime:
    return next(
        event.created_at
        for event in state.audit_events
        if event.action == "handoff_medication_followup_to_human"
        and event.resource_id == mission_id
    )


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
async def test_unlinked_post_handoff_document_cannot_release_medication_mission() -> None:
    state, plan = _build_handoff_state()
    mission = _mission(state, plan.id)
    handoff_at = _handoff_at(state, mission.id)
    document = ClinicalDocument(
        title="Human review note",
        filename="review.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff_at + timedelta(seconds=1),
    )
    state.documents.append(document)

    report = reconcile_medication_review_release(state, now=handoff_at + timedelta(seconds=2))

    assert not report["completed"]
    assert report["waiting"]
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert document.id not in mission.evidence_ids


@pytest.mark.asyncio
async def test_prescription_document_can_be_linked_but_cannot_release_review_gate() -> None:
    state, plan = _build_handoff_state()
    mission = _mission(state, plan.id)
    handoff_at = _handoff_at(state, mission.id)
    document = ClinicalDocument(
        title="Prescription",
        filename="prescription.pdf",
        category=DocumentCategory.PRESCRIPTION,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff_at + timedelta(seconds=1),
    )
    state.documents.append(document)
    service = _service_with_state(state)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)

    saved = await service.snapshot()
    saved_mission = _mission(saved, plan.id)
    saved_document = next(item for item in saved.documents if item.id == document.id)
    assert linked_to_mission(saved_document, mission.id) is True
    assert saved_mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert document.id not in saved_mission.evidence_ids


@pytest.mark.asyncio
async def test_pre_handoff_consultation_document_cannot_release_medication_mission() -> None:
    state, plan = _build_handoff_state()
    mission = _mission(state, plan.id)
    handoff_at = _handoff_at(state, mission.id)
    document = ClinicalDocument(
        title="Older consultation",
        filename="older-consultation.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff_at - timedelta(seconds=1),
    )
    state.documents.append(document)
    service = _service_with_state(state)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)

    saved = await service.snapshot()
    saved_mission = _mission(saved, plan.id)
    assert saved_mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert "documented_human_review_evidence_linked" not in saved_mission.closure_evidence


@pytest.mark.parametrize("category", [DocumentCategory.CONSULTATION, DocumentCategory.DISCHARGE])
@pytest.mark.asyncio
async def test_explicit_post_handoff_review_document_closes_workflow_without_changing_medication_plan(
    category: DocumentCategory,
) -> None:
    state, plan = _build_handoff_state()
    mission = _mission(state, plan.id)
    plan_before = plan.model_dump(mode="json")
    handoff_at = _handoff_at(state, mission.id)
    document = ClinicalDocument(
        title="Documented human review",
        filename="human-review.pdf",
        category=category,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff_at + timedelta(seconds=1),
    )
    state.documents.append(document)
    service = _service_with_state(state)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)

    saved = await service.snapshot()
    saved_mission = _mission(saved, plan.id)
    saved_plan = next(item for item in saved.medication_plans if item.id == plan.id)
    assert saved_mission.status == MissionStatus.COMPLETED
    assert document.id in saved_mission.evidence_ids
    assert "documented_human_review_evidence_linked" in saved_mission.closure_evidence
    assert saved_plan.model_dump(mode="json") == plan_before

    receipt = next(
        event
        for event in saved.audit_events
        if event.action == "resolve_medication_followup_after_documented_review"
        and event.resource_id == mission.id
    )
    assert receipt.details["explicit_patient_link_required"] is True
    assert receipt.details["professional_authorship_verified"] is False
    assert receipt.details["clinical_content_validated"] is False
    assert receipt.details["dose_instruction_given"] is False
    assert receipt.details["medication_plan_changed"] is False
    assert receipt.details["clinical_resolution_claimed"] is False
    assert receipt.details["treatment_changed"] is False

    message = next(
        item
        for item in reversed(saved.messages)
        if item.metadata.get("medication_followup_human_review_documented")
    )
    assert message.metadata["dose_instruction_given"] is False
    assert message.metadata["medication_plan_changed"] is False
    assert message.metadata["clinical_resolution_claimed"] is False
    assert "did not interpret the document as a new dose or medication order" in message.content

    assert any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("medication_followup_event") == "human_review_documented"
        and event.details.get("event", {}).get("payload", {}).get("medication_plan_changed") is False
        and event.details.get("status") == "emitted"
        for event in saved.audit_events
    )


@pytest.mark.asyncio
async def test_runtime_kill_switch_allows_explicit_link_but_blocks_automatic_medication_release() -> None:
    state, plan = _build_handoff_state()
    mission = _mission(state, plan.id)
    handoff_at = _handoff_at(state, mission.id)
    state.audit_events = [event for event in state.audit_events if event.action != "autopilot_event_intent"]
    document = ClinicalDocument(
        title="Human review note",
        filename="review.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
        uploaded_at=handoff_at + timedelta(seconds=1),
    )
    state.documents.append(document)
    service = _service_with_state(state, autonomous_enabled=False)

    await link_document_to_mission(service, document_id=document.id, mission_id=mission.id)

    saved = await service.snapshot()
    saved_mission = _mission(saved, plan.id)
    saved_document = next(item for item in saved.documents if item.id == document.id)
    assert mission_tag(mission.id) in saved_document.tags
    assert saved_mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert not any(
        event.action == "resolve_medication_followup_after_documented_review"
        for event in saved.audit_events
    )
    assert not any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("medication_followup_event") == "human_review_documented"
        for event in saved.audit_events
    )


def test_documented_medication_review_notification_preserves_truth_boundary() -> None:
    state = PatientState()
    state.profile.email = "ana@example.com"
    state.consent.signal_types.extend(["guardian_email", "guardian_email_auto_send"])
    assessment = GuardianAssessment(
        observation_id="doc_review",
        metric="medication_followup",
        classification="medication_followup_human_review_documented",
        summary="Documented medication review evidence captured",
        notify_patient=True,
    )

    plan = plan_guardian_notification(state, assessment, mission_id="mission_med")

    assert plan.email is not None
    assert plan.email.delivery_mode == "eligible_auto_send"
    assert "did not independently verify professional authorship or clinical content" in plan.email.body
    assert "did not interpret the document as a new dose or medication order" in plan.email.body
    assert "does not claim that the medication issue is clinically resolved" in plan.email.body
    assert "did not change treatment" in plan.email.body
    assert plan.email.changes_treatment is False
    assert plan.email.diagnostic_claim is False
