from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from healthia_one.auth import patient_scope
from healthia_one.fcm_registration import (
    FCMDeviceRegistrationRequest,
    FCMRegistrationStore,
    build_fcm_registration_store,
    build_registration,
)
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
    """Register FCM client instances only through a valid paired-device bearer.

    The raw FCM registration token is accepted once and stored server-side. It is
    never returned in API responses, logs, action receipts or proof artifacts.
    """

    verifier = pairing_manager or DevicePairingManager()
    registrations = store or build_fcm_registration_store(settings)
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
        if connection is None or connection.status == "disconnected":
            raise HTTPException(status_code=401, detail="La conexión del dispositivo fue revocada.")
        if str(connection.device_id or "") != principal.device_id:
            raise HTTPException(status_code=401, detail="La identidad del dispositivo no coincide con la conexión.")
        return principal

    @router.post("/register")
    async def register_fcm_device(
        payload: FCMDeviceRegistrationRequest,
        authorization: str | None = Header(default=None),
    ) -> dict:
        principal = await active_principal(authorization, payload.device_id)
        registration = build_registration(
            patient_id=principal.patient_id,
            connection_id=principal.connection_id,
            device_id=principal.device_id,
            registration_token=payload.registration_token,
        )
        registrations.save(registration)
        return {
            "registered": True,
            "connection_id": principal.connection_id,
            "device_id": principal.device_id,
            "token_stored_server_side": True,
            "token_returned": False,
            "updated_at": registration.updated_at.isoformat(),
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
        return {
            "registered": bool(registration and registration.enabled),
            "connection_id": principal.connection_id,
            "device_id": principal.device_id,
            "token_returned": False,
        }

    return router
