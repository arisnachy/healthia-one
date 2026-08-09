from __future__ import annotations

import os
import re
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request

from healthia_one.auth import patient_scope
from healthia_one.autopilot_events import EventOutboxStore, build_event_outbox_store
from healthia_one.autopilot_runtime import OpportunityAutopilot
from healthia_one.config import Settings, settings
from healthia_one.models import PatientState
from healthia_one.opportunity_integration import autopilot, outbox
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


def _network_policy(event_type: str) -> tuple[bool, bool]:
    scientific = event_type in {
        "patient_state_changed",
        "family_history.changed",
        "medication.changed",
        "scheduled.discovery_refresh",
        "manual.discovery_refresh",
    }
    paid_resource = event_type == "manual.resource_refresh"
    return scientific, paid_resource


async def load_patient_state(settings_value: Settings, patient_id: str) -> PatientState:
    service = HealthIAService(settings_value)
    with patient_scope(patient_id):
        return await service.snapshot()


async def process_outbox_event(
    event_id: str,
    *,
    outbox_store: EventOutboxStore,
    engine: OpportunityAutopilot,
    state_loader: Callable[[str], Awaitable[PatientState]],
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
        allow_science, allow_paid = _network_policy(record.event.event_type)
        report = engine.process(
            state,
            record.event,
            allow_scientific_network=allow_science,
            allow_paid_resource_search=allow_paid,
        )
        if report.actions and report.actions[0].status == "blocked":
            # Keep the outbox pending while another worker owns the lease.
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
) -> FastAPI:
    app = FastAPI(title="HealthIA Opportunity Autopilot Worker", docs_url=None, redoc_url=None)
    worker_outbox = outbox_store or outbox()
    worker_engine = engine or autopilot()

    async def state_loader(patient_id: str) -> PatientState:
        return await load_patient_state(settings_value, patient_id)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "status": "ok",
            "worker": "healthia_opportunity_autopilot",
            "store_backend": settings_value.store_backend,
            "expected_event_type": FIRESTORE_CREATED,
            "iam_boundary_required": settings_value.env != "local",
        }

    @app.post("/events/firestore")
    async def firestore_event(request: Request) -> dict:
        # Production security boundary is Cloud Run IAM. Eventarc invokes this
        # private service using its configured service account; this application
        # additionally rejects any event type/path outside our exact outbox.
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
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Autopilot outbox event not found") from exc
        except Exception as exc:
            # Non-2xx lets Eventarc retry according to its delivery semantics.
            raise HTTPException(status_code=503, detail="Autopilot event processing failed") from exc

    return app


app = create_worker_app()
