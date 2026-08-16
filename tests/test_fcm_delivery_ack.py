from __future__ import annotations

import pytest
from pydantic import ValidationError

from healthia_one.fcm_registration import (
    FCMDeliveryAckRequest,
    FCMDeviceReenableRequest,
    MemoryFCMRegistrationStore,
    build_registration,
)


def registration(token: str = "fcm-registration-token-1234567890"):
    return build_registration(
        patient_id="patient_test",
        connection_id="hc_test_connection",
        device_id="android-test-device",
        registration_token=token,
    )


def test_memory_store_records_phi_neutral_delivery_ack_without_exposing_token():
    store = MemoryFCMRegistrationStore()
    original = registration()
    store.save(original)

    acknowledged = store.acknowledge(
        "patient_test",
        "hc_test_connection",
        "fcmproof_12345678",
        True,
    )

    assert acknowledged is not None
    assert acknowledged.last_delivery_proof_id == "fcmproof_12345678"
    assert acknowledged.last_delivery_ack_at is not None
    assert acknowledged.last_delivery_notification_shown is True
    assert acknowledged.registration_token == original.registration_token
    assert acknowledged.token_sha256 == original.token_sha256


def test_ack_can_record_delivery_without_visible_notification_without_mislabeling_it():
    store = MemoryFCMRegistrationStore()
    store.save(registration())

    acknowledged = store.acknowledge(
        "patient_test",
        "hc_test_connection",
        "fcmproof_hidden123",
        False,
    )

    assert acknowledged is not None
    assert acknowledged.last_delivery_proof_id == "fcmproof_hidden123"
    assert acknowledged.last_delivery_ack_at is not None
    assert acknowledged.last_delivery_notification_shown is False


def test_token_refresh_preserves_existing_delivery_ack_until_next_proof():
    store = MemoryFCMRegistrationStore()
    store.save(registration())
    first = store.acknowledge("patient_test", "hc_test_connection", "fcmproof_abcdefgh", True)
    assert first is not None and first.last_delivery_ack_at is not None

    refreshed = registration("new-fcm-registration-token-0987654321")
    store.save(refreshed)
    reread = store.load("patient_test", "hc_test_connection")

    assert reread is not None
    assert reread.registration_token == "new-fcm-registration-token-0987654321"
    assert reread.last_delivery_proof_id == "fcmproof_abcdefgh"
    assert reread.last_delivery_ack_at == first.last_delivery_ack_at
    assert reread.last_delivery_notification_shown is True


def test_disabled_registration_erases_token_material_and_cannot_acknowledge():
    store = MemoryFCMRegistrationStore()
    store.save(registration())
    assert store.disable_connection("patient_test", "hc_test_connection") is True

    tombstone = store.load("patient_test", "hc_test_connection")
    assert tombstone is not None
    assert tombstone.enabled is False
    assert tombstone.registration_token is None
    assert tombstone.token_sha256 is None
    assert tombstone.usable() is False
    assert store.acknowledge("patient_test", "hc_test_connection", "fcmproof_abcdefgh", True) is None


def test_automatic_token_refresh_cannot_override_privacy_tombstone():
    store = MemoryFCMRegistrationStore()
    store.save(registration())
    assert store.disable_connection("patient_test", "hc_test_connection") is True

    automatic_refresh = registration("automatic-refresh-token-0987654321")
    store.save(automatic_refresh)
    reread = store.load("patient_test", "hc_test_connection")

    assert reread is not None
    assert reread.enabled is False
    assert reread.registration_token is None
    assert reread.token_sha256 is None
    assert reread.usable() is False
    assert store.list_active("patient_test") == []


def test_explicit_notification_opt_in_rehydrates_tombstone_with_current_token():
    store = MemoryFCMRegistrationStore()
    store.save(registration())
    assert store.disable_connection("patient_test", "hc_test_connection") is True

    current = registration("explicit-opt-in-current-token-123456")
    store.save(current, allow_reenable=True)
    reread = store.load("patient_test", "hc_test_connection")

    assert reread is not None
    assert reread.enabled is True
    assert reread.usable() is True
    assert reread.registration_token == "explicit-opt-in-current-token-123456"
    assert reread.token_sha256 is not None
    assert len(store.list_active("patient_test")) == 1


def test_reenable_request_requires_literal_true_opt_in():
    valid = FCMDeviceReenableRequest(
        device_id="android-test-device",
        registration_token="fcm-registration-token-1234567890",
        notifications_opt_in=True,
    )
    assert valid.notifications_opt_in is True

    with pytest.raises(ValidationError):
        FCMDeviceReenableRequest(
            device_id="android-test-device",
            registration_token="fcm-registration-token-1234567890",
            notifications_opt_in=False,
        )


def test_delivery_ack_request_requires_notification_visibility_and_safe_proof_id():
    valid = FCMDeliveryAckRequest(
        device_id="android-test-device",
        proof_id="fcmproof_1234-ABCD",
        notification_shown=True,
    )
    assert valid.proof_id == "fcmproof_1234-ABCD"
    assert valid.notification_shown is True

    with pytest.raises(ValidationError):
        FCMDeliveryAckRequest(device_id="android-test-device", proof_id="fcmproof_1234-ABCD")

    with pytest.raises(ValidationError):
        FCMDeliveryAckRequest(
            device_id="android-test-device",
            proof_id="patient has chest pain",
            notification_shown=True,
        )

    with pytest.raises(ValidationError):
        FCMDeliveryAckRequest(
            device_id="android-test-device",
            proof_id="short",
            notification_shown=True,
        )
