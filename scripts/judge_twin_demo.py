from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from io import BytesIO

os.environ.setdefault("HEALTHIA_STORE_BACKEND", "memory")
os.environ.setdefault("HEALTHIA_LLM_BACKEND", "mock")
os.environ.setdefault("HEALTHIA_COST_MODE", "local")
os.environ.setdefault("HEALTHIA_AI_REQUEST_LIMIT", "0")
os.environ.setdefault("HEALTHIA_COST_GUARD_START_ENABLED", "false")
os.environ.setdefault("HEALTHIA_PROACTIVE_ENABLED", "false")
os.environ.setdefault("HEALTHIA_BLOB_BACKEND", "local")

from fastapi.testclient import TestClient

from app.main import app


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run() -> dict:
    now = datetime.now(timezone.utc)
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        start = client.get("/api/bootstrap").json()
        initial_messages = len(start["messages"])

        greeting = client.post("/api/chat", json={"message": "Hola"}).json()
        require(greeting["message"]["metadata"].get("llm_status") == "not_needed", "greeting used model")
        require(greeting["message"]["agent_plan"] == [], "greeting woke agents")
        after_greeting = client.get("/api/bootstrap").json()
        require(len(after_greeting["messages"]) == initial_messages + 2, "background chat spam appeared")

        lab_payload = {
            "panel": "Panel metabólico sintético",
            "results": [
                {"name": "Glucosa", "value": 108, "unit": "mg/dL", "reference": "70-99", "flag": "high"},
                {"name": "Creatinina", "value": 0.9, "unit": "mg/dL", "reference": "0.6-1.2"},
            ],
        }
        upload = client.post(
            "/api/results/upload",
            files={"file": ("metabolic.json", BytesIO(json.dumps(lab_payload).encode()), "application/json")},
        )
        require(upload.status_code == 200, upload.text)
        result = upload.json()
        require(result["artifact_type"] == "laboratory", "structured lab was not identified")
        require(result["original_storage_uri"], "original artifact URI missing")
        original = client.get(f"/api/results/{result['id']}/file")
        require(original.status_code == 200, "original artifact cannot be reopened")

        twin = client.get("/api/bootstrap").json()
        result_event = next(
            (event for event in twin["twin_events"] if event["entity_type"] == "result" and event["entity_id"] == result["id"]),
            None,
        )
        require(result_event is not None, "result never reached living twin")
        require(result_event["source"]["source_type"] != "AI_extraction", "deterministic lab was mislabeled as AI")

        chat = client.post(
            "/api/chat",
            json={"message": "¿Qué decía el Panel metabólico sintético que subí?"},
        ).json()
        require(result["id"] in chat["message"]["metadata"].get("compiled_result_ids", []), "chat could not retrieve old result")
        require(chat["message"]["agent_plan"] == [], "result retrieval unnecessarily woke agents in zero-spend mode")

        pairing = client.post("/api/devices/pairing").json()
        claim = client.post(
            "/api/devices/pairing/claim",
            json={"code": pairing["code"], "device_id": "judge-phone", "display_name": "Judge phone"},
        ).json()
        sync = client.post(
            "/api/devices/health-connect/sync",
            headers={"Authorization": f"Bearer {claim['access_token']}"},
            json={
                "device_id": "judge-phone",
                "records": [
                    {
                        "patient_id": "forged-other-user",
                        "external_id": f"judge-steps-{now.timestamp()}",
                        "metric": "steps",
                        "observed_at": now.isoformat(),
                        "value": 7100,
                        "unit": "count",
                        "source_package": "com.healthia.judge",
                    }
                ],
            },
        ).json()
        require(sync["patient_id"] == "patient_demo", "device escaped paired patient identity")
        require(sync["twin_events_added"] == 1, "device did not add a twin event")

        final = client.get("/api/bootstrap").json()
        require(any(item["steps"] == 7100 for item in final["activity"]), "device activity missing")
        require(any(event["event_type"] == "device_observation" for event in final["twin_events"]), "device event missing from twin")

        readiness = client.get("/api/readiness").json()
        require(readiness["proactive_enabled"] is False, "background polling unexpectedly enabled")
        require(readiness["cost_control"]["requests_used"] == 0, "zero-spend rehearsal used provider requests")

    return {
        "status": "PASS",
        "provider_requests": 0,
        "proof": {
            "greeting_zero_agents": True,
            "no_unsolicited_chat": True,
            "structured_result_to_twin": True,
            "original_result_reopenable": True,
            "old_result_retrievable_by_chat": True,
            "device_identity_rebound": True,
            "device_event_to_twin": True,
        },
        "truth_boundary": "Local zero-spend rehearsal. Live Google ADK/Gemini/Cloud proof remains a separate external gate.",
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
