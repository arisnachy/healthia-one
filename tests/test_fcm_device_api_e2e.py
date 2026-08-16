from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from healthia_one.fcm_device_api import build_fcm_device_router
from healthia_one.fcm_registration import MemoryFCMRegistrationStore
from healthia_one.pairing import DevicePairingManager


class FakeService:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def snapshot(self):
        connections = [] if self.connection is None else [self.connection]
        return SimpleNamespace(device_connections=connections)


def build_client(*, connection_status: str = "connected", connection_present: bool = True):
    pairing = DevicePairingManager(token_secret=b"k" * 32)
    session = pairing.create(patient_id="patient_test")
    claim = pairing.claim(session["code"], "android-test-device", "Controlled Android")
    connection = SimpleNamespace(
        id=claim["connection_id"],
        status=connection_status,
        device_id=claim["device_id"],
    ) if connection_present else None
    store = MemoryFCMRegistrationStore()
    app = FastAPI()
    app.include_router(
        build_fcm_device_router(
            FakeService(connection),
            SimpleNamespace(store_backend="memory"),
            pairing_manager=pairing,
            store=store,
        )
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {claim['access_token']}"}
    return client, headers, store, claim, connection


def test_signed_device_api_enforces_sticky_opt_out_and_explicit_reenable() -> None:
    client, headers, store, claim, _ = build_client()
    device_id = claim["device_id"]

    first = client.post(
        "/api/devices/fcm/register",
        headers=headers,
        json={
            "device_id": device_id,
            "registration_token": "initial-fcm-registration-token-1234567890",
        },
    )
    assert first.status_code == 200
    assert first.json()["registered"] is True
    assert first.json()["notifications_enabled"] is True
    assert first.json()["token_returned"] is False

    disabled = client.delete(f"/api/devices/fcm/register/{device_id}", headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()["unregistered"] is True
    assert disabled.json()["sticky_opt_out"] is True

    tombstone = store.load("patient_test", claim["connection_id"])
    assert tombstone is not None
    assert tombstone.enabled is False
    assert tombstone.registration_token is None
    assert tombstone.token_sha256 is None

    automatic_refresh = client.post(
        "/api/devices/fcm/register",
        headers=headers,
        json={
            "device_id": device_id,
            "registration_token": "automatic-refresh-token-0987654321",
        },
    )
    assert automatic_refresh.status_code == 200
    assert automatic_refresh.json()["registered"] is False
    assert automatic_refresh.json()["notifications_enabled"] is False
    assert automatic_refresh.json()["sticky_opt_out_respected"] is True
    assert automatic_refresh.json()["token_stored_server_side"] is False

    still_disabled = store.load("patient_test", claim["connection_id"])
    assert still_disabled is not None
    assert still_disabled.registration_token is None
    assert still_disabled.token_sha256 is None

    reenabled = client.post(
        "/api/devices/fcm/register/enable",
        headers=headers,
        json={
            "device_id": device_id,
            "registration_token": "explicit-current-fcm-token-1234567890",
            "notifications_opt_in": True,
        },
    )
    assert reenabled.status_code == 200
    assert reenabled.json()["registered"] is True
    assert reenabled.json()["notifications_enabled"] is True
    assert reenabled.json()["explicit_opt_in"] is True
    assert reenabled.json()["token_returned"] is False

    current = store.load("patient_test", claim["connection_id"])
    assert current is not None and current.usable()
    assert current.registration_token == "explicit-current-fcm-token-1234567890"

    hidden_ack = client.post(
        "/api/devices/fcm/ack",
        headers=headers,
        json={
            "device_id": device_id,
            "proof_id": "fcmproof_hidden-1234",
            "notification_shown": False,
        },
    )
    assert hidden_ack.status_code == 200
    assert hidden_ack.json()["acknowledged"] is True
    assert hidden_ack.json()["notification_shown"] is False

    hidden_status = client.get(f"/api/devices/fcm/status/{device_id}", headers=headers)
    assert hidden_status.status_code == 200
    assert hidden_status.json()["registered"] is True
    assert hidden_status.json()["has_delivery_ack"] is True
    assert hidden_status.json()["last_delivery_notification_shown"] is False

    visible_ack = client.post(
        "/api/devices/fcm/ack",
        headers=headers,
        json={
            "device_id": device_id,
            "proof_id": "fcmproof_visible-5678",
            "notification_shown": True,
        },
    )
    assert visible_ack.status_code == 200
    assert visible_ack.json()["notification_shown"] is True

    visible_status = client.get(f"/api/devices/fcm/status/{device_id}", headers=headers)
    assert visible_status.status_code == 200
    assert visible_status.json()["last_delivery_notification_shown"] is True


def test_fresh_signed_device_can_explicitly_opt_in_before_first_health_connect_sync() -> None:
    client, headers, store, claim, _ = build_client(connection_present=False)
    device_id = claim["device_id"]

    response = client.post(
        "/api/devices/fcm/register/enable",
        headers=headers,
        json={
            "device_id": device_id,
            "registration_token": "fresh-pairing-fcm-token-1234567890",
            "notifications_opt_in": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["registered"] is True
    current = store.load("patient_test", claim["connection_id"])
    assert current is not None and current.usable()


def test_signed_bearer_cannot_use_fcm_api_after_device_connection_revocation() -> None:
    client, headers, _, claim, connection = build_client()
    device_id = claim["device_id"]
    connection.status = "disconnected"

    response = client.post(
        "/api/devices/fcm/register/enable",
        headers=headers,
        json={
            "device_id": device_id,
            "registration_token": "explicit-current-fcm-token-1234567890",
            "notifications_opt_in": True,
        },
    )
    assert response.status_code == 401
    assert "revocada" in response.json()["detail"].lower()


def test_fcm_api_rejects_bearer_bound_to_a_different_device_id() -> None:
    client, headers, _, _, _ = build_client()

    response = client.post(
        "/api/devices/fcm/register",
        headers=headers,
        json={
            "device_id": "different-android-device",
            "registration_token": "different-device-fcm-token-1234567890",
        },
    )
    assert response.status_code == 401
