from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from healthia_one.auth import current_patient_id, patient_scope
from healthia_one.auth_web import install_patient_auth
from healthia_one.config import settings
from healthia_one.continuity import build_timeline, condition_pack_summary, consultation_brief, medication_summary
from healthia_one.control import export_patient_state
from healthia_one.cost_guard import CostGuardBlocked
from healthia_one.devices import device_summary, medication_device_cross_checks
from healthia_one.documents import build_document, document_index
from healthia_one.evidence_store import evidence_backend, load_evidence, local_evidence_path, persist_evidence
from healthia_one.family import family_summary
from healthia_one.fcm_device_api import build_fcm_device_router
from healthia_one.fcm_registration import build_fcm_registration_store
from healthia_one.profile import normalize_medication_text, profile_summary
from healthia_one.models import (
    ActivityRecord,
    Appointment,
    ChatRequest,
    FamilyMember,
    DevicePairingClaim,
    EvaluationCompleteRequest,
    EvaluationRunRequest,
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
from healthia_one.result_ai import analyze_uploaded_result, apply_multimodal_analysis, multimodal_supported
from healthia_one.result_capabilities import UnsupportedClinicalFormat, capability_manifest, validate_clinical_upload
from healthia_one.results import explain_result, parse_result_file
from healthia_one.pairing import DevicePairingManager, PairingError
from healthia_one.runtime_architecture import build_pairing_manager, build_service, runtime_readiness
from healthia_one.service import HealthIAService
from healthia_one.twin import clinical_twin_summary

service = build_service(settings)
pairing_manager = build_pairing_manager(settings)
fcm_registration_store = build_fcm_registration_store(settings)
ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
UPLOAD_ROOT = ROOT / "uploads" / "patient_demo"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await service.initialize()
    if evidence_backend() == "local":
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    # No permanent polling loop. Agents run because the patient talks, evidence
    # arrives, a device syncs, or an explicit review is requested.
    yield


app = FastAPI(title="HealthIA ONE", version="0.8.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="assets")
account_manager = install_patient_auth(app, service=service, settings=settings, web_root=WEB_ROOT)
app.include_router(
    build_fcm_device_router(
        service,
        settings,
        pairing_manager=pairing_manager,
        store=fcm_registration_store,
    )
)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/living")
async def living_system() -> FileResponse:
    if not settings.evaluation_enabled or not settings.evaluation_access_key.strip():
        raise HTTPException(status_code=404, detail="Evaluation capability is not available")
    return FileResponse(WEB_ROOT / "living.html")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "healthia-one"}


def _require_evaluation_capability(access_key: str | None) -> None:
    configured = settings.evaluation_access_key.strip()
    if not settings.evaluation_enabled or not configured:
        raise HTTPException(status_code=404, detail="Evaluation capability is not available")
    supplied = (access_key or "").strip()
    if not supplied or not secrets.compare_digest(supplied, configured):
        raise HTTPException(status_code=403, detail="Invalid evaluation capability")


@app.get("/api/readiness")
async def readiness():
    dependency_readiness = await runtime_readiness(
        service,
        settings,
        pairing_manager,
        fcm_registration_store,
    )
    cloud = settings.env.strip().lower() == "cloud"
    patient_sessions_ready = (not cloud) or account_manager.credential_persistence == "restart_safe"
    runtime_checks = dependency_readiness["runtime"]["checks"]
    runtime_checks["patient_sessions_restart_safe"] = patient_sessions_ready
    dependency_readiness["runtime"]["ready"] = all(runtime_checks.values())
    dependency_readiness["ready"] = bool(
        dependency_readiness["ready"] and dependency_readiness["runtime"]["ready"]
    )

    payload = {
        "ready": dependency_readiness["ready"],
        "llm_backend": settings.llm_backend,
        "model": settings.model,
        "adk_ready": settings.adk_ready,
        "ai_ready": settings.adk_ready,
        "ai_status": service.gemini.last_status,
        "store_backend": settings.store_backend,
        "evidence_backend": evidence_backend(),
        "agent_execution": "demand_driven",
        "proactive_enabled": False,
        "living_evaluation_available": bool(settings.evaluation_enabled and settings.evaluation_access_key.strip()),
        "release_sha": settings.release_sha,
        "auth_required": settings.auth_required,
        "patient_session_persistence": account_manager.credential_persistence,
        "patient_state_scope": "authenticated_patient" if settings.auth_required else "demo_patient",
        "cost_control": service.gemini.cost_status(),
        "dependency_readiness": dependency_readiness,
        "capabilities": [
            "chat",
            "gemini_adaptive_clinical_interview",
            "interview_memory",
            "ai_followup_or_orientation_decision",
            "demand_driven_followup",
            "patient_login_logout",
            "patient_scoped_state",
            "patient_scoped_events",
            "vitals",
            "weight",
            "activity",
            "results",
            "multimodal_result_interpretation",
            "clinical_twin",
            "durable_original_evidence",
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
            "fcm_private_notifications",
            "device_medication_cross_check",
            "cloud_cost_guard",
            "bounded_living_system_evaluation",
            "multi_instance_pairing",
            "distributed_event_fanout",
            "truthful_dependency_readiness",
        ],
        "truth_boundary": (
            "Patient continuity system. It does not confirm diagnoses, prescribe, change medication, "
            "or replace emergency and professional care."
        ),
    }
    if not payload["ready"]:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/api/cost-control")
async def get_cost_control() -> dict:
    return service.gemini.cost_status()


@app.post("/api/cost-control")
async def update_cost_control(enabled: bool, request: Request) -> dict:
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=403, detail="El interruptor de costos solo puede cambiarse desde la computadora local.")
    try:
        return service.gemini.set_cost_enabled(enabled)
    except CostGuardBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
    payload["clinical_twin"] = clinical_twin_summary(state)
    payload["audit_summary"] = {
        "count": len(state.audit_events),
        "latest": [item.model_dump(mode="json") for item in state.audit_events[-20:]],
    }
    return payload


@app.get("/api/twin")
async def twin() -> dict:
    return clinical_twin_summary(await service.snapshot())


@app.post("/api/evaluation/arm")
async def evaluation_arm(x_healthia_evaluation_key: str | None = Header(default=None)) -> dict:
    _require_evaluation_capability(x_healthia_evaluation_key)
    return await service.arm_living_evaluation()


@app.post("/api/evaluation/run")
async def evaluation_run(
    request: EvaluationRunRequest,
    x_healthia_evaluation_key: str | None = Header(default=None),
) -> dict:
    _require_evaluation_capability(x_healthia_evaluation_key)
    try:
        return await service.run_living_evaluation(request.session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/evaluation/complete")
async def evaluation_complete(
    request: EvaluationCompleteRequest,
    x_healthia_evaluation_key: str | None = Header(default=None),
) -> dict:
    _require_evaluation_capability(x_healthia_evaluation_key)
    try:
        return await service.complete_living_evaluation(
            request.session_id,
            systolic=request.systolic,
            diastolic=request.diastolic,
            pulse=request.pulse,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/evaluation/state")
async def evaluation_state(x_healthia_evaluation_key: str | None = Header(default=None)) -> dict:
    _require_evaluation_capability(x_healthia_evaluation_key)
    return await service.living_evaluation_snapshot()


@app.post("/api/ai/test")
async def test_google_ai() -> dict:
    return await service.gemini.probe()


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


@app.delete("/api/devices/{connection_id}")
async def disconnect_device(connection_id: str) -> dict:
    patient_id = (await service.snapshot()).profile.id
    if not await service.disconnect_device(connection_id):
        raise HTTPException(status_code=404, detail="Conexión no encontrada.")
    fcm_tombstoned = fcm_registration_store.disable_connection(patient_id, connection_id)
    return {
        "disconnected": True,
        "connection_id": connection_id,
        "fcm_tombstoned": bool(fcm_tombstoned),
    }


@app.post("/api/devices/pairing")
async def create_device_pairing(request: Request) -> dict:
    patient_id = (await service.snapshot()).profile.id
    payload = await asyncio.to_thread(pairing_manager.create, patient_id)
    payload["backend_url"] = str(request.base_url).rstrip("/")
    return payload


@app.get("/api/devices/pairing/{code}")
async def device_pairing_status(code: str) -> dict:
    try:
        payload = await asyncio.to_thread(pairing_manager.status, code)
    except PairingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if payload.get("patient_id") != current_patient_id():
        raise HTTPException(status_code=404, detail="Conexión no encontrada.")
    return payload


@app.get("/api/devices/pairing/{code}/wait")
async def wait_device_pairing(code: str) -> dict:
    """Hold one request until the pairing is claimed or expires; no browser polling."""
    try:
        initial = await asyncio.to_thread(pairing_manager.status, code)
        if initial.get("patient_id") != current_patient_id():
            raise HTTPException(status_code=404, detail="Conexión no encontrada.")
        return await asyncio.to_thread(pairing_manager.wait_for_claim, code, 600)
    except PairingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/devices/pairing/claim")
async def claim_device_pairing(claim: DevicePairingClaim) -> dict:
    try:
        return await asyncio.to_thread(pairing_manager.claim, claim.code, claim.device_id, claim.display_name)
    except PairingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


@app.post("/api/devices/health-connect/sync")
async def health_connect_sync(
    batch: HealthConnectSyncBatch,
    authorization: str | None = Header(default=None),
) -> dict:
    principal = pairing_manager.identify(bearer_token(authorization), batch.device_id)
    if principal is None:
        raise HTTPException(status_code=401, detail="Dispositivo no vinculado o token inválido.")
    granted_metrics = set(batch.granted_metrics)
    if batch.records and not granted_metrics:
        raise HTTPException(status_code=422, detail="El lote no declara métricas autorizadas.")
    unauthorized = sorted({record.metric.value for record in batch.records if record.metric not in granted_metrics})
    if unauthorized:
        raise HTTPException(
            status_code=422,
            detail=f"El lote contiene métricas no autorizadas: {', '.join(unauthorized)}.",
        )
    for record in batch.records:
        record.patient_id = principal.patient_id
        record.metadata["paired_connection_id"] = principal.connection_id
        record.metadata["paired_device_id"] = principal.device_id
        record.metadata["paired_patient_id"] = principal.patient_id
    with patient_scope(principal.patient_id):
        try:
            result = await service.ingest_health_connect(
                batch,
                authorized_connection_id=principal.connection_id,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    result["connection_id"] = principal.connection_id
    result["patient_id"] = principal.patient_id
    result["device_identity_verified"] = True
    return result


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    return (await service.add_patient_message(request.message)).model_dump(mode="json")


@app.post("/api/consultations/new")
async def start_new_consultation() -> dict:
    """Create a chat boundary while preserving the patient record."""
    message = await service.start_new_consultation()
    return {
        "conversation_id": message.metadata["conversation_id"],
        "message": message.model_dump(mode="json"),
        "preserves_longitudinal_record": True,
    }


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
    try:
        validate_clinical_upload(file.filename or "documento", file.content_type or "application/octet-stream", content)
    except UnsupportedClinicalFormat as exc:
        raise HTTPException(status_code=415, detail={"code": "format_not_implemented", "format": exc.detected_format, "capabilities_url": "/api/results/capabilities"}) from exc
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 5 MB.")
    state = await service.snapshot()
    try:
        document = build_document(
            filename=file.filename or "documento",
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(content),
            category=category,
            title=title,
            patient_id=state.profile.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    document = await persist_evidence(document, content, ROOT)
    return (await service.add_document(document)).model_dump(mode="json")


@app.get("/api/documents/{document_id}/download")
async def download_document(document_id: str, inline: bool = False):
    document = await service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    path = local_evidence_path(document, ROOT)
    if path is not None:
        return FileResponse(
            path,
            media_type=document.mime_type,
            filename=document.filename,
            content_disposition_type="inline" if inline else "attachment",
        )
    try:
        content = await load_evidence(document, ROOT)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=404, detail="Archivo no disponible") from exc
    return Response(
        content=content,
        media_type=document.mime_type,
        headers={"Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{document.filename}"'},
    )


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


@app.get("/api/results/capabilities")
async def result_capabilities() -> dict:
    return capability_manifest(settings.max_upload_bytes, service.gemini.settings.adk_ready)


@app.post("/api/results/upload")
async def upload_result(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "result"
    content_type = file.content_type or "application/octet-stream"
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 5 MB.")
    try:
        validate_clinical_upload(filename, content_type, content)
    except UnsupportedClinicalFormat as exc:
        raise HTTPException(status_code=415, detail={"code": "format_not_implemented", "format": exc.detected_format, "capabilities_url": "/api/results/capabilities"}) from exc
    state = await service.snapshot()
    try:
        result = parse_result_file(filename, content)
        result.patient_id = state.profile.id
        document = build_document(
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            title=f"Evidencia · {Path(filename).stem}",
            patient_id=state.profile.id,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo interpretar el archivo: {exc}") from exc

    document = await persist_evidence(document, content, ROOT)

    if result.status == "pending_multimodal" and multimodal_supported(filename, content_type):
        analysis = await analyze_uploaded_result(
            service.gemini,
            state,
            filename,
            content_type,
            content,
        )
        result = apply_multimodal_analysis(result, analysis)
    else:
        result.explanation = explain_result(result)
        result.explained = result.status == "parsed"

    document.related_result_id = result.id
    document.status = "parsed" if result.status == "parsed" else "pending_review"
    document.summary = result.explanation[:2000]
    stored = await service.add_result_evidence(result, document)
    payload = stored.model_dump(mode="json")
    payload["document_id"] = document.id
    payload["original_available"] = True
    payload["evidence_backend"] = evidence_backend()
    payload["twin_updated"] = True
    return payload


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
        granted_metrics=[DeviceMetric.STEPS, DeviceMetric.HEART_RATE, DeviceMetric.WEIGHT],
        records=[
            DeviceObservation(
                patient_id=current_patient_id(),
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
                patient_id=current_patient_id(),
                external_id=f"demo-heart-{int(now.timestamp())}",
                metric=DeviceMetric.HEART_RATE,
                observed_at=now,
                value=76,
                unit="bpm",
                source_name="Android Health Connect",
            ),
            DeviceObservation(
                patient_id=current_patient_id(),
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
    patient_id = current_patient_id()

    async def generate():
        yield "event: ready\ndata: {}\n\n"
        async for payload in service.broker.subscribe(patient_id=patient_id):
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception) -> JSONResponse:  # pragma: no cover
    return JSONResponse(status_code=500, content={"detail": "Error interno auditable", "type": type(exc).__name__})
