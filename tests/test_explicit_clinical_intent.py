from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


def test_explicit_request_starts_general_ai_required_clinical_interview() -> None:
    state = seed_state()
    response = respond(state, "Quiero hacer una consulta")
    interview = response.message.metadata["clinical_interview"]
    assert interview["domain"] == "general"
    assert interview["chief_complaint"] == "Quiero hacer una consulta"
    assert interview["question_block"]["questions"] == []
    assert interview["question_block"]["generation_required"] is True
    assert len(response.message.agent_plan) == 2


def test_prepare_existing_consultation_keeps_appointment_route() -> None:
    state = seed_state()
    response = respond(state, "Prepara mi próxima consulta")
    assert "clinical_interview" not in response.message.metadata
    assert response.message.metadata["action_target"] == "appointments"
