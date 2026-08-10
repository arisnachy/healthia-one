from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Protocol

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


class FCMDeviceRegistration(BaseModel):
    patient_id: str
    connection_id: str
    device_id: str
    registration_token: str = Field(repr=False)
    token_sha256: str = Field(min_length=64, max_length=64)
    enabled: bool = True
    updated_at: datetime = Field(default_factory=utc_now)


class FCMRegistrationStore(Protocol):
    def save(self, registration: FCMDeviceRegistration) -> None: ...
    def load(self, patient_id: str, connection_id: str) -> FCMDeviceRegistration | None: ...
    def list_active(self, patient_id: str) -> list[FCMDeviceRegistration]: ...
    def disable_connection(self, patient_id: str, connection_id: str) -> bool: ...


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


class MemoryFCMRegistrationStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], FCMDeviceRegistration] = {}

    def save(self, registration: FCMDeviceRegistration) -> None:
        self._values[(registration.patient_id, registration.connection_id)] = registration.model_copy(deep=True)

    def load(self, patient_id: str, connection_id: str) -> FCMDeviceRegistration | None:
        value = self._values.get((patient_id, connection_id))
        return value.model_copy(deep=True) if value else None

    def list_active(self, patient_id: str) -> list[FCMDeviceRegistration]:
        return [
            value.model_copy(deep=True)
            for (owner, _), value in self._values.items()
            if owner == patient_id and value.enabled
        ]

    def disable_connection(self, patient_id: str, connection_id: str) -> bool:
        key = (patient_id, connection_id)
        value = self._values.get(key)
        if value is None:
            return False
        value.enabled = False
        value.updated_at = utc_now()
        self._values[key] = value
        return True


class FirestoreFCMRegistrationStore:
    COLLECTION = "healthia_fcm_registrations"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.client = firestore.Client(project=project)

    def _devices(self, patient_id: str):
        return self.client.collection(self.COLLECTION).document(patient_id).collection("devices")

    def save(self, registration: FCMDeviceRegistration) -> None:
        self._devices(registration.patient_id).document(registration.connection_id).set(
            registration.model_dump(mode="json")
        )

    def load(self, patient_id: str, connection_id: str) -> FCMDeviceRegistration | None:
        snapshot = self._devices(patient_id).document(connection_id).get()
        return FCMDeviceRegistration.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def list_active(self, patient_id: str) -> list[FCMDeviceRegistration]:
        query = self._devices(patient_id).where("enabled", "==", True)
        return [FCMDeviceRegistration.model_validate(item.to_dict()) for item in query.stream()]

    def disable_connection(self, patient_id: str, connection_id: str) -> bool:
        ref = self._devices(patient_id).document(connection_id)
        snapshot = ref.get()
        if not snapshot.exists:
            return False
        ref.set({"enabled": False, "updated_at": utc_now().isoformat()}, merge=True)
        return True


def build_fcm_registration_store(settings) -> FCMRegistrationStore:
    if settings.store_backend == "firestore":
        return FirestoreFCMRegistrationStore(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
    return MemoryFCMRegistrationStore()
