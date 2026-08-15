from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from healthia_one.config import Settings
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import plan_guardian_notification
from healthia_one.models import (
    Appointment,
    ClinicalDocument,
    DocumentCategory,
    MissionStatus,
    PatientState,
)
from healthia_one.postvisit_guardian import MISSION_TYPE, reconcile_postvisit_guardian
from healthia_one.service import HealthIAService
from healthia_one.store import MemoryStore


NOW = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)


def _completed_appointment(*, hours_ago: int = 2, title: str = "Family medicine follow-up") -> Appointment:
    return Appointment(
        title=title,
        specialty="Family medicine",
        scheduled_at=NOW - timedelta(hours=hours_ago),
        status="completed",
    )


def _mission(state: PatientState, appointment_id: str):
    return next(
        item
        for item in state.missions
        if item.mission_type == MISSION_TYPE and appointment_id in item.evidence_ids
    )


def _consult_document(*, uploaded_at: datetime, category: DocumentCategory = DocumentCategory.CONSULTATION) -> ClinicalDocument:
    return ClinicalDocument(
        title="Visit summary",
        filename="visit-summary.pdf",
        category=category,
        mime_type="application/pdf",
        uploaded_at=uploaded_at,
        status="parsed",
    )


def test_completed_appointment_opens_postvisit_capture_mission_without_inventing_visit_content() -> None:
    state = PatientState()
    appointment = _completed_appointment()
    state.appointments.append(appointment)

    report = reconcile_postvisit_guardian(state, now=NOW)

    mission = _mission(state, appointment.id)
    assert report["created"] and report["created"][0]["appointment_id"] == appointment.id
    assert mission.status == MissionStatus.WAITING_PATIENT
    assert appointment.id in mission.evidence_ids
    assert "consultation note or discharge summary" in mission.next_action
    message = next(item for item in state.messages if item.mission_id == mission.id)
    assert message.metadata["postvisit_summary_gap"] is True
    assert "will not invent what happened" in message.content
    intent = next(
        event
        for event in state.audit_events
        if event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("guardian_domain") == "postvisit_continuity"
    )
    payload = intent.details["event"]["payload"]
    assert payload["appointment_booked_or_changed"] is False
    assert payload["treatment_changed"] is False
    assert payload["diagnosis_claimed"] is False


def test_consultation_document_after_visit_closes_same_mission_with_receipt() -> None:
    state = PatientState()
    appointment = _completed_appointment()
    state.appointments.append(appointment)
    reconcile_postvisit_guardian(state, now=NOW)
    document = _consult_document(uploaded_at=NOW + timedelta(minutes=5))
    state.documents.append(document)

    report = reconcile_postvisit_guardian(state, now=NOW + timedelta(minutes=5))

    mission = _mission(state, appointment.id)
    assert report["completed"] and report["completed"][0]["mission_id"] == mission.id
    assert mission.status == MissionStatus.COMPLETED
    assert document.id in mission.evidence_ids
    assert "postvisit_document_present_unambiguous" in mission.closure_evidence
    receipt_id = next(item for item in mission.closure_evidence if item.startswith("audit_"))
    receipt = next(item for item in state.audit_events if item.id == receipt_id)
    assert receipt.action == "resolve_postvisit_summary_mission"
    assert receipt.details["resolution"] == "postvisit_document_present_unambiguous"
    assert receipt.details["diagnosis_claimed"] is False
    assert receipt.details["treatment_changed"] is False


def test_unrelated_document_category_cannot_close_postvisit_mission() -> None:
    state = PatientState()
    appointment = _completed_appointment()
    state.appointments.append(appointment)
    reconcile_postvisit_guardian(state, now=NOW)
    state.documents.append(
        _consult_document(uploaded_at=NOW + timedelta(minutes=5), category=DocumentCategory.INSURANCE)
    )

    report = reconcile_postvisit_guardian(state, now=NOW + timedelta(minutes=5))

    assert not report["completed"]
    assert _mission(state, appointment.id).status == MissionStatus.WAITING_PATIENT


def test_document_uploaded_before_visit_cannot_close_postvisit_mission() -> None:
    state = PatientState()
    appointment = _completed_appointment(hours_ago=2)
    state.appointments.append(appointment)
    state.documents.append(_consult_document(uploaded_at=appointment.scheduled_at - timedelta(minutes=1)))

    reconcile_postvisit_guardian(state, now=NOW)

    assert _mission(state, appointment.id).status == MissionStatus.WAITING_PATIENT


def test_one_unlinked_document_cannot_be_silently_assigned_between_two_completed_visits() -> None:
    state = PatientState()
    first = _completed_appointment(hours_ago=4, title="Family medicine")
    second = _completed_appointment(hours_ago=2, title="Cardiology")
    state.appointments.extend([first, second])
    reconcile_postvisit_guardian(state, now=NOW)
    state.documents.append(_consult_document(uploaded_at=NOW + timedelta(minutes=5)))

    report = reconcile_postvisit_guardian(state, now=NOW + timedelta(minutes=5))

    assert not report["completed"]
    assert _mission(state, first.id).status == MissionStatus.WAITING_PATIENT
    assert _mission(state, second.id).status == MissionStatus.WAITING_PATIENT


def test_existing_unambiguous_postvisit_evidence_prevents_unnecessary_mission() -> None:
    state = PatientState()
    appointment = _completed_appointment()
    state.appointments.append(appointment)
    document = _consult_document(uploaded_at=NOW - timedelta(hours=1))
    state.documents.append(document)

    report = reconcile_postvisit_guardian(state, now=NOW)

    assert not report["created"]
    assert report["waiting"][0]["status"] == "evidence_already_present"
    assert not [item for item in state.missions if item.mission_type == MISSION_TYPE]


def test_postvisit_guardian_email_copy_is_evidence_only_and_non_mutating() -> None:
    state = PatientState()
    state.profile.email = "ana@example.com"
    state.consent.signal_types.extend(["guardian_email", "guardian_email_auto_send"])
    gap = GuardianAssessment(
        observation_id="appt_1",
        metric="postvisit_continuity",
        classification="postvisit_summary_gap",
        summary="Post-visit evidence missing",
        notify_patient=True,
    )
    resolved = gap.model_copy(
        update={
            "classification": "postvisit_summary_resolved",
            "summary": "Post-visit evidence captured",
        }
    )

    gap_plan = plan_guardian_notification(state, gap, mission_id="mission_postvisit")
    resolved_plan = plan_guardian_notification(state, resolved, mission_id="mission_postvisit")

    assert gap_plan.email is not None and resolved_plan.email is not None
    assert gap_plan.email.delivery_mode == "eligible_auto_send"
    assert "not guessing what happened" in gap_plan.email.body
    assert "document capture only" in resolved_plan.email.body
    assert gap_plan.email.changes_treatment is False
    assert gap_plan.email.diagnostic_claim is False
    assert gap_plan.email.contains_precise_location is False


@pytest.mark.asyncio
async def test_service_upserts_same_appointment_then_closes_postvisit_mission_when_document_arrives() -> None:
    state = PatientState()
    service = HealthIAService(
        Settings(
            store_backend="memory",
            llm_backend="mock",
            proactive_enabled=True,
        )
    )
    service.store = MemoryStore(state, autonomous_enabled=True)
    appointment = Appointment(
        title="Longitudinal visit",
        specialty="Family medicine",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status="scheduled",
    )

    await service.add_appointment(appointment)
    initial = await service.snapshot()
    assert len(initial.appointments) == 1
    assert not [item for item in initial.missions if item.mission_type == MISSION_TYPE]

    completed = appointment.model_copy(update={"status": "completed"})
    await service.add_appointment(completed)
    after_completion = await service.snapshot()
    assert len(after_completion.appointments) == 1
    assert after_completion.appointments[0].id == appointment.id
    assert after_completion.appointments[0].status == "completed"
    mission = _mission(after_completion, appointment.id)
    assert mission.status == MissionStatus.WAITING_PATIENT

    document = ClinicalDocument(
        title="Consultation note",
        filename="consultation-note.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        status="parsed",
    )
    await service.add_document(document)

    final = await service.snapshot()
    mission = _mission(final, appointment.id)
    assert mission.status == MissionStatus.COMPLETED
    assert document.id in mission.evidence_ids
    receipt_id = next(item for item in mission.closure_evidence if item.startswith("audit_"))
    receipt = next(item for item in final.audit_events if item.id == receipt_id)
    assert receipt.details["resolution"] == "postvisit_document_present_unambiguous"
    assert any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("postvisit_guardian_event") == "resolved"
        and event.details.get("status") == "emitted"
        for event in final.audit_events
    )


@pytest.mark.asyncio
async def test_runtime_kill_switch_blocks_postvisit_guardian_even_with_patient_consent() -> None:
    service = HealthIAService(
        Settings(
            store_backend="memory",
            llm_backend="mock",
            proactive_enabled=False,
        )
    )
    initial = await service.snapshot()
    initial_message_count = len(initial.messages)
    appointment = Appointment(
        title="Completed visit while runtime autonomy is off",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status="completed",
    )

    await service.add_appointment(appointment)
    saved = await service.snapshot()

    assert saved.consent.proactive_enabled is True
    assert service.settings.proactive_enabled is False
    assert len(saved.messages) == initial_message_count
    assert not [item for item in saved.missions if item.mission_type == MISSION_TYPE]
