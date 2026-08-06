from healthia_one.models import VitalRecord
from healthia_one.safety import assess_text, assess_vital


def test_urgent_text_stops_normal_flow():
    decision = assess_text("Tengo dolor fuerte en el pecho y no puedo respirar")
    assert decision.must_stop_normal_flow is True
    assert decision.level == "urgent"


def test_routine_text_does_not_trigger_urgent_path():
    decision = assess_text("Quiero entender mis resultados")
    assert decision.must_stop_normal_flow is False


def test_low_oxygen_is_urgent():
    decision = assess_vital(VitalRecord(oxygen_saturation=87))
    assert decision.level == "urgent"
