from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Response
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
        version="1.0",
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
        # Does not initialize Firestore/Secret Manager and exposes no patient data.
        return {"status": "ok", "service": "healthia-gmail-worker"}

    @app.post("/events/gmail-push")
    async def gmail_push(envelope: dict[str, Any]) -> Any:
        try:
            notification = decode_gmail_pubsub_push(envelope)
        except ValueError:
            # The payload cannot become valid on retry. Cloud Run IAM is the
            # authentication boundary; ack malformed Pub/Sub data without
            # touching Gmail or exposing the body in logs/responses.
            return Response(status_code=204)

        worker = runtime()
        watch = worker.watch_store.load_by_email(notification.email_address)
        if watch is None:
            # An authorized Pub/Sub topic can carry mailbox events that no longer
            # belong to an active HealthIA watch. Ack without querying Gmail.
            return Response(status_code=204)

        # A delayed push can arrive after the patient disconnects Google or
        # switches accounts. Disable the stale cursor and ACK without reading
        # Gmail/Secret Manager. This makes disconnect immediate from HealthIA's
        # perspective even if Gmail/PubSub delivery was already in flight.
        connection = worker.constellation.runtime.oauth_connection_store.load(watch.patient_id)
        mailbox = str(connection.google_account or "").strip().lower() if connection else ""
        if connection is None or not connection.enabled or mailbox != watch.email_address.strip().lower():
            watch.enabled = False
            worker.watch_store.save(watch)
            return Response(status_code=204)

        try:
            missions = worker.bridge.process(watch.patient_id, envelope)
        except PermissionError:
            # Mailbox/watch mismatch is non-retryable and must not read history.
            return Response(status_code=204)
        except Exception as exc:
            # Transient Gmail/Firestore/Gemini failures should be retried by
            # Pub/Sub. Do not leak mailbox, patient, message or secret details.
            raise HTTPException(status_code=503, detail=f"gmail_event_retry:{type(exc).__name__}") from exc
        return {
            "status": "processed",
            "resumed_missions": [item.id for item in missions],
            "count": len(missions),
        }

    @app.post("/scheduled/renew-gmail-watches")
    async def renew_gmail_watches() -> dict[str, Any]:
        worker = runtime()
        try:
            renewed = worker.watch_manager.renew_due()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"gmail_watch_renewal_retry:{type(exc).__name__}") from exc
        return {
            "status": "completed",
            "renewed_count": len(renewed),
            "patient_ids": [patient_id for patient_id, _ in renewed],
        }

    @app.post("/internal/ensure-watch")
    async def ensure_watch(payload: EnsureWatchRequest) -> dict[str, Any]:
        # Private IAM-only bootstrap/repair hook. Mailbox identity is still read
        # from the patient's stored OAuth connection; callers cannot supply it.
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
