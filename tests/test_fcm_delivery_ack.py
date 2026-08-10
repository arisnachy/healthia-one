from __future__ import annotations

import pytest
from pydantic import ValidationError

from healthia_one.fcm_registration import (
    FCMDeliveryAckRequest,
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
    )

    assert acknowledged is not None
    assert acknowledged.last_delivery_proof_id == "fcmproof_12345678"
    assert acknowledged.last_delivery_ack_at is not None
    assert acknowledged.registration_token == original.registration_token
    assert acknowledged.token_sha256 == original.token_sha256


def test_token_refresh_preserves_existing_delivery_ack_until_next_proof():
    store = MemoryFCMRegistrationStore()
    store.save(registration())
    first = store.acknowledge("patient_test", "hc_test_connection", "fcmproof_abcdefgh")
    assert first is not None and first.last_delivery_ack_at is not None

    refreshed = registration("new-fcm-registration-token-0987654321")
    store.save(refreshed)
    reread = store.load("patient_test", "hc_test_connection")

    assert reread is not None
    assert reread.registration_token == "new-fcm-registration-token-0987654321"
    assert reread.last_delivery_proof_id == "fcmproof_abcdefgh"
    assert reread.last_delivery_ack_at == first.last_delivery_ack_at


def test_disabled_registration_cannot_acknowledge_delivery():
    store = MemoryFCMRegistrationStore()
    store.save(registration())
    assert store.disable_connection("patient_test", "hc_test_connection") is True

    assert store.acknowledge("patient_test", "hc_test_connection", "fcmproof_abcdefgh") is None


def test_delivery_ack_request_rejects_content_shaped_or_unsafe_proof_ids():
    valid = FCMDeliveryAckRequest(device_id="android-test-device", proof_id="fcmproof_1234-ABCD")
    assert valid.proof_id == "fcmproof_1234-ABCD"

    with pytest.raises(ValidationError):
        FCMDeliveryAckRequest(device_id="android-test-device", proof_id="patient has chest pain")

    with pytest.raises(ValidationError):
        FCMDeliveryAckRequest(device_id="android-test-device", proof_id="short")
