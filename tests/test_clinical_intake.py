import json

from healthia_one.clinical_intake import ANSWER_PREFIX, detect_clinical_consultation
from healthia_one.models import RiskLevel
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


def answer_payload(interview: dict, stage: int) -> str:
    if stage == 1:
        answers = [
            {"question_id": "onset", "question_prompt": "¿Cuándo comenzó y cómo ha evolucionado?", "selected": ["1 a 3 días"], "detail": "Empeora desde ayer"},
            {"question_id": "symptoms", "selected": ["Ardor al orinar", "Orino con más frecuencia"], "detail": ""},
            {"question_id": "severity", "selected": ["Moderada"], "detail": "4 de 10"},
            {"question_id": "red_flags", "selected": ["Ninguna de las anteriores"], "detail": ""},
            {"question_id": "medications_allergies", "selected": ["No he tomado nada", "No tengo alergias conocidas"], "detail": ""},
        ]
    else:
        answers = [
            {"question_id": "modifiers", "selected": ["No identifico un patrón"], "detail": ""},
            {"question_id": "associated", "selected": ["Ninguno"], "detail": ""},
            {"question_id": "history", "selected": ["Ninguno conocido"], "detail": ""},
            {"question_id": "vitals", "selected": ["No disponibles"], "detail": ""},
            {"question_id": "goal", "selected": ["Entender posibles explicaciones", "Planificar seguimiento"], "detail": ""},
        ]
    return ANSWER_PREFIX + json.dumps({"interview_id": interview["id"], "stage": stage, "answers": answers})


def test_symptom_message_starts_five_question_interview_with_minimal_capabilities() -> None:
    state = seed_state()
    response = respond(state, "Desde ayer me arde al orinar y tengo que ir al baño a cada rato")

    interview = response.message.metadata["clinical_interview"]
    assert response.message.metadata["intent"] == "clinical_consultation"
    assert interview["domain"] == "urinary"
    assert interview["stage"] == 1
    assert len(interview["question_block"]["questions"]) == 5
    assert 1 <= len(response.message.agent_plan) <= 2
    assert {step.agent for step in response.message.agent_plan} <= {"INTERVIEWER", "SENTINEL"}
    assert response.mission is not None
    assert response.mission.mission_type == "clinical_interview"


def test_interview_preserves_context_updates_twin_and_returns_updated_mission() -> None:
    state = seed_state()
    initial_twin_events = len(state.twin_events)
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
    assert len(second_interview["question_block"]["questions"]) == 5
    assert second.mission is not None and second.mission.id == first.mission.id
    assert len(state.twin_events) == initial_twin_events

    final = respond(state, answer_payload(second_interview, 2))

    assert final.message.metadata["clinical_interview"]["status"] == "completed"
    assert final.message.metadata["twin_updated"] is True
    assert "Desde ayer me arde al orinar y tengo frecuencia urinaria" in final.message.content
    assert "### Lo que entendí de tu consulta" in final.message.content
    assert "No confirmaré un diagnóstico" in final.message.content
    assert "¿Cuándo comenzó y cómo ha evolucionado?" in final.message.content
    assert final.mission is not None and final.mission.id == first.mission.id
    assert final.mission.next_action == "Revisar la síntesis clínica y confirmar el nivel de atención con un profesional"
    mission = next(item for item in state.missions if item.id == first_interview["mission_id"])
    assert mission.status.value == "waiting_professional"
    assert mission.closure_evidence == ["adaptive_interview_completed"]
    twin_event = next(item for item in state.twin_events if item.entity_id == first_interview["id"])
    assert twin_event.event_type == "clinical_interview_reported"
    assert twin_event.certainty == "patient_reported"
    assert twin_event.source.source_type == "patient_report"
    assert twin_event.verification_status == "unverified"
    assert len(state.twin_events) == initial_twin_events + 1


def test_greeting_and_record_navigation_do_not_start_medical_interview() -> None:
    for text in ("Hola", "Muéstrame mi expediente", "Prepara mi próxima consulta"):
        is_consultation, _ = detect_clinical_consultation(text)
        assert is_consultation is False


def test_urgent_language_keeps_deterministic_safety_gate() -> None:
    state = seed_state()
    response = respond(state, "Tengo dolor fuerte en el pecho y dificultad para respirar")
    assert response.message.risk_level == RiskLevel.URGENT
    assert "clinical_interview" not in response.message.metadata
