from __future__ import annotations

import json
import logging
import os
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from healthia_one.config import Settings
from healthia_one.gmail_mission_events import (
    FirestoreMissionResolver,
    GeminiAdministrativeReplyInterpreter,
    GmailHistoryReader,
    GmailMissionEventBridge,
    decode_gmail_pubsub_push,
)
from healthia_one.gmail_watch_runtime import (
    FirestoreGmailWatchDirectory,
    GmailWatchManager,
)
from healthia_one.google_constellation_runtime import (
    GoogleConstellationService,
    build_google_constellation_service,
)
from healthia_one.google_oauth_credentials import SecretManagerOAuthTokenProvider


logger = logging.getLogger("healthia.gmail_worker")


class EnsureWatchRequest(BaseModel):
    patient_id: str = Field(min_length=3, max_length=180)
    force: bool = False


@dataclass
class GmailWorkerRuntime:
    constellation: GoogleConstellationService
    watch_store: FirestoreGmailWatchDirectory
    watch_manager: GmailWatchManager
    bridge: GmailMissionEventBridge


def build_live_runtime(settings: Settings | None = None) -> GmailWorkerRuntime:
    resolved = settings or Settings()
    if resolved.store_backend != "firestore":
        raise RuntimeError("Gmail push worker requires HEALTHIA_STORE_BACKEND=firestore")
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    topic_name = os.getenv("HEALTHIA_GMAIL_PUBSUB_TOPIC", "").strip()
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Gmail push worker")
    if not topic_name:
        raise RuntimeError("HEALTHIA_GMAIL_PUBSUB_TOPIC is required for Gmail push worker")

    constellation = build_google_constellation_service(resolved)
    watch_store = FirestoreGmailWatchDirectory(project=project)
    token_provider = SecretManagerOAuthTokenProvider(
        connection_store=constellation.runtime.oauth_connection_store
    )
    resolver = FirestoreMissionResolver(project=project)
    interpreter = GeminiAdministrativeReplyInterpreter(resolved)
    bridge = GmailMissionEventBridge(
        watch_store=watch_store,
        mission_resolver=resolver,
        coordinator=constellation.coordinator,
        history_reader_factory=lambda patient_id: GmailHistoryReader(patient_id, token_provider),
        interpreter=interpreter,
    )
    manager = GmailWatchManager(
        constellation=constellation,
        watch_store=watch_store,
        topic_name=topic_name,
        renew_before_hours=24,
    )
    return GmailWorkerRuntime(
        constellation=constellation,
        watch_store=watch_store,
        watch_manager=manager,
        bridge=bridge,
    )


def create_app(runtime_factory: Callable[[], GmailWorkerRuntime] = build_live_runtime) -> FastAPI:
    app = FastAPI(
        title="HealthIA Gmail Mission Worker",
        version="1.1",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    cached: dict[str, GmailWorkerRuntime] = {}

    def runtime() -> GmailWorkerRuntime:
        if "value" not in cached:
            cached["value"] = runtime_factory()
        return cached["value"]

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "healthia-gmail-worker"}

    @app.post("/events/gmail-push")
    async def gmail_push(envelope: dict[str, Any]) -> Any:
        try:
            notification = decode_gmail_pubsub_push(envelope)
        except ValueError:
            return Response(status_code=204)

        worker = runtime()
        watch = worker.watch_store.load_by_email(notification.email_address)
        if watch is None:
            return Response(status_code=204)

        connection = worker.constellation.runtime.oauth_connection_store.load(watch.patient_id)
        mailbox = str(connection.google_account or "").strip().lower() if connection else ""
        if connection is None or not connection.enabled or mailbox != watch.email_address.strip().lower():
            watch.enabled = False
            worker.watch_store.save(watch)
            return Response(status_code=204)

        try:
            missions = worker.bridge.process(watch.patient_id, envelope)
        except PermissionError:
            return Response(status_code=204)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"gmail_event_retry:{type(exc).__name__}") from exc
        return {
            "status": "processed",
            "resumed_missions": [item.id for item in missions],
            "count": len(missions),
        }

    @app.post("/scheduled/renew-gmail-watches")
    async def renew_gmail_watches(request: Request) -> dict[str, Any]:
        worker = runtime()
        schedule_time = str(request.headers.get("x-cloudscheduler-scheduletime") or "").strip()
        job_name = str(request.headers.get("x-cloudscheduler-jobname") or "").strip()
        try:
            renewed = worker.watch_manager.renew_due(renewal_window=schedule_time or None)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"gmail_watch_renewal_retry:{type(exc).__name__}") from exc

        counts = Counter(status for _, status in renewed)
        payload = {
            "status": "completed",
            "processed_count": len(renewed),
            "renewed_count": int(counts.get("renewed", 0)),
            "disabled_disconnected_count": int(counts.get("disabled_disconnected", 0)),
            "scheduler_request_bound": bool(schedule_time),
            "scheduler_job_bound": bool(job_name),
            "secret_material_exposed": False,
        }
        # Emit one machine-readable, PHI-neutral operational event. It contains
        # aggregate counts and binding booleans only: no patient IDs, mailbox,
        # OAuth material, message IDs, clinical content, or raw Scheduler headers.
        logger.info(
            json.dumps(
                {
                    "event": "healthia_gmail_watch_scheduler",
                    "processed_count": payload["processed_count"],
                    "renewed_count": payload["renewed_count"],
                    "disabled_disconnected_count": payload["disabled_disconnected_count"],
                    "scheduler_request_bound": payload["scheduler_request_bound"],
                    "scheduler_job_bound": payload["scheduler_job_bound"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return payload

    @app.post("/internal/ensure-watch")
    async def ensure_watch(payload: EnsureWatchRequest) -> dict[str, Any]:
        worker = runtime()
        try:
            watch, status = worker.watch_manager.ensure_watch(
                payload.patient_id,
                force=payload.force,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"gmail_watch_not_ready:{type(exc).__name__}") from exc
        return {
            "status": status,
            "patient_id": watch.patient_id,
            "email_address": watch.email_address,
            "history_id": watch.history_id,
            "expiration_ms": watch.expiration_ms,
            "secret_material_exposed": False,
        }

    return app


app = create_app()
