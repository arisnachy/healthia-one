from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from healthia_one.config import settings
from healthia_one.continuity import build_timeline, condition_pack_summary, consultation_brief, medication_summary
from healthia_one.control import export_patient_state
from healthia_one.devices import device_summary, medication_device_cross_checks
from healthia_one.documents import build_document, document_index
from healthia_one.family import family_summary
from healthia_one.profile import normalize_medication_text, profile_summary
from healthia_one.models import (
    ActivityRecord,
    Appointment,
    ChatRequest,
    FamilyMember,
    HealthConnectSyncBatch,
    HealthGoal,
    MedicationCheckIn,
    MedicationNormalizeRequest,
    MedicationPlan,
    MuteRuleRequest,
    PatientConsent,
    PatientProfile,
    SnoozeRequest,
    VitalRecord,
    WeightRecord,
)
from healthia_one.results import explain_result, parse_result_file
from healthia_one.service import HealthIAService

service = HealthIAService(settings)
ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
UPLOAD_ROOT = ROOT / "uploads" / "patient_demo"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await service.initialize()
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    stop_event = asyncio.Event()
    background_task = asyncio.create_task(service.background_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        background_task.cancel()
        with suppress(asyncio.CancelledError):
            await background_task


app = FastAPI(title="HealthIA ONE", version="0.4.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="assets")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "healthia-one"}


@app.get("/api/readiness")
async def readiness() -> dict:
    return {
        "ready": True,
        "llm_backend": settings.llm_backend,
        "model": settings.model,
        "adk_ready": settings.adk_ready,
        "store_backend": settings.store_backend,
        "proactive_interval_seconds": settings.proactive_interval_seconds,
        "capabilities": [
            "chat",
            "proactive_followup",
            "vitals",
            "weight",
            "activity",
            "results",
            "family_genogram",
            "document_archive",
            "unified_timeline",
            "medication_checkins",
            "appointments",
            "consultation_brief",
            "condition_packs",
            "patient_consent",
            "quiet_hours",
            "snooze_and_mute",
            "audit_log",
            "patient_export",
            "patient_profile",
            "reproductive_health",
            "pregnancy_and_postpartum",
            "bmi_and_nutrition_context",
            "health_connect_sync",
            "device_medication_cross_check",
        ],
        "truth_boundary": (
            "Synthetic patient continuity system. It does not diagnose, prescribe, change medication, "
            "or replace emergency and professional care."
        ),
    }


@app.get("/api/bootstrap")
async def bootstrap() -> dict:
    state = await service.snapshot()
    payload = state.model_dump(mode="json")
    payload["family_summary"] = family_summary(state)
    payload["document_index"] = document_index(state)
    payload["timeline"] = build_timeline(state)
    payload["medication_summary"] = medication_summary(state)
    payload["condition_packs"] = condition_pack_summary(state)
    payload["consultation_brief"] = consultation_brief(state)
    payload["profile_summary"] = profile_summary(state)
    payload["device_summary"] = device_summary(state)
    payload["device_medication_cross_checks"] = medication_device_cross_checks(state)
    payload["audit_summary"] = {
        "count": len(state.audit_events),
        "latest": [item.model_dump(mode="json") for item in state.audit_events[-20:]],
    }
    return payload


@app.get("/api/profile")
async def get_profile() -> dict:
    return profile_summary(await service.snapshot())


@app.put("/api/profile")
async def update_profile(profile: PatientProfile) -> dict:
    await service.update_profile(profile)
    return profile_summary(await service.snapshot())


@app.post("/api/profile/medications/normalize")
async def normalize_medication(request: MedicationNormalizeRequest) -> dict:
    try:
        plan = normalize_medication_text(request.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "suggestion": plan.model_dump(mode="json"),
        "requires_confirmation": True,
        "safety": "La normalización organiza el texto; no prescribe ni confirma que el medicamento sea correcto.",
    }


@app.get("/api/devices")
async def devices() -> dict:
    state = await service.snapshot()
    payload = device_summary(state)
    payload["medication_cross_checks"] = medication_device_cross_checks(state)
    return payload


@app.post("/api/devices/health-connect/sync")
async def health_connect_sync(batch: HealthConnectSyncBatch) -> dict:
    return await service.ingest_health_connect(batch)


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    return (await service.add_patient_message(request.message)).model_dump(mode="json")


@app.post("/api/vitals")
async def add_vital(vital: VitalRecord) -> dict:
    return (await service.add_vital(vital)).model_dump(mode="json")


@app.post("/api/weight")
async def add_weight(weight: WeightRecord) -> dict:
    return (await service.add_weight(weight)).model_dump(mode="json")


@app.post("/api/activity")
async def add_activity(activity: ActivityRecord) -> dict:
    return (await service.add_activity(activity)).model_dump(mode="json")


@app.get("/api/family")
async def get_family() -> dict:
    state = await service.snapshot()
    return {"members": [item.model_dump(mode="json") for item in state.family_members], "summary": family_summary(state)}


@app.post("/api/family")
async def add_family_member(member: FamilyMember) -> dict:
    return (await service.add_family_member(member)).model_dump(mode="json")


@app.get("/api/documents")
async def list_documents() -> dict:
    state = await service.snapshot()
    return {"documents": [item.model_dump(mode="json") for item in state.documents], "index": document_index(state)}


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str | None = Form(default=None),
    title: str | None = Form(default=None),
) -> dict:
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 5 MB.")
    try:
        document = build_document(
            filename=file.filename or "documento",
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(content),
            category=category,
            title=title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    destination = ROOT / document.storage_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(destination.write_bytes, content)
    return (await service.add_document(document)).model_dump(mode="json")


@app.get("/api/documents/{document_id}/download")
async def download_document(document_id: str) -> FileResponse:
    document = await service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    path = (ROOT / document.storage_path).resolve()
    if ROOT.resolve() not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    return FileResponse(path, media_type=document.mime_type, filename=document.filename)


@app.get("/api/timeline")
async def timeline() -> dict:
    state = await service.snapshot()
    return {"events": build_timeline(state), "condition_packs": condition_pack_summary(state)}


@app.get("/api/treatment")
async def treatment() -> dict:
    return medication_summary(await service.snapshot())


@app.post("/api/treatment/plans")
async def add_medication_plan(plan: MedicationPlan) -> dict:
    return (await service.add_medication_plan(plan)).model_dump(mode="json")


@app.post("/api/treatment/checkins")
async def add_medication_checkin(checkin: MedicationCheckIn) -> dict:
    try:
        return (await service.add_medication_checkin(checkin)).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/appointments")
async def appointments() -> dict:
    state = await service.snapshot()
    return {
        "appointments": [item.model_dump(mode="json") for item in state.appointments],
        "consultation_brief": consultation_brief(state),
    }


@app.post("/api/appointments")
async def add_appointment(appointment: Appointment) -> dict:
    return (await service.add_appointment(appointment)).model_dump(mode="json")


@app.get("/api/consultation-brief")
async def get_consultation_brief(appointment_id: str | None = None) -> dict:
    return consultation_brief(await service.snapshot(), appointment_id)


@app.post("/api/goals")
async def add_goal(goal: HealthGoal) -> dict:
    return (await service.add_goal(goal)).model_dump(mode="json")


@app.get("/api/consent")
async def get_consent() -> dict:
    return (await service.snapshot()).consent.model_dump(mode="json")


@app.put("/api/consent")
async def update_consent(consent: PatientConsent) -> dict:
    return (await service.update_consent(consent)).model_dump(mode="json")


@app.post("/api/consent/snooze")
async def snooze(request: SnoozeRequest) -> dict:
    until = await service.snooze(request.hours)
    return {"snoozed_until": until.isoformat(), "hours": request.hours}


@app.post("/api/consent/mute")
async def mute_rule(request: MuteRuleRequest) -> dict:
    consent = await service.mute_rule(request.prefix)
    return consent.model_dump(mode="json")


@app.get("/api/audit")
async def audit_log(limit: int = 100) -> dict:
    limit = min(max(limit, 1), 500)
    state = await service.snapshot()
    events = state.audit_events[-limit:]
    return {"count": len(state.audit_events), "events": [item.model_dump(mode="json") for item in reversed(events)]}


@app.get("/api/export")
async def patient_export() -> JSONResponse:
    payload = export_patient_state(await service.snapshot())
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": "attachment; filename=healthia-one-patient-export.json"},
    )


@app.post("/api/results/upload")
async def upload_result(file: UploadFile = File(...)) -> dict:
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 5 MB.")
    try:
        result = parse_result_file(file.filename or "result", content)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo interpretar el archivo: {exc}") from exc
    result.explanation = explain_result(result)
    result.explained = result.status == "parsed"
    return (await service._append_and_publish("results", result, "results", action="upload_result")).model_dump(mode="json")


@app.post("/api/demo/reset")
async def demo_reset() -> dict:
    state = await service.reset_demo()
    return {"reset": True, "patient_id": state.profile.id}


@app.post("/api/demo/device-sync")
async def demo_device_sync() -> dict:
    from datetime import datetime, timezone
    from healthia_one.models import DeviceMetric, DeviceObservation

    now = datetime.now(timezone.utc)
    batch = HealthConnectSyncBatch(
        device_id="android-demo",
        source_package="com.healthia.one.demo",
        background_read=True,
        records=[
            DeviceObservation(
                external_id=f"demo-steps-{now.date().isoformat()}",
                metric=DeviceMetric.STEPS,
                observed_at=now,
                value=3560,
                unit="count",
                source_name="Android Health Connect",
                device_manufacturer="Demo",
                device_model="Synthetic Wear",
            ),
            DeviceObservation(
                external_id=f"demo-heart-{int(now.timestamp())}",
                metric=DeviceMetric.HEART_RATE,
                observed_at=now,
                value=76,
                unit="bpm",
                source_name="Android Health Connect",
            ),
            DeviceObservation(
                external_id=f"demo-weight-{now.date().isoformat()}",
                metric=DeviceMetric.WEIGHT,
                observed_at=now,
                value=80.1,
                unit="kg",
                source_name="Smart scale via Health Connect",
            ),
        ],
    )
    return await service.ingest_health_connect(batch)


@app.post("/api/demo/tick")
async def demo_tick() -> dict:
    messages = await service.run_proactive_check(manual_requested=True)
    return {"created": len(messages), "messages": [item.model_dump(mode="json") for item in messages]}


@app.get("/api/events/stream")
async def events() -> StreamingResponse:
    async def generate():
        yield "event: ready\ndata: {}\n\n"
        async for payload in service.broker.subscribe():
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception) -> JSONResponse:  # pragma: no cover
    return JSONResponse(status_code=500, content={"detail": "Error interno auditable", "type": type(exc).__name__})
