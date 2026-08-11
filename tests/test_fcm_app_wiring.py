from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main


ROOT = Path(__file__).resolve().parents[1]


def _assert_device_bearer_boundary(response) -> None:
    assert response.status_code == 401
    assert "dispositivo" in response.json()["detail"].lower()


def test_production_app_exposes_complete_fcm_device_surface_over_http() -> None:
    """A missing route would return 404; the real mounted router must return its 401 bearer gate."""

    with TestClient(main.app) as client:
        _assert_device_bearer_boundary(
            client.post(
                "/api/devices/fcm/register",
                json={
                    "device_id": "android-test-device",
                    "registration_token": "fcm-registration-token-1234567890",
                },
            )
        )
        _assert_device_bearer_boundary(
            client.post(
                "/api/devices/fcm/register/enable",
                json={
                    "device_id": "android-test-device",
                    "registration_token": "fcm-registration-token-1234567890",
                    "notifications_opt_in": True,
                },
            )
        )
        _assert_device_bearer_boundary(
            client.post(
                "/api/devices/fcm/ack",
                json={
                    "device_id": "android-test-device",
                    "proof_id": "fcmproof_http-1234",
                    "notification_shown": True,
                },
            )
        )
        _assert_device_bearer_boundary(
            client.delete("/api/devices/fcm/register/android-test-device")
        )
        _assert_device_bearer_boundary(
            client.get("/api/devices/fcm/status/android-test-device")
        )


def test_fcm_router_has_one_production_mount_and_auth_keeps_only_session_exception() -> None:
    main_source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    auth_source = (ROOT / "healthia_one/auth_web.py").read_text(encoding="utf-8")

    assert main_source.count("build_fcm_device_router(") == 1
    assert "pairing_manager=pairing_manager" in main_source
    assert "store=fcm_registration_store" in main_source
    assert "build_fcm_device_router" not in auth_source
    assert 'path.startswith("/api/devices/fcm/")' in auth_source


def test_readiness_advertises_private_fcm_capability_over_http() -> None:
    with TestClient(main.app) as client:
        response = client.get("/api/readiness")

    assert response.status_code == 200
    assert "fcm_private_notifications" in response.json()["capabilities"]


@pytest.mark.asyncio
async def test_disconnect_device_tombstones_shared_fcm_registration(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeService:
        async def snapshot(self):
            return SimpleNamespace(profile=SimpleNamespace(id="patient_test"))

        async def disconnect_device(self, connection_id: str) -> bool:
            return connection_id == "hc_controlled"

    class FakeStore:
        def disable_connection(self, patient_id: str, connection_id: str) -> bool:
            calls.append((patient_id, connection_id))
            return True

    monkeypatch.setattr(main, "service", FakeService())
    monkeypatch.setattr(main, "fcm_registration_store", FakeStore())

    result = await main.disconnect_device("hc_controlled")

    assert result == {
        "disconnected": True,
        "connection_id": "hc_controlled",
        "fcm_tombstoned": True,
    }
    assert calls == [("patient_test", "hc_controlled")]


@pytest.mark.asyncio
async def test_unknown_disconnect_does_not_touch_fcm_store(monkeypatch) -> None:
    touched = False

    class FakeService:
        async def snapshot(self):
            return SimpleNamespace(profile=SimpleNamespace(id="patient_test"))

        async def disconnect_device(self, connection_id: str) -> bool:
            return False

    class FakeStore:
        def disable_connection(self, patient_id: str, connection_id: str) -> bool:
            nonlocal touched
            touched = True
            return True

    monkeypatch.setattr(main, "service", FakeService())
    monkeypatch.setattr(main, "fcm_registration_store", FakeStore())

    with pytest.raises(main.HTTPException) as exc:
        await main.disconnect_device("missing")

    assert exc.value.status_code == 404
    assert touched is False
