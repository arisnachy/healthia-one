from pathlib import Path

from healthia_one.language import bind_requested_locale, reset_requested_locale
from healthia_one.models import ChatMessage
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
    assert response.message.mission_id == response.mission.id
    assert any(item.id == response.mission.id for item in state.missions)


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


def test_past_tense_upload_narration_is_not_mistaken_for_file_picker_command() -> None:
    state = seed_state()
    response = respond(
        state,
        "Explain the result I just uploaded and confirm that it was saved with the original file.",
    )

    assert "ui_action" not in response.message.metadata
    assert response.mission is not None
    assert response.mission.mission_type == "result_explanation"
    assert response.message.metadata["mission_type"] == "result_explanation"
    assert response.message.mission_id == response.mission.id
    assert any(
        item.id == response.mission.id and item.mission_type == "result_explanation"
        for item in state.missions
    )


def test_explicit_result_explanation_outranks_stale_treatment_context() -> None:
    state = seed_state()
    state.messages.append(
        ChatMessage(
            role="assistant",
            author="HealthIA",
            content="We were reviewing your treatment.",
            metadata={"action_target": "treatment", "mission_type": "medication_management"},
        )
    )

    response = respond(
        state,
        "Explain the result synthetic-final-lab.pdf I just uploaded and confirm that it was saved with the original file.",
    )

    assert response.mission is not None
    assert response.mission.mission_type == "result_explanation"
    assert response.message.metadata["action_target"] == "results"
    assert response.message.metadata["mission_type"] == "result_explanation"
    assert response.message.mission_id == response.mission.id
    assert any(item.id == response.mission.id for item in state.missions)


def test_english_request_localizes_durable_mission_copy() -> None:
    token = bind_requested_locale("en-US")
    try:
        state = seed_state()
        clinical = respond(
            state,
            "I have burning pain when I urinate since yesterday and I want to discuss a health problem.",
        )
        assert clinical.mission is not None
        assert clinical.mission.title == "Understand the current health problem and guide the next step"
        assert clinical.mission.next_action == "Answer the adaptive questions generated for this case"

        result = respond(
            state,
            "Explain the result I just uploaded and confirm that it was saved with the original file.",
        )
        assert result.mission is not None
        assert result.mission.title == "Understand a health result"
        assert result.mission.next_action == "Upload the result you want to review"
        assert all("Comprender" not in item.title for item in state.missions)
        assert all("Cargar el resultado" not in item.next_action for item in state.missions)
    finally:
        reset_requested_locale(token)


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
