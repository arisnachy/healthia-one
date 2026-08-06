from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


def test_explicit_request_starts_general_clinical_interview() -> None:
    state = seed_state()
    response = respond(state, "Quiero hacer una consulta")
    interview = response.message.metadata["clinical_interview"]
    assert interview["domain"] == "general"
    assert interview["chief_complaint"] == "Quiero hacer una consulta"
    assert len(interview["question_block"]["questions"]) == 5


def test_prepare_existing_consultation_keeps_appointment_route() -> None:
    state = seed_state()
    response = respond(state, "Prepara mi próxima consulta")
    assert "clinical_interview" not in response.message.metadata
    assert response.message.metadata["action_target"] == "appointments"
