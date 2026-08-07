from __future__ import annotations

from types import SimpleNamespace

from healthia_one.config import Settings
from healthia_one.google_ai_transport import VertexInteractionsAdapter


def test_final_candidate_defaults_to_hackathon_gemini_35_flash() -> None:
    assert Settings().model == "gemini-3.5-flash"


def test_vertex_readiness_uses_project_not_gemini_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "healthia-test-project")
    settings = Settings(llm_backend="gemini_api")
    assert settings.vertex_ai_enabled is True
    assert settings.adk_ready is True


def test_vertex_readiness_fails_closed_without_project(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    settings = Settings(llm_backend="gemini_api")
    assert settings.vertex_ai_enabled is True
    assert settings.adk_ready is False


def test_vertex_adapter_preserves_structured_output_and_thinking_controls() -> None:
    class FakeModels:
        def __init__(self) -> None:
            self.config = None

        def generate_content(self, *, model, contents, config):
            assert model == "gemini-3.5-flash"
            assert contents == "extract this"
            self.config = config
            return SimpleNamespace(text='{"status":"ok"}')

    fake_models = FakeModels()
    adapter = VertexInteractionsAdapter(SimpleNamespace(models=fake_models))
    schema = {
        "type": "object",
        "required": ["status"],
        "properties": {"status": {"type": "string"}},
    }
    response = adapter.create(
        model="gemini-3.5-flash",
        input="extract this",
        generation_config={
            "max_output_tokens": 256,
            "thinking_level": "minimal",
            "response_mime_type": "application/json",
            "response_json_schema": schema,
        },
        store=False,
    )

    assert response.output_text == '{"status":"ok"}'
    assert fake_models.config is not None
    assert getattr(fake_models.config, "max_output_tokens", None) == 256
    assert getattr(fake_models.config, "response_mime_type", None) == "application/json"
    assert getattr(fake_models.config, "response_json_schema", None) == schema
    thinking = getattr(fake_models.config, "thinking_config", None)
    assert thinking is not None
    assert "minimal" in str(getattr(thinking, "thinking_level", "")).lower()
