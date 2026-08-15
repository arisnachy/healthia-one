from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from healthia_one.appointment_guardian import (
    MISSION_TYPE,
    appointment_guardian_due,
    appointment_preparation_snapshot,
    reconcile_appointment_guardian,
)
from healthia_one.config import Settings
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import plan_guardian_notification
from healthia_one.models import (
    Appointment,
    ClinicalDocument,
    DocumentCategory,
    HealthResult,
    MedicationPlan,
    MissionStatus,
    PatientState,
    ResultItem,
)
from healthia_one.service import HealthIAService
from healthia_one.store import MemoryStore


NOW = datetime(2026, 8, 15, 16, 0, tzinfo=timezone.utc)


def _state_with_appointment(*, required: list[str], hours: int = 40) -> tuple[PatientState, Appointment]:
    state = PatientState()
    state.medication_plans = [
        MedicationPlan(
            name="Losartan",
            generic_name="losartan",
            strength="50 mg",
            schedule="daily",
            active=True,
            verification_status="patient_confirmed",
        )
    ]
    appointment = Appointment(
        title="Family medicine follow-up",
        specialty="Family medicine",
        scheduled_at=NOW + timedelta(hours=hours),
        required_documents=required,
    )
    state.appointments = [appointment]
    return state, appointment


def _mission(state: PatientState, appointment_id: str):
    return next(
        item
        for item in state.missions
        if item.mission_type == MISSION_TYPE and appointment_id in item.evidence_ids
    )


def _result_evidence(filename: str = "recent-lab.json") -> tuple[HealthResult, ClinicalDocument]:
    result = HealthResult(
        filename=filename,
        panel="Recent laboratory",
        uploaded_at=NOW,
        status="parsed",
        explained=True,
        items=[ResultItem(name="Sodium", value=139, unit="mmol/L")],
    )
    document = ClinicalDocument(
        title="Original recent laboratory",
        filename=filename,
        category=DocumentCategory.LABORATORY,
        mime_type="application/json",
        uploaded_at=NOW,
        status="parsed",
        related_result_id=result.id,
    )
    return result, document


def test_upcoming_appointment_opens_only_for_missing_verifiable_requirement() -> None:
    state, appointment = _state_with_appointment(required=["Resultados recientes", "Lista de medicamentos"])
    before_appointment = appointment.model_dump(mode="json")
    before_medications = [item.model_dump(mode="json") for item in state.medication_plans]

    report = reconcile_appointment_guardian(state, now=NOW)

    mission = _mission(state, appointment.id)
    assert report["created"] and report["created"][0]["appointment_id"] == appointment.id
    assert mission.status == MissionStatus.WAITING_PATIENT
    assert "Resultados recientes" in mission.next_action
    assert "Lista de medicamentos" not in mission.next_action
    assert appointment.model_dump(mode="json") == before_appointment
    assert [item.model_dump(mode="json") for item in state.medication_plans] == before_medications
    assert any(
        message.metadata.get("appointment_preparation_gap")
        and message.metadata.get("appointment_id") == appointment.id
        for message in state.messages
    )
    assert any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("guardian_domain") == "appointment_preparation"
        and event.details.get("event", {}).get("payload", {}).get("appointment_id") == appointment.id
        for event in state.audit_events
    )


def test_recent_result_arrival_closes_same_appointment_mission_with_receipt() -> None:
    state, appointment = _state_with_appointment(required=["Recent results", "Medication list"])
    reconcile_appointment_guardian(state, now=NOW)
    mission = _mission(state, appointment.id)
    assert mission.status == MissionStatus.WAITING_PATIENT

    result, document = _result_evidence()
    state.results.append(result)
    state.documents.append(document)
    report = reconcile_appointment_guardian(state, now=NOW + timedelta(hours=1))

    mission = _mission(state, appointment.id)
    assert report["completed"] and report["completed"][0]["mission_id"] == mission.id
    assert mission.status == MissionStatus.COMPLETED
    assert appointment.id in mission.evidence_ids
    assert result.id in mission.evidence_ids
    assert document.id in mission.evidence_ids
    assert "listed_appointment_requirements_verified" in mission.closure_evidence
    receipt_id = next(item for item in mission.closure_evidence if item.startswith("audit_"))
    receipt = next(item for item in state.audit_events if item.id == receipt_id)
    assert receipt.action == "resolve_appointment_preparation_mission"
    assert receipt.details["resolution"] == "listed_requirements_verified"
    assert receipt.details["appointment_booked_or_changed"] is False
    assert receipt.details["treatment_changed"] is False


def test_unknown_required_document_stays_open_until_exact_persisted_match_exists() -> None:
    state, appointment = _state_with_appointment(required=["Referral letter"])
    first = appointment_preparation_snapshot(state, appointment, now=NOW)
    assert first["ready"] is False
    assert first["checks"][0]["verification"] == "unverified_requirement"

    reconcile_appointment_guardian(state, now=NOW)
    mission = _mission(state, appointment.id)
    assert mission.status == MissionStatus.WAITING_PATIENT

    document = ClinicalDocument(
        title="Referral letter",
        filename="referral-letter.pdf",
        mime_type="application/pdf",
        uploaded_at=NOW,
        status="parsed",
    )
    state.documents.append(document)
    reconcile_appointment_guardian(state, now=NOW + timedelta(minutes=5))

    mission = _mission(state, appointment.id)
    assert mission.status == MissionStatus.COMPLETED
    assert document.id in mission.evidence_ids


def test_identity_and_insurance_require_actual_categorized_documents() -> None:
    state, appointment = _state_with_appointment(required=["Documento de identidad", "Seguro"])
    state.documents.append(
        ClinicalDocument(
            title="ID",
            filename="id.pdf",
            category=DocumentCategory.IDENTITY,
            mime_type="application/pdf",
            uploaded_at=NOW,
            status="parsed",
        )
    )
    snapshot = appointment_preparation_snapshot(state, appointment, now=NOW)
    assert snapshot["ready"] is False
    assert snapshot["missing_requirements"] == ["Seguro"]

    state.documents.append(
        ClinicalDocument(
            title="Insurance card",
            filename="insurance.pdf",
            category=DocumentCategory.INSURANCE,
            mime_type="application/pdf",
            uploaded_at=NOW,
            status="parsed",
        )
    )
    snapshot = appointment_preparation_snapshot(state, appointment, now=NOW)
    assert snapshot["ready"] is True
    assert snapshot["missing_requirements"] == []


def test_cancelled_appointment_cancels_open_preparation_mission_without_external_action() -> None:
    state, appointment = _state_with_appointment(required=["Recent results"])
    reconcile_appointment_guardian(state, now=NOW)
    mission = _mission(state, appointment.id)
    assert mission.status == MissionStatus.WAITING_PATIENT

    appointment.status = "cancelled"
    report = reconcile_appointment_guardian(state, now=NOW + timedelta(minutes=1))

    mission = _mission(state, appointment.id)
    assert report["cancelled"]
    assert mission.status == MissionStatus.CANCELLED
    assert "appointment_cancelled" in mission.closure_evidence
    assert not any(
        event.details.get("event", {}).get("payload", {}).get("appointment_guardian_event") == "resolved"
        for event in state.audit_events
    )


def test_far_future_appointment_is_not_due_for_autonomous_preparation() -> None:
    state, appointment = _state_with_appointment(required=["Recent results"], hours=120)
    assert appointment_guardian_due(state, now=NOW) is False
    report = reconcile_appointment_guardian(state, now=NOW)
    assert not report["created"]
    assert not state.missions


def test_appointment_guardian_notification_copy_is_non_clinical_and_non_mutating() -> None:
    state, _ = _state_with_appointment(required=["Recent results"])
    state.profile.email = "ana@example.com"
    state.consent.signal_types.extend(["guardian_email", "guardian_email_auto_send"])
    gap = GuardianAssessment(
        observation_id="appt_1",
        metric="appointment_preparation",
        classification="appointment_preparation_gap",
        summary="Preparation gap",
        notify_patient=True,
    )
    resolved = gap.model_copy(
        update={
            "classification": "appointment_preparation_resolved",
            "summary": "Preparation complete",
        }
    )

    gap_plan = plan_guardian_notification(state, gap, mission_id="mission_appt")
    resolved_plan = plan_guardian_notification(state, resolved, mission_id="mission_appt")

    assert gap_plan.email is not None and resolved_plan.email is not None
    assert gap_plan.email.delivery_mode == "eligible_auto_send"
    assert "did not book, cancel, or change" in gap_plan.email.body
    assert "No appointment, diagnosis, medication, or treatment was changed" in resolved_plan.email.body
    assert gap_plan.email.contains_precise_location is False
    assert gap_plan.email.changes_treatment is False
    assert gap_plan.email.diagnostic_claim is False


@pytest.mark.asyncio
async def test_service_path_opens_then_closes_appointment_preparation_mission() -> None:
    state = PatientState()
    state.medication_plans = [
        MedicationPlan(
            name="Losartan",
            generic_name="losartan",
            strength="50 mg",
            schedule="daily",
            active=True,
        )
    ]
    service = HealthIAService(
        Settings(
            store_backend="memory",
            llm_backend="mock",
            proactive_enabled=True,
            data_path=".healthia-one/test-appointment-guardian.json",
        )
    )
    service.store = MemoryStore(state, autonomous_enabled=service.settings.proactive_enabled)
    appointment = Appointment(
        title="Service integration appointment",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=36),
        required_documents=["Recent results", "Medication list"],
    )

    await service.add_appointment(appointment)
    after_appointment = await service.snapshot()
    mission = _mission(after_appointment, appointment.id)
    assert mission.status == MissionStatus.WAITING_PATIENT
    gap_intents = [
        event
        for event in after_appointment.audit_events
        if event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("appointment_id") == appointment.id
    ]
    assert gap_intents
    assert all(item.details["status"] == "emitted" for item in gap_intents)

    result = HealthResult(
        filename="service-recent.json",
        panel="Recent laboratory",
        status="parsed",
        explained=True,
        items=[ResultItem(name="Potassium", value=4.2, unit="mmol/L")],
    )
    document = ClinicalDocument(
        title="Original service result",
        filename="service-recent.json",
        category=DocumentCategory.LABORATORY,
        mime_type="application/json",
        status="parsed",
        related_result_id=result.id,
    )
    await service.add_result_evidence(result, document)

    after_result = await service.snapshot()
    mission = _mission(after_result, appointment.id)
    assert mission.status == MissionStatus.COMPLETED
    assert result.id in mission.evidence_ids
    assert document.id in mission.evidence_ids
    receipt_id = next(item for item in mission.closure_evidence if item.startswith("audit_"))
    receipt = next(item for item in after_result.audit_events if item.id == receipt_id)
    assert receipt.details["resolution"] == "listed_requirements_verified"
    assert receipt.details["appointment_booked_or_changed"] is False
