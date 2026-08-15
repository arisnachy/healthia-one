from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from healthia_one.auth import patient_scope
from healthia_one.fcm_registration import (
    FCMDeliveryAckRequest,
    FCMDeviceReenableRequest,
    FCMDeviceRegistrationRequest,
    FCMRegistrationStore,
    build_fcm_registration_store,
    build_registration,
)
from healthia_one.mission_evidence_api import build_mission_evidence_router
from healthia_one.pairing import DevicePairingManager


def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def build_fcm_device_router(
    service,
    settings,
    *,
    pairing_manager: DevicePairingManager | None = None,
    store: FCMRegistrationStore | None = None,
) -> APIRouter:
    """Build the authenticated control-router bundle installed by app.main.

    Device FCM endpoints retain their exact `/api/devices/fcm` paths. Mission
    evidence endpoints live in their own module/router and are composed here so
    app.main does not need a second global router wiring path.
    """

    verifier = pairing_manager or DevicePairingManager()
    registrations = store or build_fcm_registration_store(settings)
    root = APIRouter()
    router = APIRouter(prefix="/api/devices/fcm", tags=["devices"])

    async def active_principal(authorization: str | None, device_id: str):
        principal = verifier.identify(_bearer(authorization), device_id)
        if principal is None:
            raise HTTPException(status_code=401, detail="Dispositivo no vinculado o token inválido.")
        with patient_scope(principal.patient_id):
            state = await service.snapshot()
        connection = next(
            (item for item in state.device_connections if item.id == principal.connection_id),
            None,
        )
        if connection is not None and connection.status == "disconnected":
            raise HTTPException(status_code=401, detail="La conexión del dispositivo fue revocada.")
        if connection is not None and str(connection.device_id or "") != principal.device_id:
            raise HTTPException(status_code=401, detail="La identidad del dispositivo no coincide con la conexión.")
        return principal

    def registration_for(principal, registration_token: str):
        return build_registration(
            patient_id=principal.patient_id,
            connection_id=principal.connection_id,
            device_id=principal.device_id,
            registration_token=registration_token,
        )

    @router.post("/register")
    async def register_fcm_device(
        payload: FCMDeviceRegistrationRequest,
        authorization: str | None = Header(default=None),
    ) -> dict:
        principal = await active_principal(authorization, payload.device_id)
        candidate = registration_for(principal, payload.registration_token)
        registrations.save(candidate)
        current = registrations.load(principal.patient_id, principal.connection_id)
        usable = bool(current and current.usable())
        return {
            "registered": usable,
            "notifications_enabled": usable,
            "connection_id": principal.connection_id,
            "device_id": principal.device_id,
            "token_stored_server_side": usable,
            "token_returned": False,
            "sticky_opt_out_respected": bool(current and not current.enabled),
            "updated_at": current.updated_at.isoformat() if current else candidate.updated_at.isoformat(),
        }

    @router.post("/register/enable")
    async def explicitly_reenable_fcm_device(
        payload: FCMDeviceReenableRequest,
        authorization: str | None = Header(default=None),
    ) -> dict:
        principal = await active_principal(authorization, payload.device_id)
        candidate = registration_for(principal, payload.registration_token)
        registrations.save(candidate, allow_reenable=True)
        current = registrations.load(principal.patient_id, principal.connection_id)
        if current is None or not current.usable():
            raise HTTPException(status_code=409, detail="No se pudo reactivar el registro FCM.")
        return {
            "registered": True,
            "notifications_enabled": True,
            "explicit_opt_in": True,
            "connection_id": principal.connection_id,
            "device_id": principal.device_id,
            "token_stored_server_side": True,
            "token_returned": False,
            "updated_at": current.updated_at.isoformat(),
        }

    @router.post("/ack")
    async def acknowledge_fcm_delivery(
        payload: FCMDeliveryAckRequest,
        authorization: str | None = Header(default=None),
    ) -> dict:
        principal = await active_principal(authorization, payload.device_id)
        registration = registrations.acknowledge(
            principal.patient_id,
            principal.connection_id,
            payload.proof_id,
            payload.notification_shown,
        )
        if registration is None:
            raise HTTPException(status_code=409, detail="El registro FCM no está activo.")
        return {
            "acknowledged": True,
            "proof_id": payload.proof_id,
            "notification_shown": bool(registration.last_delivery_notification_shown),
            "connection_id": principal.connection_id,
            "device_id": principal.device_id,
            "token_returned": False,
            "acknowledged_at": registration.last_delivery_ack_at.isoformat()
            if registration.last_delivery_ack_at
            else None,
        }

    @router.delete("/register/{device_id}")
    async def unregister_fcm_device(
        device_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict:
        principal = await active_principal(authorization, device_id)
        disabled = registrations.disable_connection(principal.patient_id, principal.connection_id)
        return {
            "unregistered": bool(disabled),
            "notifications_enabled": False,
            "sticky_opt_out": bool(disabled),
            "token_erased_server_side": bool(disabled),
            "connection_id": principal.connection_id,
            "device_id": principal.device_id,
            "token_returned": False,
        }

    @router.get("/status/{device_id}")
    async def fcm_device_status(
        device_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict:
        principal = await active_principal(authorization, device_id)
        registration = registrations.load(principal.patient_id, principal.connection_id)
        usable = bool(registration and registration.usable())
        return {
            "registered": usable,
            "notifications_enabled": usable,
            "connection_id": principal.connection_id,
            "device_id": principal.device_id,
            "token_returned": False,
            "has_delivery_ack": bool(registration and registration.last_delivery_ack_at),
            "last_delivery_notification_shown": registration.last_delivery_notification_shown
            if registration
            else None,
        }

    root.include_router(router)
    root.include_router(build_mission_evidence_router(service))
    return root
