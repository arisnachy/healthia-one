from pathlib import Path

from healthia_one.orchestrator import respond
from healthia_one.patient_control import maybe_control_response
from healthia_one.service import seed_state


ROOT = Path(__file__).resolve().parents[1]


def test_low_confidence_health_language_stays_conversational() -> None:
    state = seed_state()
    response = respond(state, "Siento algo raro")

    assert response.message.metadata["intent"] == "clinical_conversation"
    assert response.message.metadata["clinical_mode"] == "conversation_first"
    assert response.message.metadata["structured_interview_started"] is False
    assert "clinical_interview" not in response.message.metadata
    assert response.mission is None


def test_detailed_symptom_narrative_can_still_start_adaptive_interview() -> None:
    state = seed_state()
    response = respond(state, "Tengo dolor de cuello desde ayer")

    assert response.message.metadata["intent"] == "clinical_consultation"
    assert response.message.metadata["clinical_interview"]["status"] == "awaiting_answers"
    assert response.mission is not None


def test_chat_open_results_command_is_not_hijacked_by_clinical_intake() -> None:
    state = seed_state()
    response = respond(state, "No puedo abrir mis resultados desde ayer; abre mis resultados")

    assert "clinical_interview" not in response.message.metadata
    assert response.message.metadata["ui_action"] == {"type": "open_view", "view": "results"}
    assert response.message.metadata["health_os_control"] is True


def test_chat_can_open_measurement_entry_directly() -> None:
    state = seed_state()
    response = respond(state, "Quiero registrar mi presión arterial")

    assert "clinical_interview" not in response.message.metadata
    assert response.message.metadata["ui_action"] == {
        "type": "open_dialog",
        "view": "measurements",
        "dialog": "vital",
    }


def test_chat_can_open_result_upload_picker() -> None:
    state = seed_state()
    response = respond(state, "Quiero subir un resultado de laboratorio")

    assert "clinical_interview" not in response.message.metadata
    assert response.message.metadata["ui_action"] == {
        "type": "pick_file",
        "view": "results",
        "picker": "result",
    }


def test_chat_can_navigate_profile_and_devices() -> None:
    state = seed_state()
    profile = respond(state, "Abre mi perfil")
    devices = respond(state, "Muéstrame mis dispositivos")

    assert profile.message.metadata["ui_action"] == {"type": "open_view", "view": "profile"}
    assert devices.message.metadata["ui_action"] == {"type": "open_view", "view": "devices"}
    assert "clinical_interview" not in profile.message.metadata
    assert "clinical_interview" not in devices.message.metadata


def test_privacy_control_response_exposes_health_os_action() -> None:
    state = seed_state()
    response = maybe_control_response(state, "Abre privacidad y permisos")

    assert response is not None
    assert response.message.metadata["ui_action"] == {"type": "open_view", "view": "control"}
    assert response.message.metadata["health_os_control"] is True


def test_frontend_executes_chat_ui_actions_only_after_a_new_chat_response() -> None:
    source = (ROOT / "web" / "continuity.js").read_text(encoding="utf-8")

    assert "__HEALTHIA_CHAT_OS_CONTROLLER__" in source
    assert "metadata?.ui_action" in source
    assert 'action.type === "open_dialog"' in source
    assert 'action.type === "pick_file"' in source
    assert 'healthia:chat-settled' in source
    assert "let armed = false" in source
    assert "latestAssistant?.metadata?.ui_action" in source
    assert 'document.addEventListener("healthia:ui-updated"' not in source


def test_adaptive_five_question_contract_is_presented_one_turn_at_a_time() -> None:
    source = (ROOT / "web" / "conversational-interview.js").read_text(encoding="utf-8")
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "web" / "conversational-interview.css").read_text(encoding="utf-8")

    assert "__HEALTHIA_CONVERSATIONAL_INTERVIEW__" in source
    assert 'const ANSWER_PREFIX = "[ENTREVISTA_CLINICA]"' in source
    assert "fields.length !== 5" in source
    assert "index !== current" in source
    assert "clinical-next-question" in source
    assert "clinical-dont-know" in source
    assert "ensureFreeText(fieldset)" in source
    assert "form.requestSubmit()" in source
    assert "collectPayload(form, fields)" in source
    assert "answeredByKey" in source
    assert "conversationCompleted" in source
    assert ".clinical-conversation-mode" in css
    assert index.index("clinical-council.js") < index.index("conversational-interview.js")


def test_answered_interview_can_render_as_readable_chat_history() -> None:
    source = (ROOT / "web" / "conversational-interview.js").read_text(encoding="utf-8")

    assert "parseAnswerPayload" in source
    assert "payload.answers" in source
    assert "clinical-conversation-history" in source
    assert "clinical-mini-turn assistant" in source
    assert "clinical-mini-turn patient" in source
    assert "Esta parte ya la conversamos" in source
