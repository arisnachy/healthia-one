from __future__ import annotations

from healthia_one.config import Settings


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
