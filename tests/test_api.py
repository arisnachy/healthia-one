import os
from io import BytesIO

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"
os.environ["HEALTHIA_COST_MODE"] = "local"
os.environ["HEALTHIA_AI_REQUEST_LIMIT"] = "0"
os.environ["HEALTHIA_COST_GUARD_START_ENABLED"] = "false"
os.environ["HEALTHIA_PROACTIVE_ENABLED"] = "false"

from fastapi.testclient import TestClient
from app.main import app


def test_bootstrap_and_chat():
    with TestClient(app) as client:
        bootstrap = client.get("/api/bootstrap")
        assert bootstrap.status_code == 200
        assert bootstrap.json()["profile"]["id"] == "patient_demo"
        response = client.post("/api/chat", json={"message": "Quiero revisar mi peso"})
        assert response.status_code == 200
        payload = response.json()
        # Free language is intentionally left for the semantic model instead of
        # being hijacked by a keyword router. In zero-spend test mode the safe
        # semantic draft is returned without fabricating an agent run.
        assert payload["mission"] is None
        assert payload["message"]["metadata"]["semantic_route"] == "model_required"
        assert payload["message"]["agent_plan"] == []


def test_proactive_tick_is_manual_and_idempotent_for_same_rule_keys():
    with TestClient(app) as client:
        readiness = client.get("/api/readiness").json()
        assert readiness["proactive_enabled"] is False
        first = client.post("/api/demo/tick").json()["created"]
        second = client.post("/api/demo/tick").json()["created"]
        assert first >= 1
        assert second == 0


def test_uploaded_multimodal_original_is_preserved_for_authenticated_retrieval():
    payload = b"synthetic-image-bytes"
    with TestClient(app) as client:
        response = client.post(
            "/api/results/upload",
            files={"file": ("ct-synthetic.png", BytesIO(payload), "image/png")},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "pending_multimodal"
        assert "no se consume una llamada" in result["explanation"]
        original = client.get(f"/api/results/{result['id']}/file")
        assert original.status_code == 200
        assert original.content == payload


def test_cost_control_defaults_to_local_zero_spend_and_cannot_be_enabled():
    with TestClient(app) as client:
        readiness = client.get("/api/readiness")
        assert readiness.status_code == 200
        cost = readiness.json()["cost_control"]
        assert cost["mode"] == "local"
        assert cost["enabled"] is False
        assert cost["request_limit"] == 0
        assert cost["estimated_spend_usd"] is None

        status = client.get("/api/cost-control")
        assert status.status_code == 200
        assert status.json()["requests_remaining"] == 0

        toggle = client.post("/api/cost-control?enabled=true")
        assert toggle.status_code == 409
        detail = toggle.json()["detail"]
        assert any(token in detail for token in ("API key", "límite", "modo"))


def test_static_shell_has_collapsible_panels_and_authenticated_event_stream():
    html = open("web/index.html", encoding="utf-8").read()
    js = open("web/app.js", encoding="utf-8").read()
    assert "collapseLeft" in html and "collapseRight" in html
    assert 'refs.chatInput.value = ""' in js
    assert "function upsertMission" in js
    assert "data-result-file" in js
    assert 'healthiaFetch(`/api/results/${encodeURIComponent(resultId)}/file`)' in js
    # EventSource cannot attach Firebase bearer headers. The same SSE endpoint is
    # consumed through authenticated fetch and a ReadableStream instead.
    assert 'healthiaFetch("/api/events/stream"' in js
    assert "getReader()" in js
    assert "new EventSource" not in js
