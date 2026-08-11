from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FCMDeviceRegistrationRequest(BaseModel):
    device_id: str = Field(min_length=3, max_length=240)
    registration_token: str = Field(min_length=16, max_length=4096)

    @field_validator("registration_token")
    @classmethod
    def validate_registration_token(cls, value: str) -> str:
        token = str(value or "").strip()
        if not token or any(ch.isspace() for ch in token):
            raise ValueError("FCM registration token is invalid")
        return token


class FCMDeviceReenableRequest(FCMDeviceRegistrationRequest):
    notifications_opt_in: Literal[True]


class FCMDeliveryAckRequest(BaseModel):
    device_id: str = Field(min_length=3, max_length=240)
    proof_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    notification_shown: bool


class FCMDeviceRegistration(BaseModel):
    patient_id: str
    connection_id: str
    device_id: str
    registration_token: str | None = Field(default=None, repr=False)
    token_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    enabled: bool = True
    updated_at: datetime = Field(default_factory=utc_now)
    last_delivery_proof_id: str | None = Field(default=None, min_length=8, max_length=128)
    last_delivery_ack_at: datetime | None = None
    last_delivery_notification_shown: bool | None = None

    def usable(self) -> bool:
        return bool(self.enabled and self.registration_token and self.token_sha256)


class FCMRegistrationStore(Protocol):
    def save(self, registration: FCMDeviceRegistration, *, allow_reenable: bool = False) -> None: ...
    def load(self, patient_id: str, connection_id: str) -> FCMDeviceRegistration | None: ...
    def list_active(self, patient_id: str) -> list[FCMDeviceRegistration]: ...
    def disable_connection(self, patient_id: str, connection_id: str) -> bool: ...
    def acknowledge(
        self,
        patient_id: str,
        connection_id: str,
        proof_id: str,
        notification_shown: bool,
    ) -> FCMDeviceRegistration | None: ...


def build_registration(*, patient_id: str, connection_id: str, device_id: str, registration_token: str) -> FCMDeviceRegistration:
    token = str(registration_token or "").strip()
    if len(token) < 16 or len(token) > 4096 or any(ch.isspace() for ch in token):
        raise ValueError("FCM registration token is invalid")
    return FCMDeviceRegistration(
        patient_id=str(patient_id),
        connection_id=str(connection_id),
        device_id=str(device_id),
        registration_token=token,
        token_sha256=hashlib.sha256(token.encode("utf-8")).hexdigest(),
    )


def _merged_registration(
    existing: FCMDeviceRegistration | None,
    registration: FCMDeviceRegistration,
    *,
    allow_reenable: bool,
) -> FCMDeviceRegistration | None:
    """Return a value that cannot bypass a sticky user notification opt-out."""

    if existing is not None and not existing.enabled and not allow_reenable:
        return None
    if not registration.registration_token or not registration.token_sha256:
        raise ValueError("Enabled FCM registration requires token material")

    value = registration.model_copy(deep=True)
    value.enabled = True
    if existing is not None and value.last_delivery_proof_id is None:
        value.last_delivery_proof_id = existing.last_delivery_proof_id
        value.last_delivery_ack_at = existing.last_delivery_ack_at
        value.last_delivery_notification_shown = existing.last_delivery_notification_shown
    return value


class MemoryFCMRegistrationStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], FCMDeviceRegistration] = {}

    def save(self, registration: FCMDeviceRegistration, *, allow_reenable: bool = False) -> None:
        key = (registration.patient_id, registration.connection_id)
        existing = self._values.get(key)
        value = _merged_registration(existing, registration, allow_reenable=allow_reenable)
        if value is None:
            return
        self._values[key] = value

    def load(self, patient_id: str, connection_id: str) -> FCMDeviceRegistration | None:
        value = self._values.get((patient_id, connection_id))
        return value.model_copy(deep=True) if value else None

    def list_active(self, patient_id: str) -> list[FCMDeviceRegistration]:
        return [
            value.model_copy(deep=True)
            for (owner, _), value in self._values.items()
            if owner == patient_id and value.usable()
        ]

    def disable_connection(self, patient_id: str, connection_id: str) -> bool:
        key = (patient_id, connection_id)
        value = self._values.get(key)
        if value is None:
            return False
        value.enabled = False
        value.registration_token = None
        value.token_sha256 = None
        value.updated_at = utc_now()
        self._values[key] = value
        return True

    def acknowledge(
        self,
        patient_id: str,
        connection_id: str,
        proof_id: str,
        notification_shown: bool,
    ) -> FCMDeviceRegistration | None:
        key = (patient_id, connection_id)
        value = self._values.get(key)
        if value is None or not value.usable():
            return None
        value.last_delivery_proof_id = str(proof_id)
        value.last_delivery_ack_at = utc_now()
        value.last_delivery_notification_shown = bool(notification_shown)
        value.updated_at = value.last_delivery_ack_at
        self._values[key] = value
        return value.model_copy(deep=True)


class FirestoreFCMRegistrationStore:
    COLLECTION = "healthia_fcm_registrations"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.firestore = firestore
        self.client = firestore.Client(project=project)

    def _devices(self, patient_id: str):
        return self.client.collection(self.COLLECTION).document(patient_id).collection("devices")

    def save(self, registration: FCMDeviceRegistration, *, allow_reenable: bool = False) -> None:
        ref = self._devices(registration.patient_id).document(registration.connection_id)
        transaction = self.client.transaction()

        @self.firestore.transactional
        def persist(txn):
            snapshot = ref.get(transaction=txn)
            existing = FCMDeviceRegistration.model_validate(snapshot.to_dict()) if snapshot.exists else None
            value = _merged_registration(existing, registration, allow_reenable=allow_reenable)
            if value is None:
                return
            txn.set(ref, value.model_dump(mode="json", exclude_none=True), merge=True)

        persist(transaction)

    def load(self, patient_id: str, connection_id: str) -> FCMDeviceRegistration | None:
        snapshot = self._devices(patient_id).document(connection_id).get()
        return FCMDeviceRegistration.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def list_active(self, patient_id: str) -> list[FCMDeviceRegistration]:
        query = self._devices(patient_id).where("enabled", "==", True)
        values = [FCMDeviceRegistration.model_validate(item.to_dict()) for item in query.stream()]
        return [value for value in values if value.usable()]

    def disable_connection(self, patient_id: str, connection_id: str) -> bool:
        ref = self._devices(patient_id).document(connection_id)
        transaction = self.client.transaction()

        @self.firestore.transactional
        def disable(txn):
            snapshot = ref.get(transaction=txn)
            if not snapshot.exists:
                return False
            txn.update(
                ref,
                {
                    "enabled": False,
                    "registration_token": self.firestore.DELETE_FIELD,
                    "token_sha256": self.firestore.DELETE_FIELD,
                    "updated_at": utc_now().isoformat(),
                },
            )
            return True

        return bool(disable(transaction))

    def acknowledge(
        self,
        patient_id: str,
        connection_id: str,
        proof_id: str,
        notification_shown: bool,
    ) -> FCMDeviceRegistration | None:
        ref = self._devices(patient_id).document(connection_id)
        snapshot = ref.get()
        if not snapshot.exists:
            return None
        current = FCMDeviceRegistration.model_validate(snapshot.to_dict())
        if not current.usable():
            return None
        acknowledged_at = utc_now()
        ref.set(
            {
                "last_delivery_proof_id": str(proof_id),
                "last_delivery_ack_at": acknowledged_at.isoformat(),
                "last_delivery_notification_shown": bool(notification_shown),
                "updated_at": acknowledged_at.isoformat(),
            },
            merge=True,
        )
        current.last_delivery_proof_id = str(proof_id)
        current.last_delivery_ack_at = acknowledged_at
        current.last_delivery_notification_shown = bool(notification_shown)
        current.updated_at = acknowledged_at
        return current


def build_fcm_registration_store(settings) -> FCMRegistrationStore:
    if settings.store_backend == "firestore":
        return FirestoreFCMRegistrationStore(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
    return MemoryFCMRegistrationStore()
