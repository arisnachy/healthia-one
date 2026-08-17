from datetime import datetime, timedelta, timezone

from healthia_one.continuity import (
    build_timeline,
    condition_pack_summary,
    consultation_brief,
    evaluate_continuity,
    medication_summary,
)
from healthia_one.models import Appointment, MedicationCheckIn
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


def test_unified_timeline_contains_multiple_patient_domains():
    state = seed_state()
    event_types = {item["type"] for item in build_timeline(state)}
    assert {"vital", "weight", "activity", "medication", "appointment"}.issubset(event_types)


def test_timeline_exposes_english_copy_without_removing_spanish_contract():
    state = seed_state()
    events = build_timeline(state)
    vital = next(item for item in events if item["type"] == "vital")
    weight = next(item for item in events if item["type"] == "weight")
    activity = next(item for item in events if item["type"] == "activity")
    assert vital["title"].startswith("Presión ") and vital["title_en"].startswith("Blood pressure ")
    assert weight["title"].startswith("Peso ") and weight["title_en"].startswith("Weight ")
    assert "pasos" in activity["title"] and "steps" in activity["title_en"]

    packs = condition_pack_summary(state)
    assert packs and packs[0]["label"] and packs[0]["label_en"]


def test_consultation_brief_connects_patient_context():
    brief = consultation_brief(seed_state())
    assert brief["appointment"] is not None
    assert brief["active_medications"]
    assert brief["latest_vital"] is not None
    assert brief["family_context"]
    assert brief["questions"]
    assert "revisado" in brief["truth_boundary"].lower()


def test_condition_packs_are_patient_specific():
    packs = condition_pack_summary(seed_state())
    keys = {item["key"] for item in packs}
    assert keys == {"hypertension", "weight_management"}


def test_upcoming_appointment_creates_preparation_finding():
    state = seed_state()
    findings = evaluate_continuity(state)
    assert any(item.key.startswith("appointment_prep:") for item in findings)
    assert any(step.agent == "ADVOCATE" for item in findings for step in item.agent_plan)


def test_skipped_dose_never_recommends_compensation():
    state = seed_state()
    state.medication_checkins.append(
        MedicationCheckIn(medication_id=state.medication_plans[0].id, status="skipped")
    )
    findings = evaluate_continuity(state)
    medication = next(item for item in findings if item.key.startswith("medication_skipped:"))
    assert "no indica duplicar" in medication.why_it_matters.lower()


def test_chat_routes_treatment_consultation_and_timeline():
    state = seed_state()
    treatment = respond(state, "Muéstrame mi tratamiento y las tomas")
    consultation = respond(state, "Prepara mi próxima consulta médica")
    timeline = respond(state, "Enséñame mi línea de tiempo de salud")
    assert treatment.mission.mission_type == "medication_management"
    assert consultation.mission.mission_type == "consultation_preparation"
    assert timeline.mission.mission_type == "timeline_review"
    assert treatment.message.metadata["action_target"] == "treatment"


def test_medication_summary_is_explicitly_patient_reported():
    summary = medication_summary(seed_state())
    assert summary["reported_adherence_percent"] == 100.0
    assert "informado" in summary["truth_boundary"].lower()
