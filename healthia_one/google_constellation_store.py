from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field

from healthia_one.google_constellation import (
    GoogleAction,
    GoogleActionReceipt,
    GoogleGrant,
    new_id,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GoogleActionAuthorization(BaseModel):
    id: str = Field(default_factory=lambda: new_id("gauth"))
    patient_id: str
    mission_id: str
    action: GoogleAction
    enabled: bool = True
    one_time: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    consumed_at: datetime | None = None

    def usable_for(self, *, patient_id: str, mission_id: str, action: GoogleAction, now: datetime | None = None) -> bool:
        now = now or utc_now()
        if not self.enabled:
            return False
        if self.patient_id != patient_id or self.mission_id != mission_id or self.action != action:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        if self.one_time and self.consumed_at is not None:
            return False
        return True


class GoogleGrantStore(Protocol):
    def list_for_patient(self, patient_id: str) -> list[GoogleGrant]: ...
    def save(self, grant: GoogleGrant) -> None: ...


class GoogleReceiptStore(Protocol):
    def get(self, patient_id: str, idempotency_key: str) -> GoogleActionReceipt | None: ...
    def save(self, receipt: GoogleActionReceipt) -> None: ...


class GoogleAuthorizationStore(Protocol):
    def get(self, patient_id: str, authorization_id: str) -> GoogleActionAuthorization | None: ...
    def save(self, authorization: GoogleActionAuthorization) -> None: ...
    def consume(self, patient_id: str, authorization_id: str) -> GoogleActionAuthorization: ...


class MemoryGoogleGrantStore:
    def __init__(self) -> None:
        self._values: dict[str, dict[str, GoogleGrant]] = {}

    def list_for_patient(self, patient_id: str) -> list[GoogleGrant]:
        return [item.model_copy(deep=True) for item in self._values.get(patient_id, {}).values()]

    def save(self, grant: GoogleGrant) -> None:
        self._values.setdefault(grant.patient_id, {})[grant.id] = grant.model_copy(deep=True)


class MemoryGoogleReceiptStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], GoogleActionReceipt] = {}

    def get(self, patient_id: str, idempotency_key: str) -> GoogleActionReceipt | None:
        value = self._values.get((patient_id, idempotency_key))
        return value.model_copy(deep=True) if value else None

    def save(self, receipt: GoogleActionReceipt) -> None:
        self._values[(receipt.patient_id, receipt.idempotency_key)] = receipt.model_copy(deep=True)


class MemoryGoogleAuthorizationStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], GoogleActionAuthorization] = {}

    def get(self, patient_id: str, authorization_id: str) -> GoogleActionAuthorization | None:
        value = self._values.get((patient_id, authorization_id))
        return value.model_copy(deep=True) if value else None

    def save(self, authorization: GoogleActionAuthorization) -> None:
        self._values[(authorization.patient_id, authorization.id)] = authorization.model_copy(deep=True)

    def consume(self, patient_id: str, authorization_id: str) -> GoogleActionAuthorization:
        value = self._values.get((patient_id, authorization_id))
        if value is None:
            raise KeyError(authorization_id)
        if value.one_time:
            if value.consumed_at is not None:
                raise PermissionError("Google action authorization was already consumed")
            value.consumed_at = utc_now()
        self._values[(patient_id, authorization_id)] = value
        return value.model_copy(deep=True)


class FirestoreGoogleGrantStore:
    COLLECTION = "healthia_google_grants"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore
        self.client = firestore.Client(project=project)

    def _collection(self, patient_id: str):
        return self.client.collection(self.COLLECTION).document(patient_id).collection("grants")

    def list_for_patient(self, patient_id: str) -> list[GoogleGrant]:
        result: list[GoogleGrant] = []
        for snapshot in self._collection(patient_id).stream():
            raw = snapshot.to_dict() or {}
            if raw:
                result.append(GoogleGrant.model_validate(raw))
        return result

    def save(self, grant: GoogleGrant) -> None:
        self._collection(grant.patient_id).document(grant.id).set(grant.model_dump(mode="json"))


class FirestoreGoogleReceiptStore:
    COLLECTION = "healthia_google_action_receipts"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore
        self.client = firestore.Client(project=project)

    def _doc(self, patient_id: str, idempotency_key: str):
        return self.client.collection(self.COLLECTION).document(patient_id).collection("receipts").document(idempotency_key)

    def get(self, patient_id: str, idempotency_key: str) -> GoogleActionReceipt | None:
        snapshot = self._doc(patient_id, idempotency_key).get()
        return GoogleActionReceipt.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, receipt: GoogleActionReceipt) -> None:
        self._doc(receipt.patient_id, receipt.idempotency_key).set(receipt.model_dump(mode="json"))


class FirestoreGoogleAuthorizationStore:
    COLLECTION = "healthia_google_action_authorizations"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore
        self.firestore = firestore
        self.client = firestore.Client(project=project)

    def _doc(self, patient_id: str, authorization_id: str):
        return self.client.collection(self.COLLECTION).document(patient_id).collection("authorizations").document(authorization_id)

    def get(self, patient_id: str, authorization_id: str) -> GoogleActionAuthorization | None:
        snapshot = self._doc(patient_id, authorization_id).get()
        return GoogleActionAuthorization.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, authorization: GoogleActionAuthorization) -> None:
        self._doc(authorization.patient_id, authorization.id).set(authorization.model_dump(mode="json"))

    def consume(self, patient_id: str, authorization_id: str) -> GoogleActionAuthorization:
        ref = self._doc(patient_id, authorization_id)
        transaction = self.client.transaction()

        @self.firestore.transactional
        def _consume(tx):
            snapshot = ref.get(transaction=tx)
            if not snapshot.exists:
                raise KeyError(authorization_id)
            authorization = GoogleActionAuthorization.model_validate(snapshot.to_dict())
            if authorization.one_time:
                if authorization.consumed_at is not None:
                    raise PermissionError("Google action authorization was already consumed")
                authorization.consumed_at = utc_now()
                tx.set(ref, authorization.model_dump(mode="json"))
            return authorization

        return _consume(transaction)
