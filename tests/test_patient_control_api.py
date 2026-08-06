import os
from datetime import datetime, timedelta, timezone

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"

from fastapi.testclient import TestClient

from app.main import app


def test_patient_can_update_consent_snooze_mute_and_export():
    with TestClient(app) as client:
        consent = client.get("/api/consent").json()
        consent["proactive_enabled"] = False
        consent["signal_types"] = ["vitals", "appointments"]
        consent["quiet_hours_start"] = "21:30"
        consent["quiet_hours_end"] = "06:30"
        updated = client.put("/api/consent", json=consent)
        assert updated.status_code == 200
        assert updated.json()["signal_types"] == ["vitals", "appointments"]

        snoozed = client.post("/api/consent/snooze", json={"hours": 24})
        muted = client.post("/api/consent/mute", json={"prefix": "weight:"})
        exported = client.get("/api/export")
        audit = client.get("/api/audit")

        assert snoozed.status_code == 200
        assert "weight:" in muted.json()["muted_rule_prefixes"]
        assert exported.status_code == 200
        assert exported.headers["content-disposition"].endswith("healthia-one-patient-export.json")
        assert exported.json()["export"]["contains_binary_files"] is False
        assert audit.status_code == 200
        assert any(event["action"] == "update_consent" for event in audit.json()["events"])


def test_backdated_measurements_are_sorted_chronologically():
    with TestClient(app) as client:
        older = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        newer = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        first = client.post("/api/weight", json={"weight_kg": 77.0, "measured_at": newer}).json()
        second = client.post("/api/weight", json={"weight_kg": 76.0, "measured_at": older}).json()
        weights = client.get("/api/bootstrap").json()["weights"]
        positions = {item["id"]: index for index, item in enumerate(weights)}
        assert positions[second["id"]] < positions[first["id"]]


def test_chat_opens_patient_control_mission():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "Quiero revisar mis permisos y exportar mis datos"})
        assert response.status_code == 200
        body = response.json()
        assert body["mission"]["mission_type"] == "patient_control"
        assert body["message"]["metadata"]["action_target"] == "control"
