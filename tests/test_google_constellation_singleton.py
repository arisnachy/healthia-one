from fastapi.testclient import TestClient

from app.main import app
from healthia_one.config import Settings
from healthia_one.google_constellation_singleton import (
    get_google_constellation_service,
    reset_google_constellation_singletons_for_tests,
)


def test_memory_constellation_singleton_returns_same_service_for_same_runtime_settings():
    reset_google_constellation_singletons_for_tests()
    settings = Settings(store_backend="memory", llm_backend="mock")
    first = get_google_constellation_service(settings)
    second = get_google_constellation_service(settings)
    assert first is second
    assert first.coordinator.store is second.coordinator.store


def test_fastapi_uses_same_constellation_singleton_as_other_surfaces():
    with TestClient(app):
        expected = get_google_constellation_service(app.state.healthia_service.settings)
        assert app.state.google_constellation is expected
