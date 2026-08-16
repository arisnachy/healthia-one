from pathlib import Path

import pytest

from healthia_one.adk_gemini import AdkGeminiResponder
from healthia_one.config import Settings
from healthia_one.models import ChatMessage, ChatResponse, RiskLevel
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


ORCHESTRATOR_SOURCE = Path("healthia_one/orchestrator.py").read_text(encoding="utf-8")
ADK_GEMINI_SOURCE = Path("healthia_one/adk_gemini.py").read_text(encoding="utf-8")


def test_google_mission_gate_is_ordered_after_safety_before_opportunity():
    safety_index = ORCHESTRATOR_SOURCE.index("if safety.must_stop_normal_flow:")
    google_index = ORCHESTRATOR_SOURCE.index("if should_consider_google_mission(state, patient_text):")
    opportunity_index = ORCHESTRATOR_SOURCE.index("opportunity_response = opportunity_respond(state, patient_text)")
    assert safety_index < google_index < opportunity_index


def test_urgent_navigation_language_never_becomes_google_mission_candidate():
    state = seed_state()
    response = respond(
        state,
        "Tengo dolor fuerte en el pecho y falta de aire; búscame una clínica en Santiago",
    )
    assert response.message.risk_level == RiskLevel.URGENT
    assert response.message.metadata.get("google_mission_candidate") is not True
    assert response.message.metadata.get("opportunity_autopilot") is not True


def test_strong_navigation_intent_becomes_google_candidate_before_opportunity():
    state = seed_state()
    response = respond(state, "Búscame un centro de autismo en Santiago")
    assert response.message.metadata["google_mission_candidate"] is True
    assert response.message.metadata["google_mission_routing_order"] == "after_deterministic_safety_before_opportunity"
    assert response.message.metadata.get("opportunity_autopilot") is not True


@pytest.mark.asyncio
async def test_google_candidate_is_routed_once_and_skips_general_enhancer(monkeypatch):
    settings = Settings(store_backend="memory", llm_backend="mock")
    responder = AdkGeminiResponder(settings)
    state = seed_state()
    draft = respond(state, "Búscame un centro de autismo en Santiago")
    calls = []

    async def fake_google_route(_state, patient_text):
        calls.append(patient_text)
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                author="HealthIA",
                content="Encontré la misión de navegación.",
                metadata={
                    "google_constellation": True,
                    "google_mission_id": "gmission_test",
                    "google_mission_state": "awaiting_selection",
                },
            )
        )

    async def forbidden_super_enhance(*args, **kwargs):
        raise AssertionError("general enhancer must not run after a Google mission response")

    monkeypatch.setattr(responder.google_mission_router, "respond", fake_google_route)
    monkeypatch.setattr("healthia_one.gemini.GeminiResponder.enhance", forbidden_super_enhance)

    result = await responder.enhance(state, "Búscame un centro de autismo en Santiago", draft)
    assert calls == ["Búscame un centro de autismo en Santiago"]
    assert result.message.metadata["google_mission_id"] == "gmission_test"
    assert result.message.metadata["llm_status"] == "google_mission_routed"
    assert result.message.metadata["google_mission_routing_order"] == "deterministic_safety_then_google_mission"


def test_adk_enhancer_rechecks_safety_before_google_execution():
    assert "safety = assess_text(patient_text)" in ADK_GEMINI_SOURCE
    assert "if not safety.must_stop_normal_flow:" in ADK_GEMINI_SOURCE
    assert "mission_response = await self.google_mission_router.respond(state, patient_text)" in ADK_GEMINI_SOURCE
