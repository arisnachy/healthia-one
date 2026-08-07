import os

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"
os.environ["HEALTHIA_COST_MODE"] = "local"

from fastapi.testclient import TestClient

from app.main import app, service
from healthia_one.config import Settings
from healthia_one.gemini import GeminiResponder


def test_health_and_bootstrap():
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        bootstrap = client.get("/api/bootstrap")
        assert bootstrap.status_code == 200
        payload = bootstrap.json()
        assert payload["profile"]["display_name"] == "Ana Martínez"
        assert payload["vitals"]
        assert payload["weights"]


def test_default_cost_mode_is_zero_spend_and_cannot_be_enabled() -> None:
    with TestClient(app) as client:
        status = client.get("/api/cost-control")
        assert status.status_code == 200
        payload = status.json()
        assert payload["mode"] == "local"
        assert payload["enabled"] is False
        assert payload["requests_used"] == 0
        assert payload["requests_remaining"] == 0

        toggle = client.post("/api/cost-control?enabled=true")
        assert toggle.status_code == 409
        detail = toggle.json()["detail"]
        assert any(token in detail for token in ("API key", "límite", "modo"))


def test_static_shell_has_collapsible_panels_and_clean_authenticated_composer():
    html = open("web/index.html", encoding="utf-8").read()
    js = open("web/app.js", encoding="utf-8").read()
    assert "collapseLeft" in html and "collapseRight" in html
    assert 'refs.chatInput.value = ""' in js
    # Native EventSource cannot attach the Firebase bearer token. The app uses an
    # authenticated fetch stream and parses SSE frames itself.
    assert 'healthiaFetch("/api/events/stream"' in js
    assert "getReader()" in js
    assert "new EventSource" not in js
