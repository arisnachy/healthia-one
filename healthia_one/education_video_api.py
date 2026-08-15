from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from healthia_one.education_video_renderer import load_generated_video


def _video_record(state, video_id: str) -> dict | None:
    for message in reversed(state.messages):
        if message.role != "assistant":
            continue
        record = (message.metadata or {}).get("education_video")
        if not isinstance(record, dict):
            continue
        if record.get("status") == "completed" and record.get("video_id") == video_id:
            return dict(record)
    return None


def build_education_video_router(service) -> APIRouter:
    router = APIRouter(prefix="/api/education", tags=["patient-education"])

    @router.get("/videos/{video_id}")
    async def get_video(video_id: str):
        if not video_id.startswith("video_") or len(video_id) > 80:
            raise HTTPException(status_code=404, detail="Video no encontrado")
        state = await service.snapshot()
        record = _video_record(state, video_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Video no encontrado")
        try:
            media = await load_generated_video(str(record.get("storage_path") or ""))
        except (FileNotFoundError, ValueError, RuntimeError):
            raise HTTPException(status_code=404, detail="Video no disponible")
        headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
        if isinstance(media, Path):
            return FileResponse(media, media_type="video/mp4", headers=headers, content_disposition_type="inline")
        return Response(content=media, media_type="video/mp4", headers=headers)

    @router.get("/videos/{video_id}/manifest")
    async def get_video_manifest(video_id: str) -> dict:
        state = await service.snapshot()
        record = _video_record(state, video_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Video no encontrado")
        return {
            "video_id": video_id,
            "topic": record.get("topic"),
            "title": record.get("title"),
            "duration_seconds": record.get("duration_seconds"),
            "private": True,
            "patient_fact_source_ids": record.get("patient_fact_source_ids") or [],
            "veo_enhanced": bool(record.get("veo_enhanced")),
            "narration_status": record.get("narration_status"),
            "truth_boundary": "Patient education only; the video does not prescribe or change treatment.",
        }

    return router
