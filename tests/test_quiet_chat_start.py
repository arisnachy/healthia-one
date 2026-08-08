from healthia_one.service import seed_state
from healthia_one.orchestrator import respond


def test_synthetic_demo_opens_with_no_unsolicited_chat() -> None:
    state = seed_state()
    assert state.messages == []
    assert state.twin_events, "the twin may persist silently even when chat is empty"


def test_first_greeting_is_normal_and_zero_agent() -> None:
    state = seed_state()
    response = respond(state, "Hola")
    assert response.message.content == "Hola, ¿cómo estás hoy?"
    assert response.message.agent_plan == []
    assert response.message.metadata["llm_status"] == "not_needed"
    assert response.message.metadata["agent_execution"] == "none"
    assert state.messages == [], "routing a greeting must not inject hidden/background chat messages"
