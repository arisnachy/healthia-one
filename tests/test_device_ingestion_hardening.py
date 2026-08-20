from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from healthia_one.deterministic_router import respond
from healthia_one.models import DeviceObservation
from healthia_one.service import seed_state


def observation(**overrides) -> DeviceObservation:
    payload = {
        "external_id": "measurement-1",
        "metric": "heart_rate",
        "observed_at": datetime.now(timezone.utc),
        "value": 72,
        "unit": "bpm",
        "source_package": "com.example.health",
    }
    payload.update(overrides)
    return DeviceObservation(**payload)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"unit": "kg"}, "unsupported unit"),
        ({"value": 900}, "outside supported range"),
        ({"observed_at": datetime.now(timezone.utc) + timedelta(hours=1)}, "too far in the future"),
        ({"secondary_value": 60}, "only supported for blood pressure"),
    ],
)
def test_device_observation_rejects_unsafe_measurements(overrides, message) -> None:
    with pytest.raises(ValidationError, match=message):
        observation(**overrides)


def test_blood_pressure_requires_a_plausible_ordered_pair() -> None:
    with pytest.raises(ValidationError, match="greater than diastolic"):
        observation(metric="blood_pressure", value=70, secondary_value=120, unit="mmHg")


def test_patient_can_revoke_device_connection_and_block_reuse() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        pairing = client.post("/api/devices/pairing").json()
        claim = client.post(
            "/api/devices/pairing/claim",
            json={"code": pairing["code"], "device_id": "revocable-phone", "display_name": "Phone"},
        ).json()
        payload = {
            "device_id": "revocable-phone",
            "granted_metrics": ["heart_rate"],
            "records": [
                {
                    "external_id": "pulse-1",
                    "metric": "heart_rate",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "value": 72,
                    "unit": "bpm",
                }
            ],
        }
        headers = {"Authorization": f"Bearer {claim['access_token']}"}
        first = client.post("/api/devices/health-connect/sync", headers=headers, json=payload)
        assert first.status_code == 200
        assert first.json()["granted_metrics"] == ["heart_rate"]
        assert first.json()["transport_identity_verified"] is True
        assert first.json()["clinical_source_verified"] is False
        connection_id = first.json()["connection_id"]

        revoked = client.delete(f"/api/devices/{connection_id}")
        assert revoked.status_code == 200

        payload["records"][0]["external_id"] = "pulse-2"
        reused = client.post("/api/devices/health-connect/sync", headers=headers, json=payload)
        assert reused.status_code == 401
        assert "revocada" in reused.json()["detail"]


def test_patient_can_revoke_claimed_device_before_first_sync() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        pairing = client.post("/api/devices/pairing").json()
        claim = client.post(
            "/api/devices/pairing/claim",
            json={"code": pairing["code"], "device_id": "never-synced-phone", "display_name": "Phone"},
        ).json()
        revoked = client.delete(f"/api/devices/{claim['connection_id']}")
        assert revoked.status_code == 200

        sync = client.post(
            "/api/devices/health-connect/sync",
            headers={"Authorization": f"Bearer {claim['access_token']}"},
            json={
                "device_id": "never-synced-phone",
                "granted_metrics": ["heart_rate"],
                "records": [{
                    "external_id": "must-stay-revoked",
                    "metric": "heart_rate",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "value": 72,
                    "unit": "bpm",
                }],
            },
        )
        assert sync.status_code == 401
        assert "revocada" in sync.json()["detail"]


def test_repaired_phone_uses_a_new_connection_after_revocation() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        first_pairing = client.post("/api/devices/pairing").json()
        first_claim = client.post(
            "/api/devices/pairing/claim",
            json={"code": first_pairing["code"], "device_id": "repaired-phone", "display_name": "Phone"},
        ).json()
        payload = {
            "device_id": "repaired-phone",
            "granted_metrics": ["heart_rate"],
            "records": [{
                "external_id": "before-repair",
                "metric": "heart_rate",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "value": 72,
                "unit": "bpm",
            }],
        }
        first = client.post(
            "/api/devices/health-connect/sync",
            headers={"Authorization": f"Bearer {first_claim['access_token']}"},
            json=payload,
        ).json()
        client.delete(f"/api/devices/{first['connection_id']}").raise_for_status()

        second_pairing = client.post("/api/devices/pairing").json()
        second_claim = client.post(
            "/api/devices/pairing/claim",
            json={"code": second_pairing["code"], "device_id": "repaired-phone", "display_name": "Phone"},
        ).json()
        payload["records"][0]["external_id"] = "after-repair"
        repaired = client.post(
            "/api/devices/health-connect/sync",
            headers={"Authorization": f"Bearer {second_claim['access_token']}"},
            json=payload,
        )
        assert repaired.status_code == 200
        assert repaired.json()["connection_id"] != first["connection_id"]


@pytest.mark.parametrize("granted_metrics", [[], ["steps"]])
def test_authenticated_sync_rejects_records_outside_declared_permissions(granted_metrics) -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        pairing = client.post("/api/devices/pairing").json()
        claim = client.post(
            "/api/devices/pairing/claim",
            json={"code": pairing["code"], "device_id": "permission-phone", "display_name": "Phone"},
        ).json()
        response = client.post(
            "/api/devices/health-connect/sync",
            headers={"Authorization": f"Bearer {claim['access_token']}"},
            json={
                "device_id": "permission-phone",
                "granted_metrics": granted_metrics,
                "records": [{
                    "external_id": "unauthorized-pulse",
                    "metric": "heart_rate",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "value": 72,
                    "unit": "bpm",
                }],
            },
        )
        assert response.status_code == 422


def test_server_side_consent_blocks_device_metric_after_revocation() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        pairing = client.post("/api/devices/pairing").json()
        claim = client.post(
            "/api/devices/pairing/claim",
            json={"code": pairing["code"], "device_id": "consent-phone", "display_name": "Phone"},
        ).json()
        consent = client.get("/api/consent").json()
        consent["signal_types"] = [item for item in consent["signal_types"] if item != "device_data"]
        client.put("/api/consent", json=consent).raise_for_status()

        response = client.post(
            "/api/devices/health-connect/sync",
            headers={"Authorization": f"Bearer {claim['access_token']}"},
            json={
                "device_id": "consent-phone",
                "granted_metrics": ["heart_rate"],
                "records": [{
                    "external_id": "revoked-heart-rate",
                    "metric": "heart_rate",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "value": 72,
                    "unit": "bpm",
                }],
            },
        )
        assert response.status_code == 403
        assert "consentimiento vigente" in response.json()["detail"]


def test_profile_write_cannot_restore_canonical_consent_projection() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        consent = client.get("/api/consent").json()
        consent["signal_types"] = [item for item in consent["signal_types"] if item != "device_data"]
        client.put("/api/consent", json=consent).raise_for_status()

        profile = client.get("/api/profile").json()["profile"]
        profile["consented_signal_types"].append("device_data")
        updated = client.put("/api/profile", json=profile)
        assert updated.status_code == 200
        assert "device_data" not in updated.json()["profile"]["consented_signal_types"]


def test_revocation_check_occurs_inside_service_mutation_lock() -> None:
    source = open("healthia_one/service.py", encoding="utf-8").read()
    lock_offset = source.index("async with self._mutation_lock", source.index("async def ingest_health_connect"))
    check_offset = source.index("if authorized_connection_id", lock_offset)
    ingest_offset = source.index("ingest_health_connect_batch", check_offset)
    assert lock_offset < check_offset < ingest_offset


def test_android_bridge_reads_only_granted_metric_types() -> None:
    source = open(
        "android-health-bridge/app/src/main/java/com/healthia/one/bridge/HealthConnectRepository.kt",
        encoding="utf-8",
    ).read()
    worker = open(
        "android-health-bridge/app/src/main/java/com/healthia/one/bridge/HealthSyncWorker.kt",
        encoding="utf-8",
    ).read()
    api = open(
        "android-health-bridge/app/src/main/java/com/healthia/one/bridge/HealthiaApi.kt",
        encoding="utf-8",
    ).read()
    assert "grantedMetricNames" in source
    assert 'metricPermissions.getValue("steps") in granted' in source
    assert "missing.isEmpty()" not in source
    assert "grantedMetrics.isEmpty()" in worker
    assert 'put("granted_metrics"' in api


def test_urgent_device_reading_creates_deterministic_human_review_alert() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        pairing = client.post("/api/devices/pairing").json()
        claim = client.post(
            "/api/devices/pairing/claim",
            json={"code": pairing["code"], "device_id": "safety-phone", "display_name": "Safety phone"},
        ).json()
        response = client.post(
            "/api/devices/health-connect/sync",
            headers={"Authorization": f"Bearer {claim['access_token']}"},
            json={
                "device_id": "safety-phone",
                "granted_metrics": ["oxygen_saturation"],
                "records": [
                    {
                        "external_id": "spo2-low-1",
                        "metric": "oxygen_saturation",
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        "value": 85,
                        "unit": "%",
                    }
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["safety_alerts"][0]["risk_level"] == "urgent"
        latest = client.get("/api/bootstrap").json()["messages"][-1]
        assert latest["metadata"]["device_safety_alert"] is True
        assert latest["metadata"]["requires_human_review"] is True
        assert latest["metadata"]["clinical_source_verified"] is False


def test_main_chat_routes_device_requests_to_real_device_view() -> None:
    response = respond(seed_state(), "Quiero conectar mi reloj y revisar Health Connect")
    assert response.message.metadata["action_target"] == "devices"
    assert response.mission is not None
    assert response.mission.mission_type == "device_connection"
    assert "Dispositivos" in response.message.content


def test_synthetic_device_path_does_not_claim_authenticated_transport() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        result = client.post("/api/demo/device-sync")
        assert result.status_code == 200
        assert result.json()["transport_identity_verified"] is False
