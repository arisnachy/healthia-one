from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from healthia_one.config import Settings
from healthia_one.google_constellation_singleton import get_google_constellation_service


def test_memory_constellation_singleton_returns_same_service_for_same_runtime_settings():
    # Use a distinct singleton key instead of clearing the process-wide registry.
    # `app` is already imported and legitimately holds its startup singleton; a
    # global reset here would invalidate the test environment, not production.
    settings = Settings(
        store_backend="memory",
        llm_backend="mock",
        data_path=Path("data/test-google-singleton-isolated.json"),
    )
    first = get_google_constellation_service(settings)
    second = get_google_constellation_service(settings)
    assert first is second
    assert first.coordinator.store is second.coordinator.store


def test_fastapi_uses_same_constellation_singleton_as_other_surfaces():
    with TestClient(app):
        expected = get_google_constellation_service(app.state.healthia_service.settings)
        assert app.state.google_constellation is expected
        assert app.state.google_constellation is app.state.healthia_service.gemini.google_mission_router.constellation
