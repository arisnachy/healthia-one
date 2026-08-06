from datetime import datetime, timezone

from healthia_one.models import PatientState, VitalRecord, WeightRecord
from healthia_one.proactive import evaluate_state
from healthia_one.service import seed_state


def test_seed_detects_weight_change_and_low_activity():
    findings = evaluate_state(seed_state())
    keys = {item.key.split(":")[0] for item in findings}
    assert "weight_gain" in keys
    assert "low_activity" in keys
    assert "missing_bp" in keys


def test_extreme_blood_pressure_becomes_priority():
    state = PatientState()
    state.vitals = [VitalRecord(systolic=186, diastolic=122, pulse=90)]
    state.weights = [WeightRecord(weight_kg=70)]
    findings = evaluate_state(state)
    alert = next(item for item in findings if item.key.startswith("vital_alert"))
    assert alert.risk_level in {"priority", "urgent"}
    assert "umbral determinista" in alert.why_it_matters


def test_missing_weight_is_explainable():
    state = PatientState()
    state.vitals = [VitalRecord(measured_at=datetime.now(timezone.utc), systolic=130, diastolic=80)]
    findings = evaluate_state(state)
    finding = next(item for item in findings if item.key.startswith("missing_weight"))
    assert "No veo" in finding.summary
    assert finding.next_action
    assert finding.agent_plan
