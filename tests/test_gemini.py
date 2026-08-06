import asyncio
from types import SimpleNamespace

from healthia_one.config import Settings
from healthia_one.gemini import GeminiResponder
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


class FakeInteractions:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text="Respuesta de Gemini basada en el contexto autorizado.")


class FakeModels:
    def get(self, *, model: str):
        return SimpleNamespace(name=model)


class FakeClient:
    def __init__(self) -> None:
        self.interactions = FakeInteractions()
        self.models = FakeModels()


def test_gemini_enhances_the_real_patient_chat_boundary(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    settings = Settings(llm_backend="gemini_api", model="gemini-3.6-flash")
    client = FakeClient()
    responder = GeminiResponder(settings, client_factory=lambda: client)
    state = seed_state()
    draft = respond(state, "Quiero entender mi presión")
    result = asyncio.run(responder.enhance(state, "Quiero entender mi presión", draft))
    assert result.message.content.startswith("Respuesta de Gemini")
    assert result.message.metadata["llm_status"] == "completed"
    assert client.interactions.calls[0]["model"] == "gemini-3.6-flash"
    assert "system_instruction" in client.interactions.calls[0]


def test_gemini_probe_uses_model_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    responder = GeminiResponder(Settings(llm_backend="gemini_api"), client_factory=FakeClient)
    result = asyncio.run(responder.probe())
    assert result["ok"] is True
