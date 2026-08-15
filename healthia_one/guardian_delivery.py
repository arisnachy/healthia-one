from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from urllib import parse

from pydantic import BaseModel, Field

from healthia_one.config import Settings
from healthia_one.fcm_registration import FCMRegistrationStore, build_fcm_registration_store
from healthia_one.google_clinical_cloud_connectors import FCMConnector
from healthia_one.google_connector_runtime import ConnectorResult, GoogleConnectorError
from healthia_one.google_constellation import GoogleAction
from healthia_one.models import PatientState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GuardianDeliveryReceipt(BaseModel):
    id: str
    patient_id: str
    mission_id: str
    event_id: str
    channel: Literal["fcm"] = "fcm"
    connection_id: str
    status: Literal["completed", "failed"]
    provider_resource_id: str = ""
    proof_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    safe_summary: str = ""


class GuardianDeliveryStore(Protocol):
    def get(self, patient_id: str, receipt_id: str) -> GuardianDeliveryReceipt | None: ...
    def save(self, receipt: GuardianDeliveryReceipt) -> None: ...


class MemoryGuardianDeliveryStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], GuardianDeliveryReceipt] = {}

    def get(self, patient_id: str, receipt_id: str) -> GuardianDeliveryReceipt | None:
        value = self._values.get((patient_id, receipt_id))
        return value.model_copy(deep=True) if value else None

    def save(self, receipt: GuardianDeliveryReceipt) -> None:
        self._values[(receipt.patient_id, receipt.id)] = receipt.model_copy(deep=True)


class FirestoreGuardianDeliveryStore:
    COLLECTION = "healthia_guardian_delivery_receipts"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.client = firestore.Client(project=project)

    def _doc(self, patient_id: str, receipt_id: str):
        return self.client.collection(self.COLLECTION).document(patient_id).collection("receipts").document(receipt_id)

    def get(self, patient_id: str, receipt_id: str) -> GuardianDeliveryReceipt | None:
        snapshot = self._doc(patient_id, receipt_id).get()
        return GuardianDeliveryReceipt.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, receipt: GuardianDeliveryReceipt) -> None:
        self._doc(receipt.patient_id, receipt.id).set(receipt.model_dump(mode="json"))


def build_guardian_delivery_store(settings: Settings) -> GuardianDeliveryStore:
    if settings.store_backend == "firestore":
        return FirestoreGuardianDeliveryStore(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
    return MemoryGuardianDeliveryStore()


def _receipt_id(event_id: str, connection_id: str) -> str:
    raw = f"{event_id}|fcm|{connection_id}"
    return "gdelivery_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]


def _proof_id(receipt_id: str) -> str:
    return "guardian:" + hashlib.sha256(receipt_id.encode("utf-8")).hexdigest()[:32]


class GuardianFCMConnector(FCMConnector):
    """FCM data-message variant aligned with the controlled Android bridge.

    It sends no clinical copy. Android renders the neutral local notification and
    acknowledges the stable proof id. This preserves the existing controlled-device
    proof contract and lets the client suppress a repeated visible notification.
    """

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action != GoogleAction.FCM_SEND_MISSION_NOTIFICATION:
            raise GoogleConnectorError(f"Unsupported Guardian FCM action: {action}")
        if not self.project_id:
            raise GoogleConnectorError("GOOGLE_CLOUD_PROJECT is required for Guardian FCM")
        token = str(payload.get("device_token") or "").strip()
        mission_id = str(payload.get("mission_id") or "").strip()
        proof_id = str(payload.get("proof_id") or "").strip()
        event_type = str(payload.get("event_type") or "guardian_update").strip()[:80]
        if not token or not mission_id or not proof_id:
            raise GoogleConnectorError("Guardian FCM requires device token, mission id and proof id")
        if len(proof_id) not in range(8, 129) or any(not (ch.isalnum() or ch in "._:-") for ch in proof_id):
            raise GoogleConnectorError("Guardian FCM proof id is invalid")

        body = {
            "message": {
                "token": token,
                "data": {
                    "kind": "healthia_update",
                    "proof_id": proof_id,
                    "mission_id": mission_id,
                    "event_type": event_type,
                    "open_view": "missions",
                },
                "android": {"priority": "HIGH"},
            }
        }
        result = self.transport.call(
            "POST",
            f"https://fcm.googleapis.com/v1/projects/{parse.quote(self.project_id, safe='')}/messages:send",
            headers=self._headers(fcm=True),
            body=body,
        )
        name = str(result.get("name") or "")
        if not name:
            raise GoogleConnectorError("FCM provider did not return a message resource")
        return ConnectorResult(
            resource_id=name,
            safe_summary="Sent one PHI-neutral Guardian data notification through FCM.",
            data={"message_name": name, "proof_id": proof_id},
            external_mutation=True,
        )


class GuardianPushDispatcher:
    """Deliver one PHI-neutral Guardian wake-up notification per active device.

    The patient's FCM registration is already a sticky explicit opt-in. Guardian
    adds a second patient-level signal flag (`guardian_push`) before it will send.
    Provider delivery is at-least-once: Firestore/Eventarc can redeliver after a
    process crash. The stable proof id therefore travels to Android, where the
    client suppresses a repeated visible notification for the same proof.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        registrations: FCMRegistrationStore | None = None,
        receipts: GuardianDeliveryStore | None = None,
        connector: FCMConnector | None = None,
    ) -> None:
        self.settings = settings
        self.registrations = registrations or build_fcm_registration_store(settings)
        self.receipts = receipts or build_guardian_delivery_store(settings)
        self.connector = connector or GuardianFCMConnector(project_id=os.getenv("GOOGLE_CLOUD_PROJECT") or "")

    def dispatch(self, state: PatientState, *, event_id: str, mission_id: str) -> dict[str, Any]:
        signals = set(state.consent.signal_types)
        if not state.consent.proactive_enabled or "guardian_push" not in signals:
            return {
                "status": "skipped_not_authorized",
                "sent": 0,
                "recovered": 0,
                "reason": "Guardian push requires proactive monitoring and the guardian_push signal opt-in.",
            }

        active = self.registrations.list_active(state.profile.id)
        if not active:
            return {
                "status": "skipped_no_active_device",
                "sent": 0,
                "recovered": 0,
                "reason": "No explicitly enabled FCM registration is active for this patient.",
            }

        sent = 0
        recovered = 0
        receipt_ids: list[str] = []
        for registration in active:
            receipt_id = _receipt_id(event_id, registration.connection_id)
            proof_id = _proof_id(receipt_id)
            prior = self.receipts.get(state.profile.id, receipt_id)
            if prior is not None and prior.status == "completed":
                recovered += 1
                receipt_ids.append(prior.id)
                continue
            if not registration.registration_token:
                continue

            try:
                outcome = self.connector.execute(
                    GoogleAction.FCM_SEND_MISSION_NOTIFICATION,
                    {
                        "device_token": registration.registration_token,
                        "mission_id": mission_id,
                        "event_type": "guardian_update",
                        "proof_id": proof_id,
                        "kind": "healthia_update",
                    },
                    idempotency_key=hashlib.sha256(receipt_id.encode("utf-8")).hexdigest(),
                )
                receipt = GuardianDeliveryReceipt(
                    id=receipt_id,
                    patient_id=state.profile.id,
                    mission_id=mission_id,
                    event_id=event_id,
                    connection_id=registration.connection_id,
                    status="completed",
                    provider_resource_id=outcome.resource_id,
                    proof_id=proof_id,
                    safe_summary="Sent one PHI-neutral Guardian update to an explicitly enabled patient device.",
                )
                self.receipts.save(receipt)
                receipt_ids.append(receipt.id)
                sent += 1
            except Exception:
                self.receipts.save(
                    GuardianDeliveryReceipt(
                        id=receipt_id,
                        patient_id=state.profile.id,
                        mission_id=mission_id,
                        event_id=event_id,
                        connection_id=registration.connection_id,
                        status="failed",
                        proof_id=proof_id,
                        safe_summary="Guardian push failed closed; Eventarc redelivery may retry with the same proof id.",
                    )
                )
                raise

        return {
            "status": "completed" if sent or recovered else "skipped_no_active_device",
            "sent": sent,
            "recovered": recovered,
            "receipt_ids": receipt_ids,
            "clinical_content_in_lock_screen": False,
        }
