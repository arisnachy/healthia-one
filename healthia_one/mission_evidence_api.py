from __future__ import annotations

from fastapi import APIRouter, HTTPException

from healthia_one.control import audit
from healthia_one.models import MissionStatus


MISSION_TAG_PREFIX = "mission:"


def mission_tag(mission_id: str) -> str:
    return f"{MISSION_TAG_PREFIX}{mission_id}"


def linked_to_mission(document, mission_id: str) -> bool:
    return mission_tag(mission_id) in set(document.tags)


def linked_mission_ids(document) -> list[str]:
    return [
        tag[len(MISSION_TAG_PREFIX):]
        for tag in document.tags
        if tag.startswith(MISSION_TAG_PREFIX) and len(tag) > len(MISSION_TAG_PREFIX)
    ]


async def link_document_to_mission(service, *, document_id: str, mission_id: str):
    """Persist one explicit patient document->mission evidence link.

    This function does not interpret document contents or assert professional
    authorship. It records only that the authenticated patient explicitly linked
    this stored document to this open mission. Guardian rules decide whether that
    linked evidence satisfies their own narrower closure contracts.
    """
    async with service._mutation_lock:
        state = await service.store.load()
        document = next((item for item in state.documents if item.id == document_id), None)
        if document is None or document.patient_id != state.profile.id:
            raise LookupError("Document not found for authenticated patient")
        mission = next((item for item in state.missions if item.id == mission_id), None)
        if mission is None or mission.patient_id != state.profile.id:
            raise LookupError("Mission not found for authenticated patient")
        if mission.status in {MissionStatus.COMPLETED, MissionStatus.CANCELLED}:
            raise ValueError("Closed missions cannot receive new evidence links")
        if document.status == "invalid":
            raise ValueError("Invalid documents cannot be linked as mission evidence")

        existing_links = linked_mission_ids(document)
        if existing_links and mission_id not in existing_links:
            raise ValueError("This document is already linked to another mission")
        tag = mission_tag(mission_id)
        if tag not in document.tags:
            document.tags.append(tag)
            audit(
                state,
                actor="patient",
                action="link_document_to_mission",
                resource_type="clinical_document",
                resource_id=document.id,
                details={
                    "mission_id": mission.id,
                    "explicit_patient_link": True,
                    "document_content_validated": False,
                    "professional_authorship_verified": False,
                },
            )
            # StateStore Guardian reconciliation runs after this explicit link is
            # durable-in-memory but before the canonical commit. Any resulting
            # external notification intent is still flushed only post-commit.
            await service.store.save(state)
        linked = next(item for item in state.documents if item.id == document_id)

    await service.broker.publish({"type": "state", "section": "documents"})
    await service.broker.publish({"type": "state", "section": "missions"})
    return linked


def build_mission_evidence_router(service) -> APIRouter:
    router = APIRouter(prefix="/api/missions", tags=["missions"])

    @router.post("/{mission_id}/evidence/documents/{document_id}")
    async def link_document(mission_id: str, document_id: str) -> dict:
        try:
            document = await link_document_to_mission(
                service,
                document_id=document_id,
                mission_id=mission_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "linked": True,
            "mission_id": mission_id,
            "document": document.model_dump(mode="json"),
            "truth_boundary": (
                "The patient explicitly linked this stored document to the mission. "
                "This action does not validate document authorship or clinical content."
            ),
        }

    @router.get("/{mission_id}/evidence")
    async def mission_evidence(mission_id: str) -> dict:
        state = await service.snapshot()
        mission = next((item for item in state.missions if item.id == mission_id), None)
        if mission is None or mission.patient_id != state.profile.id:
            raise HTTPException(status_code=404, detail="Mission not found for authenticated patient")
        documents = [
            document
            for document in state.documents
            if document.patient_id == state.profile.id and linked_to_mission(document, mission_id)
        ]
        return {
            "mission_id": mission_id,
            "documents": [item.model_dump(mode="json") for item in documents],
            "count": len(documents),
        }

    return router
