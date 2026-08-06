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


def test_gemini_enhances_the_real_patient_chat_boundary_without_provider_storage(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    settings = Settings(llm_backend="gemini_api", model="gemini-3.6-flash")
    client = FakeClient()
    responder = GeminiResponder(settings, client_factory=lambda: client)
    state = seed_state()
    draft = respond(state, "Quiero entender mi presión")
    result = asyncio.run(responder.enhance(state, "Quiero entender mi presión", draft))
    call = client.interactions.calls[0]
    assert result.message.content.startswith("Respuesta de Gemini")
    assert result.message.metadata["llm_status"] == "completed"
    assert result.message.metadata["store"] is False
    assert call["model"] == "gemini-3.6-flash"
    assert call["store"] is False
    assert "system_instruction" in call


def test_interaction_text_keeps_output_text_compatibility() -> None:
    interaction = SimpleNamespace(output_text="Texto directo", outputs=[])
    assert GeminiResponder._interaction_text(interaction) == "Texto directo"


def test_gemini_probe_executes_a_real_minimal_interaction(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = FakeClient(output="HEALTHIA_OK")
    responder = GeminiResponder(Settings(llm_backend="gemini_api"), client_factory=lambda: client)
    result = asyncio.run(responder.probe())
    assert result["ok"] is True
    assert result["live_request"] is True
    assert result["store"] is False
    assert result["response"] == "HEALTHIA_OK"
    call = client.interactions.calls[0]
    assert call["store"] is False
    assert call["input"] == "Responde únicamente con HEALTHIA_OK"


def test_gemini_probe_reports_provider_quota_failure(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class BrokenInteractions:
        def create(self, **kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    responder = GeminiResponder(
        Settings(llm_backend="gemini_api"),
        client_factory=lambda: SimpleNamespace(interactions=BrokenInteractions()),
    )
    result = asyncio.run(responder.probe())
    assert result["ok"] is False
    assert result["status"] == "probe_failed"
    assert result["live_request"] is True
    assert "RESOURCE_EXHAUSTED" in result["detail"]
