from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from healthia_one.config import settings
from healthia_one.models import ActivityRecord, ChatRequest, VitalRecord, WeightRecord
from healthia_one.results import explain_result, parse_result_file
from healthia_one.service import HealthIAService

service = HealthIAService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await service.initialize()
    stop_event = asyncio.Event()
    background_task = asyncio.create_task(service.background_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        background_task.cancel()
        with suppress(asyncio.CancelledError):
            await background_task


app = FastAPI(title="HealthIA ONE", version="0.1.0", lifespan=lifespan)
WEB_ROOT = Path(__file__).resolve().parents[1] / "web"
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
        "truth_boundary": (
            "Patient continuity demo using synthetic data. It does not diagnose, prescribe, or "
            "replace emergency or professional care."
        ),
    }


@app.get("/api/bootstrap")
async def bootstrap() -> dict:
    state = await service.snapshot()
    return state.model_dump(mode="json")


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    response = await service.add_patient_message(request.message)
    return response.model_dump(mode="json")


@app.post("/api/vitals")
async def add_vital(vital: VitalRecord) -> dict:
    return (await service.add_vital(vital)).model_dump(mode="json")


@app.post("/api/weight")
async def add_weight(weight: WeightRecord) -> dict:
    return (await service.add_weight(weight)).model_dump(mode="json")


@app.post("/api/activity")
async def add_activity(activity: ActivityRecord) -> dict:
    return (await service.add_activity(activity)).model_dump(mode="json")


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
    async with service._mutation_lock:
        state = await service.store.load()
        state.results.append(result)
        await service.store.save(state)
    await service.broker.publish({"type": "state", "section": "results"})
    return result.model_dump(mode="json")


@app.post("/api/demo/tick")
async def demo_tick() -> dict:
    messages = await service.run_proactive_check()
    return {"created": len(messages), "messages": [item.model_dump(mode="json") for item in messages]}


@app.get("/api/events/stream")
async def events() -> StreamingResponse:
    async def generate():
        yield "event: ready\ndata: {}\n\n"
        async for payload in service.broker.subscribe():
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception) -> JSONResponse:  # pragma: no cover - final boundary
    return JSONResponse(status_code=500, content={"detail": "Error interno auditable", "type": type(exc).__name__})
