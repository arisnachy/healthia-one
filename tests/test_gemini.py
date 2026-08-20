import asyncio
from types import SimpleNamespace

from healthia_one.config import Settings
from healthia_one.gemini import GeminiResponder
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


class FakeInteractions:
    def __init__(self, output: str = "Respuesta de Gemini basada en el contexto autorizado.") -> None:
        self.calls = []
        self.output = output

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(outputs=[SimpleNamespace(text=self.output)])


class FakeClient:
    def __init__(self, output: str = "Respuesta de Gemini basada en el contexto autorizado.") -> None:
        self.interactions = FakeInteractions(output)


def guarded_settings(**overrides) -> Settings:
    values = {
        "llm_backend": "gemini_api",
        "model": "gemini-3.6-flash",
        "cost_mode": "guarded",
        "ai_request_limit": 3,
        "cost_guard_start_enabled": True,
        "ai_max_output_tokens": 500,
    }
    values.update(overrides)
    return Settings(**values)


def test_gemini_enhances_the_real_patient_chat_boundary_without_provider_storage(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = FakeClient()
    responder = GeminiResponder(guarded_settings(), client_factory=lambda: client)
    state = seed_state()
    draft = respond(state, "Quiero entender mi presión")
    result = asyncio.run(responder.enhance(state, "Quiero entender mi presión", draft))
    call = client.interactions.calls[0]
    assert result.message.content.startswith("Respuesta de Gemini")
    assert result.message.metadata["llm_status"] == "completed"
    assert result.message.metadata["store"] is False
    assert result.message.metadata["request_number"] == 1
    assert call["model"] == "gemini-3.6-flash"
    assert call["store"] is False
    assert call["generation_config"]["max_output_tokens"] == 500
    assert call["generation_config"]["thinking_level"] == "minimal"
    assert "system_instruction" in call


def test_gemini_withholds_generated_clinical_directive(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = FakeClient(output="Suspenda el medicamento hoy.")
    responder = GeminiResponder(guarded_settings(), client_factory=lambda: client)
    state = seed_state()
    draft = respond(state, "Quiero entender mi presión")
    deterministic_content = draft.message.content

    result = asyncio.run(responder.enhance(state, "Quiero entender mi presión", draft))

    assert result.message.content == deterministic_content
    assert result.message.metadata["llm_status"] == "safety_withheld"
    assert responder.last_status == "safety_withheld"


def test_interaction_text_keeps_output_text_compatibility() -> None:
    interaction = SimpleNamespace(output_text="Texto directo", outputs=[])
    assert GeminiResponder._interaction_text(interaction) == "Texto directo"


def test_gemini_probe_executes_one_guarded_minimal_interaction(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = FakeClient(output="HEALTHIA_OK")
    responder = GeminiResponder(guarded_settings(ai_request_limit=1), client_factory=lambda: client)
    result = asyncio.run(responder.probe())
    assert result["ok"] is True
    assert result["live_request"] is True
    assert result["store"] is False
    assert result["response"] == "HEALTHIA_OK"
    assert result["request_number"] == 1
    assert result["cost_guard"]["requests_remaining"] == 0
    assert result["cost_guard"]["enabled"] is False
    call = client.interactions.calls[0]
    assert call["store"] is False
    assert call["input"] == "Responde únicamente con HEALTHIA_OK"
    assert call["generation_config"]["max_output_tokens"] == 32


def test_gemini_probe_reports_provider_quota_failure_and_counts_attempt(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class BrokenInteractions:
        def create(self, **kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    responder = GeminiResponder(
        guarded_settings(ai_request_limit=2),
        client_factory=lambda: SimpleNamespace(interactions=BrokenInteractions()),
    )
    result = asyncio.run(responder.probe())
    assert result["ok"] is False
    assert result["status"] == "probe_failed"
    assert result["live_request"] is True
    assert result["request_number"] == 1
    assert result["cost_guard"]["requests_used"] == 1
    assert "RESOURCE_EXHAUSTED" in result["detail"]


def test_gemini_never_contacts_provider_when_cost_switch_is_off(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = FakeClient()
    responder = GeminiResponder(
        guarded_settings(cost_guard_start_enabled=False),
        client_factory=lambda: client,
    )
    state = seed_state()
    draft = respond(state, "Quiero entender mi presión")
    result = asyncio.run(responder.enhance(state, "Quiero entender mi presión", draft))
    assert result.message.metadata["llm_status"] == "cost_guard_blocked"
    assert client.interactions.calls == []
    assert responder.cost_status()["blocked_requests"] == 1
