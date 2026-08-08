from __future__ import annotations

from pathlib import Path

from healthia_one.language import bind_requested_locale, reset_requested_locale
from healthia_one.safety import assess_text


ROOT = Path(__file__).resolve().parents[1]


def test_urgent_safety_recognizes_english_before_any_model_call() -> None:
    token = bind_requested_locale("en-US")
    try:
        decision = assess_text("I have severe chest pain and I cannot breathe")
    finally:
        reset_requested_locale(token)
    assert decision.must_stop_normal_flow is True
    assert decision.level.value == "urgent"
    assert "immediate" in decision.message.lower() or "emergency" in decision.message.lower()


def test_urgent_safety_remains_spanish_for_spanish_patient_input() -> None:
    token = bind_requested_locale("es-DO")
    try:
        decision = assess_text("Tengo dolor fuerte en el pecho y no puedo respirar")
    finally:
        reset_requested_locale(token)
    assert decision.must_stop_normal_flow is True
    assert "atención inmediata" in decision.message.lower() or "emergencia" in decision.message.lower()


def test_english_intents_route_to_existing_verified_functions() -> None:
    source = (ROOT / "healthia_one" / "orchestrator.py").read_text(encoding="utf-8")
    assert "ENGLISH_INTENT_ALIASES" in source
    assert '"medication"' in source and '"appointment"' in source
    assert '"result"' in source and '"blood pressure"' in source
    assert 'return deterministic_respond(state, _router_text(patient_text))' in source
    assert "ENGLISH_SYMPTOM_ALIASES" in source
    assert '"pain when urinating"' in source


def test_final_recorder_is_english_live_app_not_static_cards() -> None:
    recorder = (ROOT / "scripts" / "record_submission_demo.py").read_text(encoding="utf-8")
    assert 'locale="en-US"' in recorder
    assert '"demo_language": "en-US"' in recorder
    assert '"live_app_only": True' in recorder
    assert '"static_title_cards": False' in recorder
    assert "Since yesterday I have burning pain when I urinate" in recorder
    assert "Explain the result" in recorder
    assert "require_message_locale(page, assistant_id, \"en\")" in recorder
    assert "title_card(" not in recorder
    assert "page.goto(f\"{BASE_URL}/login\"" in recorder
    assert "set_input_files(str(pdf_path))" in recorder
    assert "wait_for_result_mission(page, result_id)" in recorder


def test_lab_omega_records_real_browser_evidence_and_state_roundtrips() -> None:
    lab = (ROOT / "scripts" / "lab_omega.py").read_text(encoding="utf-8")
    assert "record_video_dir=str(VIDEO_DIR)" in lab
    assert "register_and_authenticate" in lab
    assert "exercise_registered_views" in lab
    assert "measurement_state_roundtrip" in lab
    assert "structured_result_upload" in lab
    assert "result_original_provenance" in lab
    assert "input_language_to_backend_en" in lab
    assert "input_language_to_backend_es" in lab
    assert "console_errors" in lab and "page_errors" in lab
