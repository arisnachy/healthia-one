from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from healthia_one.opportunity_autopilot import (
    DiscoveryStatus,
    authorize_external_submission,
    mark_patient_reviewed,
    upsert_application,
)
from healthia_one.opportunity_integration import autopilot


class ReviewApplicationRequest(BaseModel):
    confirmed: bool


class AuthorizeApplicationRequest(BaseModel):
    authorized: bool


def build_opportunity_router(service) -> APIRouter:
    router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

    @router.get("")
    async def snapshot() -> dict:
        state = await service.snapshot()
        engine = autopilot()
        vault = engine.load(state.profile.id)
        return {
            "patient_id": state.profile.id,
            "watch_topics": [item.model_dump(mode="json") for item in vault.watch_topics],
            "discoveries": [item.model_dump(mode="json") for item in vault.discoveries],
            "programs": [item.model_dump(mode="json") for item in vault.programs],
            "applications": [item.model_dump(mode="json") for item in vault.applications],
            "receipts": [item.model_dump(mode="json") for item in engine.recent_receipts(state.profile.id, limit=20)],
            "truth_boundary": (
                "Discoveries and program candidates are evidence/navigation aids. They do not change treatment, "
                "prove eligibility, or authorize an external application without explicit patient review."
            ),
        }

    @router.post("/discoveries/{discovery_id}/save")
    async def save_discovery(discovery_id: str) -> dict:
        state = await service.snapshot()
        engine = autopilot()
        vault = engine.load(state.profile.id)
        item = next((candidate for candidate in vault.discoveries if candidate.id == discovery_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="Discovery not found")
        item.status = DiscoveryStatus.SAVED
        engine.store.save(vault)
        return {"saved": True, "discovery_id": item.id, "status": str(item.status)}

    @router.post("/applications/{application_id}/review")
    async def review_application(application_id: str, payload: ReviewApplicationRequest) -> dict:
        state = await service.snapshot()
        engine = autopilot()
        vault = engine.load(state.profile.id)
        packet = next((item for item in vault.applications if item.id == application_id), None)
        if packet is None:
            raise HTTPException(status_code=404, detail="Application not found")
        packet = mark_patient_reviewed(packet, confirmed=payload.confirmed)
        upsert_application(vault, packet)
        engine.store.save(vault)
        return packet.model_dump(mode="json")

    @router.post("/applications/{application_id}/authorize")
    async def authorize_application(application_id: str, payload: AuthorizeApplicationRequest) -> dict:
        state = await service.snapshot()
        engine = autopilot()
        vault = engine.load(state.profile.id)
        packet = next((item for item in vault.applications if item.id == application_id), None)
        if packet is None:
            raise HTTPException(status_code=404, detail="Application not found")
        try:
            packet = authorize_external_submission(packet, authorized=payload.authorized)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        upsert_application(vault, packet)
        engine.store.save(vault)
        return {
            **packet.model_dump(mode="json"),
            "external_action_performed": False,
            "next_step": (
                "A configured external delivery adapter must return a durable receipt before this can become SUBMITTED."
                if packet.external_submission_authorized
                else "External submission remains unauthorized."
            ),
        }

    return router
