from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.main as main


def test_production_app_exposes_complete_fcm_device_surface() -> None:
    routes = {
        (route.path, method)
        for route in main.app.routes
        for method in (getattr(route, "methods", None) or set())
    }

    expected = {
        ("/api/devices/fcm/register", "POST"),
        ("/api/devices/fcm/register/enable", "POST"),
        ("/api/devices/fcm/ack", "POST"),
        ("/api/devices/fcm/register/{device_id}", "DELETE"),
        ("/api/devices/fcm/status/{device_id}", "GET"),
    }
    assert expected <= routes


def test_readiness_advertises_private_fcm_capability() -> None:
    capability = "fcm_private_notifications"
    route = next(route for route in main.app.routes if route.path == "/api/readiness")
    assert route.endpoint is main.readiness
    # Keep this structural so it never needs a provider credential or billable call.
    assert capability in main.readiness.__code__.co_consts


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
