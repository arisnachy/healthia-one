from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


def test_profile_and_device_endpoints() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        profile = client.get("/api/profile")
        assert profile.status_code == 200
        assert "vitals" in profile.json()
        assert "pregnancy" in profile.json()

        normalized = client.post(
            "/api/profile/medications/normalize",
            json={"text": "Metformina 500 mg vía oral cada 12 horas"},
        )
        assert normalized.status_code == 200
        assert normalized.json()["requires_confirmation"] is True
        assert normalized.json()["suggestion"]["frequency_times_per_day"] == 2

        pairing = client.post("/api/devices/pairing").json()
        claim = client.post(
            "/api/devices/pairing/claim",
            json={"code": pairing["code"], "device_id": "api-test-phone", "display_name": "API test phone"},
        )
        assert claim.status_code == 200
        sync = client.post(
            "/api/devices/health-connect/sync",
            headers={"Authorization": f"Bearer {claim.json()['access_token']}"},
            json={
                "device_id": "api-test-phone",
                "source_package": "com.healthia.test",
                "background_read": True,
                "granted_metrics": ["heart_rate"],
                "records": [
                    {
                        "external_id": "api-heart-1",
                        "metric": "heart_rate",
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        "value": 74,
                        "unit": "bpm",
                        "source_package": "com.healthia.test",
                    }
                ],
            },
        )
        assert sync.status_code == 200
        assert sync.json()["accepted"] == 1
        devices = client.get("/api/devices")
        assert devices.status_code == 200
        assert devices.json()["record_count"] >= 1


def test_demo_device_sync_and_profile_update() -> None:
    with TestClient(app) as client:
        assert client.post("/api/demo/reset").status_code == 200
        demo = client.post("/api/demo/device-sync")
        assert demo.status_code == 200
        assert demo.json()["accepted"] >= 1
        current = client.get("/api/profile").json()["profile"]
        current["height_cm"] = 170
        current["lifestyle"]["coffee_cups_per_day"] = 2
        update = client.put("/api/profile", json=current)
        assert update.status_code == 200
        assert update.json()["profile"]["height_cm"] == 170
