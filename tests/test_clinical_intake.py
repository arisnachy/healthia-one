import json

from healthia_one.clinical_intake import ANSWER_PREFIX, detect_clinical_consultation
from healthia_one.models import RiskLevel
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


def answer_payload(interview: dict, stage: int) -> str:
    if stage == 1:
        answers = [
            {"question_id": "onset", "question_prompt": "¿Cuándo comenzó y cómo ha evolucionado?", "selected": ["1 a 3 días"], "detail": "Empeora desde ayer"},
            {"question_id": "symptoms", "question_prompt": "¿Qué molestias acompañan el ardor?", "selected": ["Ardor al orinar", "Orino con más frecuencia"], "detail": ""},
            {"question_id": "severity", "question_prompt": "¿Qué intensidad tiene?", "selected": ["Moderada"], "detail": "4 de 10"},
            {"question_id": "red_flags", "question_prompt": "¿Tienes alguna señal de alarma?", "selected": ["Ninguna de las anteriores"], "detail": ""},
            {"question_id": "medications_allergies", "question_prompt": "¿Tomaste algo o tienes alergias?", "selected": ["No he tomado nada", "No tengo alergias conocidas"], "detail": ""},
        ]
    else:
        answers = [
            {"question_id": "modifiers", "question_prompt": "¿Qué cambia la molestia?", "selected": ["No identifico un patrón"], "detail": ""},
            {"question_id": "associated", "question_prompt": "¿Hay otros síntomas?", "selected": ["Ninguno"], "detail": ""},
            {"question_id": "history", "question_prompt": "¿Hay antecedentes relacionados?", "selected": ["Ninguno conocido"], "detail": ""},
            {"question_id": "vitals", "question_prompt": "¿Tienes signos vitales recientes?", "selected": ["No disponibles"], "detail": ""},
            {"question_id": "goal", "question_prompt": "¿Qué necesitas aclarar?", "selected": ["Entender posibles explicaciones", "Planificar seguimiento"], "detail": ""},
        ]
    return ANSWER_PREFIX + json.dumps({"interview_id": interview["id"], "stage": stage, "answers": answers})


def test_symptom_message_starts_ai_required_interview_without_prefabricated_questions() -> None:
    state = seed_state()
    response = respond(state, "Desde ayer me arde al orinar y tengo que ir al baño a cada rato")

    interview = response.message.metadata["clinical_interview"]
    assert response.message.metadata["intent"] == "clinical_consultation"
    assert interview["domain"] == "urinary"
    assert interview["stage"] == 1
    assert interview["question_block"]["questions"] == []
    assert interview["question_block"]["generation_required"] is True
    assert len(response.message.agent_plan) == 2
    assert {step.agent for step in response.message.agent_plan} == {"INTERVIEWER", "SENTINEL"}
    assert response.mission is not None
    assert response.mission.mission_type == "clinical_interview"


def test_interview_preserves_semantic_memory_and_waits_for_ai_resolution() -> None:
    state = seed_state()
    first = respond(state, "Desde ayer me arde al orinar y tengo frecuencia urinaria")
    state.messages.append(first.message)
    first_interview = first.message.metadata["clinical_interview"]

    second = respond(state, answer_payload(first_interview, 1))
    state.messages.append(second.message)
    second_interview = second.message.metadata["clinical_interview"]

    assert second_interview["stage"] == 2
    assert second_interview["id"] == first_interview["id"]
    assert second_interview["chief_complaint"] == "Desde ayer me arde al orinar y tengo frecuencia urinaria"
    assert len(second_interview["previous_answers"]) == 5
    assert all(item.get("question_prompt") for item in second_interview["previous_answers"])
    assert second_interview["question_block"]["questions"] == []
    assert second_interview["question_block"]["generation_required"] is True

    final = respond(state, answer_payload(second_interview, 2))
    final_interview = final.message.metadata["clinical_interview"]

    assert final_interview["status"] == "ready_for_synthesis"
    assert len(final_interview["answers"]) == 10
    assert final.message.metadata["council_status"] == "awaiting_ai_resolution"
    assert "decidir con IA" in final.message.content
    assert "¿Cuándo comenzó y cómo ha evolucionado?" in final.message.content
    mission = next(item for item in state.missions if item.id == first_interview["mission_id"])
    assert mission.status.value == "waiting_professional"
    assert mission.closure_evidence == ["adaptive_interview_answers_collected"]


def test_greeting_and_record_navigation_do_not_start_medical_interview() -> None:
    for text in ("Hola", "Muéstrame mi expediente", "Prepara mi próxima consulta"):
        is_consultation, _ = detect_clinical_consultation(text)
        assert is_consultation is False


def test_urgent_language_keeps_deterministic_safety_gate() -> None:
    state = seed_state()
    response = respond(state, "Tengo dolor fuerte en el pecho y dificultad para respirar")
    assert response.message.risk_level == RiskLevel.URGENT
    assert "clinical_interview" not in response.message.metadata