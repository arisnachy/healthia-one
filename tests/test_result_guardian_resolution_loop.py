from __future__ import annotations

from datetime import timedelta

from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import plan_guardian_notification
from healthia_one.models import ClinicalDocument, HealthResult, MissionStatus, ResultItem
from healthia_one.result_guardian import MISSION_TYPE, reconcile_result_guardian
from healthia_one.service import seed_state


def _lab(filename: str, *items: ResultItem) -> tuple[HealthResult, ClinicalDocument]:
    result = HealthResult(
        filename=filename,
        panel="Laboratorio sintético",
        status="parsed",
        explained=True,
        items=list(items),
    )
    document = ClinicalDocument(
        patient_id="patient_demo",
        title=f"Evidence {filename}",
        filename=filename,
        mime_type="application/json",
        storage_path=f"uploads/patient_demo/{filename}",
        status="parsed",
        related_result_id=result.id,
    )
    return result, document


def _append_new(state, result: HealthResult, document: ClinicalDocument) -> None:
    # Result Guardian uses the previous durable state timestamp as its change
    # boundary. Make that relationship explicit in this unit-level fixture.
    result.uploaded_at = state.updated_at + timedelta(seconds=1)
    document.uploaded_at = result.uploaded_at
    state.results.append(result)
    state.documents.append(document)


def _mission(state):
    return next(item for item in state.missions if item.mission_type == MISSION_TYPE)


def test_new_partial_lab_opens_durable_followup_without_changing_treatment() -> None:
    state = seed_state()
    before = [plan.model_dump(mode="json") for plan in state.medication_plans]
    result, document = _lab(
        "chemistry-partial.json",
        ResultItem(name="Sodium", value=139, unit="mmol/L"),
    )
    _append_new(state, result, document)

    report = reconcile_result_guardian(state)

    mission = _mission(state)
    assert report["opened"] and report["opened"][0]["status"] == "created"
    assert mission.status == MissionStatus.WAITING_PATIENT
    assert result.id in mission.evidence_ids
    assert "renal" in mission.next_action.lower()
    assert "potassium" in mission.next_action.lower()
    assert [plan.model_dump(mode="json") for plan in state.medication_plans] == before
    assert any(
        message.metadata.get("autonomous_result_guardian")
        and message.metadata.get("monitoring_context_gap")
        and message.mission_id == mission.id
        for message in state.messages
    )
    assert any(
        event.action == "autopilot_event_intent"
        and event.details.get("payload", {}).get("guardian_domain") == "clinical_result"
        and event.details.get("payload", {}).get("mission_id") == mission.id
        for event in state.audit_events
    )


def test_same_result_cannot_create_duplicate_guardian_mission() -> None:
    state = seed_state()
    result, document = _lab("chemistry-partial.json", ResultItem(name="Sodium", value=139))
    _append_new(state, result, document)

    reconcile_result_guardian(state)
    # Simulate the successful durable commit. The same result is now historical.
    state.updated_at = result.uploaded_at + timedelta(seconds=1)
    reconcile_result_guardian(state)

    missions = [item for item in state.missions if item.mission_type == MISSION_TYPE]
    assert len(missions) == 1


def test_second_result_closes_open_mission_only_when_required_evidence_is_present() -> None:
    state = seed_state()
    first, first_document = _lab(
        "renal-partial.json",
        ResultItem(name="Creatinina", value=0.9, unit="mg/dL"),
    )
    _append_new(state, first, first_document)
    reconcile_result_guardian(state)
    mission = _mission(state)
    assert mission.status == MissionStatus.WAITING_PATIENT
    assert "potassium" in mission.next_action.lower()

    state.updated_at = first.uploaded_at + timedelta(seconds=2)
    second, second_document = _lab(
        "electrolytes.json",
        ResultItem(name="Potasio", value=4.2, unit="mmol/L"),
    )
    _append_new(state, second, second_document)

    report = reconcile_result_guardian(state)

    mission = _mission(state)
    assert report["resolved"] and report["resolved"][0]["status"] == "completed"
    assert mission.status == MissionStatus.COMPLETED
    assert first.id in mission.evidence_ids
    assert second.id in mission.evidence_ids
    assert first_document.id in mission.evidence_ids
    assert second_document.id in mission.evidence_ids
    assert "renal_function_evidence_present" in mission.closure_evidence
    assert "potassium_evidence_present" in mission.closure_evidence
    receipt_ids = [item for item in mission.closure_evidence if item.startswith("audit_")]
    assert len(receipt_ids) == 1
    receipt = next(event for event in state.audit_events if event.id == receipt_ids[0])
    assert receipt.action == "resolve_monitoring_context_mission"
    assert receipt.details["resolution"] == "required_evidence_present"
    assert receipt.details["treatment_changed"] is False
    assert any(
        message.metadata.get("mission_resolved")
        and message.metadata.get("resolution_receipt_id") == receipt.id
        for message in state.messages
    )


def test_unrelated_followup_result_does_not_falsely_close_mission() -> None:
    state = seed_state()
    first, first_document = _lab(
        "renal-partial.json",
        ResultItem(name="Creatinine", value=0.9, unit="mg/dL"),
    )
    _append_new(state, first, first_document)
    reconcile_result_guardian(state)
    state.updated_at = first.uploaded_at + timedelta(seconds=2)

    unrelated, unrelated_document = _lab(
        "cbc.json",
        ResultItem(name="Hemoglobin", value=13.8, unit="g/dL"),
    )
    _append_new(state, unrelated, unrelated_document)
    report = reconcile_result_guardian(state)

    mission = _mission(state)
    assert not report["resolved"]
    assert mission.status == MissionStatus.WAITING_PATIENT
    assert "potassium" in mission.next_action.lower()


def test_complete_lab_does_not_open_an_unnecessary_mission() -> None:
    state = seed_state()
    result, document = _lab(
        "complete-monitoring-context.json",
        ResultItem(name="Creatinine", value=0.9, unit="mg/dL"),
        ResultItem(name="Potassium", value=4.2, unit="mmol/L"),
    )
    _append_new(state, result, document)

    report = reconcile_result_guardian(state)

    assert not report["opened"]
    assert not [item for item in state.missions if item.mission_type == MISSION_TYPE]


def test_result_guardian_email_copy_matches_gap_and_resolution_without_diagnosis() -> None:
    state = seed_state()
    state.profile.email = "ana@example.com"
    state.consent.signal_types.extend(["guardian_email", "guardian_email_auto_send"])

    gap = GuardianAssessment(
        observation_id="result_gap",
        metric="clinical_result",
        classification="result_monitoring_context_gap",
        summary="Monitoring context gap",
        notify_patient=True,
    )
    resolved = gap.model_copy(
        update={
            "observation_id": "result_resolved",
            "classification": "result_monitoring_context_resolved",
            "summary": "Monitoring context resolved",
        }
    )

    gap_plan = plan_guardian_notification(state, gap, mission_id="mission_gap")
    resolved_plan = plan_guardian_notification(state, resolved, mission_id="mission_gap")

    assert gap_plan.email is not None and resolved_plan.email is not None
    assert gap_plan.email.delivery_mode == "eligible_auto_send"
    assert "not a diagnosis" in gap_plan.email.body
    assert "No medication or treatment was changed" in resolved_plan.email.body
    assert "closed" in resolved_plan.email.subject.lower()
