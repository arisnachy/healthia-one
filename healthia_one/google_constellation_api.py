from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from healthia_one.auth import current_patient_id
from healthia_one.google_cloud_capabilities import capability_manifest
from healthia_one.google_constellation import GrantBundle, GoogleAction
from healthia_one.google_constellation_runtime import GoogleConstellationService
from healthia_one.google_mission_runtime import OfferedSlot


class NavigationMissionRequest(BaseModel):
    condition_or_need: str = Field(min_length=2, max_length=240)
    provider_query: str = Field(min_length=2, max_length=240)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    title: str = Field(default="Find support and arrange care", min_length=2, max_length=220)


class GrantRequest(BaseModel):
    bundle: GrantBundle
    enabled: bool = True


class DiscoverRequest(BaseModel):
    radius_m: int = Field(default=10000, ge=100, le=50000)


class SelectProviderRequest(BaseModel):
    place: dict[str, Any]
    provider_email: str = Field(default="", max_length=254)


class FreeBusyRequest(BaseModel):
    time_min: str = Field(min_length=10, max_length=80)
    time_max: str = Field(min_length=10, max_length=80)
    time_zone: str = Field(min_length=1, max_length=100)


class ActionAuthorizationRequest(BaseModel):
    action: GoogleAction
    ttl_minutes: int = Field(default=15, ge=1, le=1440)
    one_time: bool = True


class ContactProviderRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=10000)


class ChooseSlotRequest(BaseModel):
    slot: OfferedSlot


class FinalizeAppointmentRequest(BaseModel):
    summary: str = Field(default="Health appointment", min_length=1, max_length=220)
    time_zone: str = Field(min_length=1, max_length=100)
    create_followup_task: bool = True


def _mission_payload(mission) -> dict:
    return {
        **mission.model_dump(mode="json"),
        "private_reasoning": None,
        "truth_boundary": (
            "Mission state reports completed external actions only when a connector returned a durable receipt. "
            "Nearby results are candidates, not clinical referrals, and authorization is not the same as execution."
        ),
    }


def build_google_constellation_router(constellation: GoogleConstellationService) -> APIRouter:
    router = APIRouter(prefix="/api/google-constellation", tags=["google-constellation"])

    def patient_id() -> str:
        return current_patient_id()

    @router.get("/capabilities")
    async def capabilities() -> dict:
        pid = patient_id()
        connection = constellation.runtime.oauth_connection_store.load(pid)
        return {
            **capability_manifest(),
            "patient_id": pid,
            "grants": [item.model_dump(mode="json") for item in constellation.grants(pid)],
            "google_account_connection": (
                {
                    "connected": bool(connection and connection.enabled),
                    "google_account": connection.google_account if connection and connection.enabled else "",
                    "granted_scopes": connection.granted_scopes if connection and connection.enabled else [],
                    "secret_material_exposed": False,
                }
            ),
        }

    @router.post("/grants")
    async def create_grant(payload: GrantRequest) -> dict:
        grant = constellation.grant(patient_id(), payload.bundle, enabled=payload.enabled)
        return {
            **grant.model_dump(mode="json"),
            "note": "This is a HealthIA capability grant; Google OAuth scopes are validated separately.",
        }

    @router.delete("/grants/{grant_id}")
    async def revoke_grant(grant_id: str) -> dict:
        try:
            grant = constellation.revoke_grant(patient_id(), grant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Google capability grant not found") from exc
        return grant.model_dump(mode="json")

    @router.post("/missions/navigation")
    async def create_navigation_mission(payload: NavigationMissionRequest) -> dict:
        mission = constellation.coordinator.create_navigation_mission(
            patient_id=patient_id(),
            condition_or_need=payload.condition_or_need,
            provider_query=payload.provider_query,
            lat=payload.lat,
            lng=payload.lng,
            title=payload.title,
        )
        return _mission_payload(mission)

    @router.get("/missions/{mission_id}")
    async def get_mission(mission_id: str) -> dict:
        try:
            mission = constellation.load_mission(patient_id(), mission_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Google health mission not found") from exc
        return _mission_payload(mission)

    @router.post("/missions/{mission_id}/discover")
    async def discover(mission_id: str, payload: DiscoverRequest) -> dict:
        try:
            mission = constellation.load_mission(patient_id(), mission_id)
            mission = constellation.coordinator.discover(
                mission,
                constellation.grants(patient_id()),
                radius_m=payload.radius_m,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Google health mission not found") from exc
        return _mission_payload(mission)

    @router.post("/missions/{mission_id}/provider")
    async def select_provider(mission_id: str, payload: SelectProviderRequest) -> dict:
        try:
            mission = constellation.load_mission(patient_id(), mission_id)
            mission = constellation.coordinator.select_provider(
                mission,
                place=payload.place,
                provider_email=payload.provider_email,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Google health mission not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _mission_payload(mission)

    @router.post("/missions/{mission_id}/availability")
    async def check_availability(mission_id: str, payload: FreeBusyRequest) -> dict:
        try:
            mission = constellation.load_mission(patient_id(), mission_id)
            mission = constellation.coordinator.check_availability(
                mission,
                constellation.grants(patient_id()),
                time_min=payload.time_min,
                time_max=payload.time_max,
                time_zone=payload.time_zone,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Google health mission not found") from exc
        return _mission_payload(mission)

    @router.post("/missions/{mission_id}/authorize")
    async def authorize_action(mission_id: str, payload: ActionAuthorizationRequest) -> dict:
        try:
            authorization = constellation.authorize(
                patient_id(),
                mission_id,
                payload.action,
                ttl_minutes=payload.ttl_minutes,
                one_time=payload.one_time,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Google health mission not found") from exc
        return {
            "authorization": authorization.model_dump(mode="json"),
            "external_action_performed": False,
            "truth_boundary": "Authorization permits one scoped action; it is not an execution receipt.",
        }

    @router.post("/missions/{mission_id}/contact")
    async def contact_provider(mission_id: str, payload: ContactProviderRequest) -> dict:
        try:
            mission = constellation.load_mission(patient_id(), mission_id)
            mission = constellation.coordinator.contact_selected_provider(
                mission,
                constellation.grants(patient_id()),
                subject=payload.subject,
                body=payload.body,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Google health mission not found") from exc
        return _mission_payload(mission)

    @router.post("/missions/{mission_id}/slot")
    async def choose_slot(mission_id: str, payload: ChooseSlotRequest) -> dict:
        try:
            mission = constellation.load_mission(patient_id(), mission_id)
            mission = constellation.coordinator.choose_slot(mission, payload.slot)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Google health mission not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _mission_payload(mission)

    @router.post("/missions/{mission_id}/finalize")
    async def finalize(mission_id: str, payload: FinalizeAppointmentRequest) -> dict:
        try:
            mission = constellation.load_mission(patient_id(), mission_id)
            mission = constellation.coordinator.finalize_appointment(
                mission,
                constellation.grants(patient_id()),
                summary=payload.summary,
                time_zone=payload.time_zone,
                create_followup_task=payload.create_followup_task,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Google health mission not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _mission_payload(mission)

    return router
