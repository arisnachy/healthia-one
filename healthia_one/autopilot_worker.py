from __future__ import annotations

import asyncio
import os
import re
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request

from healthia_one.auth import patient_scope
from healthia_one.autopilot_events import EventOutboxStore
from healthia_one.autopilot_runtime import OpportunityAutopilot
from healthia_one.autopilot_scheduler import enqueue_scheduled_refreshes, load_firestore_patient_states
from healthia_one.bp_followup_guardian import MISSION_TYPE as BP_MISSION_TYPE
from healthia_one.bp_followup_guardian import bp_followup_due
from healthia_one.config import Settings, settings
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_email_delivery import GuardianEmailDispatcher
from healthia_one.models import PatientState
from healthia_one.opportunity_integration import autopilot, outbox, radar_permissions
from healthia_one.opportunity_permissions import RadarPermissionStore
from healthia_one.service import HealthIAService


FIRESTORE_CREATED = "google.cloud.firestore.document.v1.created"
EVENT_COLLECTION = "healthia_autopilot_events"
_EVENT_SUBJECT = re.compile(r"(?:^|/)documents/healthia_autopilot_events/(?P<event_id>event_[A-Za-z0-9_-]+)$")


def event_id_from_cloudevent_headers(headers) -> str:
    event_type = str(headers.get("ce-type") or "").strip()
    if event_type != FIRESTORE_CREATED:
        raise ValueError(f"Unsupported CloudEvent type: {event_type or 'missing'}")
    subject = str(headers.get("ce-subject") or "").strip()
    match = _EVENT_SUBJECT.search(subject)
    if not match:
        raise ValueError("CloudEvent subject is not a HealthIA autopilot outbox document")
    return match.group("event_id")


def _is_guardian_event(record) -> bool:
    payload = dict(record.event.payload or {})
    return (
        record.event.event_type == "patient_state_changed"
        and str(payload.get("source") or "") == "guardian_context"
        and bool(payload.get("mission_id"))
    )


def _network_policy(event, permissions) -> tuple[bool, bool]:
    event_type = event.event_type
    payload = event.payload or {}
    if event_type == "patient_state_changed" and str(payload.get("source") or "") == "guardian_context":
        # Mainline autonomous continuity never spends a scientific/model network
        # budget just to notice or deliver an overdue BP follow-up.
        return False, False
    if event_type == "manual.discovery_refresh":
        return True, False
    if event_type == "manual.resource_refresh":
        return False, True
    if event_type == "scheduled.discovery_refresh":
        return (
            bool(payload.get("scientific_scan")) and permissions.scientific_enabled,
            bool(payload.get("resource_scan")) and permissions.resource_enabled,
        )
    if event_type in {"patient_state_changed", "family_history.changed", "medication.changed"}:
        return permissions.scientific_enabled, False
    return False, False


def care_continuity_due(state: PatientState, *, runtime_enabled: bool = True) -> bool:
    return bool(runtime_enabled and bp_followup_due(state))


async def load_patient_state(settings_value: Settings, patient_id: str) -> PatientState:
    service = HealthIAService(settings_value)
    service.store.autonomous_enabled = bool(settings_value.proactive_enabled)
    with patient_scope(patient_id):
        return await service.snapshot()


async def reconcile_care_patient(settings_value: Settings, patient_id: str) -> dict:
    service = HealthIAService(settings_value)
    service.store.autonomous_enabled = bool(settings_value.proactive_enabled)
    with patient_scope(patient_id):
        state = await service.snapshot()
        if state.profile.id != patient_id:
            raise PermissionError("Scheduled care patient does not match canonical patient state")
        if not care_continuity_due(state, runtime_enabled=settings_value.proactive_enabled):
            return {"patient_id": patient_id, "status": "not_due"}
        before = {
            mission.id: (mission.status.value, mission.updated_at.isoformat())
            for mission in state.missions
            if mission.mission_type == BP_MISSION_TYPE
        }
        await service.store.save(state)
        persisted = await service.snapshot()
        after = {
            mission.id: (mission.status.value, mission.updated_at.isoformat())
            for mission in persisted.missions
            if mission.mission_type == BP_MISSION_TYPE
        }
        return {
            "patient_id": patient_id,
            "status": "reconciled",
            "changed": before != after,
            "bp_followup_missions": len(after),
        }


async def process_outbox_event(
    event_id: str,
    *,
    outbox_store: EventOutboxStore,
    engine: OpportunityAutopilot,
    state_loader: Callable[[str], Awaitable[PatientState]],
    permission_store: RadarPermissionStore | None = None,
    guardian_email_dispatcher: GuardianEmailDispatcher | None = None,
) -> dict:
    record = outbox_store.get(event_id)
    if record is None:
        raise KeyError(event_id)
    if record.status == "processed":
        return {"event_id": event_id, "status": "duplicate_processed", "duplicate": True}

    try:
        state = await state_loader(record.patient_id)
        if state.profile.id != record.patient_id:
            raise PermissionError("Outbox patient does not match canonical patient state")

        permissions = (
            permission_store.load(record.patient_id)
            if permission_store is not None
            else type("NoAutonomousRadar", (), {"scientific_enabled": False, "resource_enabled": False})()
        )
        allow_science, allow_paid = _network_policy(record.event, permissions)

        if _is_guardian_event(record):
            payload = dict(record.event.payload or {})
            mission_id = str(payload.get("mission_id") or "")
            notification_requested = bool(payload.get("notification_requested"))
            delivery = {"status": "skipped_not_requested", "sent": 0, "recovered": 0}
            if guardian_email_dispatcher is not None and notification_requested:
                assessment_raw = payload.get("guardian_assessment")
                if not isinstance(assessment_raw, dict):
                    raise ValueError("Guardian event is missing its durable assessment")
                assessment = GuardianAssessment.model_validate(assessment_raw)
                delivery = await asyncio.to_thread(
                    guardian_email_dispatcher.dispatch,
                    state,
                    assessment,
                    event_id=record.event.id,
                    mission_id=mission_id,
                )
            outbox_store.mark_processed(event_id)
            return {
                "event_id": event_id,
                "status": "processed",
                "duplicate": False,
                "network_policy": {"scientific": False, "paid_resource": False},
                "model_calls": 0,
                "guardian_delivery": {"email": delivery},
                "mainline_autonomy": "bp_followup_only",
            }

        report = engine.process(
            state,
            record.event,
            allow_scientific_network=allow_science,
            allow_paid_resource_search=allow_paid,
        )
        if report.actions and report.actions[0].status == "blocked":
            return {
                "event_id": event_id,
                "status": "lease_busy",
                "duplicate": False,
                "report": report.model_dump(mode="json"),
            }
        outbox_store.mark_processed(event_id)
        return {
            "event_id": event_id,
            "status": "processed",
            "duplicate": report.duplicate,
            "network_policy": {"scientific": allow_science, "paid_resource": allow_paid},
            "report": report.model_dump(mode="json"),
        }
    except Exception as exc:
        outbox_store.mark_failed(event_id, f"{type(exc).__name__}: {exc}")
        raise


def create_worker_app(
    settings_value: Settings = settings,
    *,
    outbox_store: EventOutboxStore | None = None,
    engine: OpportunityAutopilot | None = None,
    permission_store: RadarPermissionStore | None = None,
    guardian_email_dispatcher: GuardianEmailDispatcher | None = None,
) -> FastAPI:
    app = FastAPI(title="HealthIA Autonomous Continuity Worker", docs_url=None, redoc_url=None)
    worker_outbox = outbox_store or outbox()
    worker_engine = engine or autopilot()
    worker_permissions = permission_store or radar_permissions()
    worker_guardian_email = guardian_email_dispatcher or GuardianEmailDispatcher(settings_value)

    async def state_loader(patient_id: str) -> PatientState:
        return await load_patient_state(settings_value, patient_id)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "status": "ok",
            "worker": "healthia_autonomous_continuity",
            "store_backend": settings_value.store_backend,
            "expected_event_type": FIRESTORE_CREATED,
            "iam_boundary_required": settings_value.env != "local",
            "scientific_schedule": "weekly_opt_in",
            "resource_schedule": "monthly_opt_in",
            "care_continuity_schedule": "daily_explicitly_opted_in_bp_followup",
            "guardian_eventarc": True,
            "guardian_email": "standing_patient_opt_in_plus_connected_gmail",
            "mainline_autonomy": "bp_followup_only",
            "autonomy_trigger": "HealthIA noticed the follow-up was overdue. Nobody prompted it.",
        }

    @app.post("/events/firestore")
    async def firestore_event(request: Request) -> dict:
        if settings_value.env != "local" and os.getenv("K_SERVICE", "").strip() == "":
            raise HTTPException(status_code=503, detail="Autopilot worker must run behind Cloud Run IAM")
        try:
            event_id = event_id_from_cloudevent_headers(request.headers)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            return await process_outbox_event(
                event_id,
                outbox_store=worker_outbox,
                engine=worker_engine,
                state_loader=state_loader,
                permission_store=worker_permissions,
                guardian_email_dispatcher=worker_guardian_email,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Autopilot outbox event not found") from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Autopilot event processing failed") from exc

    async def schedule_mode(mode: str) -> dict:
        if mode not in {"scientific", "resources"}:
            raise HTTPException(status_code=404, detail="Unknown radar schedule")
        if settings_value.store_backend != "firestore":
            raise HTTPException(status_code=409, detail="Scheduled radar production requires Firestore persistence")
        if settings_value.env != "local" and os.getenv("K_SERVICE", "").strip() == "":
            raise HTTPException(status_code=503, detail="Scheduler producer must run behind Cloud Run IAM")
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
        states = await asyncio.to_thread(load_firestore_patient_states, project)
        events = await asyncio.to_thread(
            enqueue_scheduled_refreshes,
            states,
            permission_store=worker_permissions,
            outbox_store=worker_outbox,
            mode=mode,
        )
        return {
            "mode": mode,
            "patient_states_scanned": len(states),
            "events_enqueued": len(events),
            "model_calls": 0,
            "note": "Only patients with explicit radar permission and at least one watch topic receive an event.",
        }

    @app.post("/scheduled/scientific")
    async def scheduled_scientific() -> dict:
        return await schedule_mode("scientific")

    @app.post("/scheduled/resources")
    async def scheduled_resources() -> dict:
        return await schedule_mode("resources")

    @app.post("/scheduled/care")
    async def scheduled_care() -> dict:
        if settings_value.store_backend != "firestore":
            raise HTTPException(status_code=409, detail="Scheduled care continuity requires Firestore persistence")
        if not settings_value.proactive_enabled:
            return {
                "mode": "care_continuity",
                "status": "runtime_disabled",
                "patient_states_scanned": 0,
                "patients_due": 0,
                "patients_reconciled": 0,
                "model_calls": 0,
            }
        if settings_value.env != "local" and os.getenv("K_SERVICE", "").strip() == "":
            raise HTTPException(status_code=503, detail="Care scheduler must run behind Cloud Run IAM")
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
        states = await asyncio.to_thread(load_firestore_patient_states, project)
        due_ids = [state.profile.id for state in states if care_continuity_due(state, runtime_enabled=True)]
        reports = [await reconcile_care_patient(settings_value, patient_id) for patient_id in due_ids]
        return {
            "mode": "care_continuity",
            "patient_states_scanned": len(states),
            "patients_due": len(due_ids),
            "patients_reconciled": sum(1 for item in reports if item["status"] == "reconciled"),
            "model_calls": 0,
            "network_calls_for_clinical_reasoning": 0,
            "reports": reports,
            "note": "Mainline care scheduler promotes only explicitly opted-in blood-pressure follow-up. No other experimental Guardian is activated.",
        }

    return app


app = create_worker_app()
