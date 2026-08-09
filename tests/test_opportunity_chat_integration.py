from healthia_one.models import FamilyCondition, FamilyMember
from healthia_one.opportunity_integration import _resource_location
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


def test_generic_benefits_question_is_not_hijacked_by_assistance_radar():
    state = seed_state()
    response = respond(state, "¿Qué beneficios tiene caminar todos los días?")

    assert response.message.metadata.get("opportunity_autopilot") is not True


def test_generic_what_is_missing_is_not_hijacked_by_application_workflow():
    state = seed_state()
    response = respond(state, "¿Qué falta?")

    assert response.message.metadata.get("opportunity_autopilot") is not True


def test_urgent_safety_outranks_financial_assistance_in_same_turn():
    state = seed_state()
    response = respond(
        state,
        "Tengo dolor fuerte en el pecho y falta de aire; también quería preguntar por una ayuda económica.",
    )

    assert response.message.metadata.get("opportunity_autopilot") is not True
    assert str(response.message.risk_level) in {"urgent", "priority"}


def test_resource_search_never_treats_locale_as_residence():
    state = seed_state()
    state.profile.locale = "es-DO"
    state.profile.address = ""

    location = _resource_location(state)

    assert location["country"] == ""
    assert location["region"] == ""
    assert location["locality"] == ""


def test_chat_can_request_family_support_without_hidden_model_spend_in_local_mode():
    state = seed_state()
    state.family_members.append(
        FamilyMember(
            display_name="Hijo",
            relation="hijo",
            generation=1,
            conditions=[FamilyCondition(name="Autismo", confirmed=True)],
        )
    )

    response = respond(state, "Busca ayudas para autismo")

    assert response.message.metadata.get("opportunity_autopilot") is True
    assert response.message.metadata.get("paid_search_enabled") is False
    assert "no haré llamadas ocultas" in response.message.content
