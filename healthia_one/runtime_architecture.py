from __future__ import annotations

import asyncio
import copy
import time
from typing import Any

from healthia_one.auth import patient_scope
from healthia_one.distributed_events import FirestoreEventBroker
from healthia_one.evidence_store import configured_bucket
from healthia_one.pairing import DevicePairingManager
from healthia_one.pairing_backends import FirestorePairingBackend
from healthia_one.service import HealthIAService


_READINESS_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_READINESS_CACHE_SECONDS = 5.0


class ResilientHealthIAService(HealthIAService):
    """HealthIA runtime whose process liveness is independent of cloud readiness.

    Local/test startup remains fail-fast. In cloud mode a transient dependency
    outage is recorded instead of killing the ASGI process, allowing `/healthz`
    to remain a pure liveness signal while `/api/readiness` fails closed until
    the complete startup contract succeeds on a later retry.
    """

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.startup_error: str | None = None
        if settings.store_backend == "firestore":
            self.broker = FirestoreEventBroker(project=settings.google_cloud_project or None)

    async def initialize(self) -> None:
        try:
            await super().initialize()
            self.startup_error = None
        except Exception as exc:
            if self.settings.env.strip().lower() != "cloud":
                raise
            # Do not expose credentials, URLs or raw exception messages through
            # public readiness. The exception class is enough for operations to
            # distinguish dependency categories while traces retain internals.
            self.startup_error = type(exc).__name__

    async def recover_startup(self) -> bool:
        """Retry the full initialization contract after a degraded cloud start."""
        try:
            await super().initialize()
        except Exception as exc:
            self.startup_error = type(exc).__name__
            return False
        self.startup_error = None
        return True


def build_service(settings) -> ResilientHealthIAService:
    return ResilientHealthIAService(settings)


def build_pairing_manager(settings) -> DevicePairingManager:
    if settings.store_backend == "firestore":
        backend = FirestorePairingBackend(project=settings.google_cloud_project or None)
        return DevicePairingManager(backend=backend)
    return DevicePairingManager()


async def _probe_startup_recovery(service: ResilientHealthIAService, timeout_seconds: float) -> dict:
    if service.startup_error is None:
        return {"ready": True, "mode": "startup_complete"}
    try:
        recovered = await asyncio.wait_for(service.recover_startup(), timeout=timeout_seconds)
    except Exception as exc:
        service.startup_error = type(exc).__name__
        return {"ready": False, "mode": "startup_retry", "error": type(exc).__name__}
    if not recovered:
        return {"ready": False, "mode": "startup_retry", "error": service.startup_error}
    return {"ready": True, "mode": "startup_retry_recovered"}


async def _probe_state_store(service: HealthIAService, timeout_seconds: float) -> dict:
    try:
        # A non-mutating read through the exact production adapter proves ADC,
        # project routing, Firestore reachability and datastore permissions. The
        # id obeys the same patient-scope format contract as real principals.
        with patient_scope("patient_readiness_probe"):
            await asyncio.wait_for(service.store.load(), timeout=timeout_seconds)
        return {"ready": True, "mode": "live_read"}
    except Exception as exc:
        return {"ready": False, "mode": "live_read", "error": type(exc).__name__}


async def _probe_evidence_store(settings, timeout_seconds: float) -> dict:
    bucket_name = configured_bucket()
    if not bucket_name:
        return {"ready": True, "backend": "local", "mode": "filesystem"}

    def list_one_object() -> None:
        from google.cloud import storage

        client = storage.Client(project=settings.google_cloud_project or None)
        # Runtime has object-level permissions. Listing one object proves the
        # private evidence bucket is reachable without writing or reading PHI.
        iterator = client.list_blobs(bucket_name, max_results=1)
        next(iter(iterator), None)

    try:
        await asyncio.wait_for(asyncio.to_thread(list_one_object), timeout=timeout_seconds)
        return {"ready": True, "backend": "gcs", "mode": "live_object_list"}
    except Exception as exc:
        return {"ready": False, "backend": "gcs", "mode": "live_object_list", "error": type(exc).__name__}


def _configuration_checks(service, settings, pairing_manager, fcm_registration_store) -> dict:
    cloud = settings.env.strip().lower() == "cloud"
    firestore = settings.store_backend == "firestore"
    pairing_backend = getattr(pairing_manager, "backend", None)
    pairing_persistence = getattr(pairing_manager, "session_persistence", "process_local")
    fcm_persistence = "firestore" if fcm_registration_store.__class__.__name__.startswith("Firestore") else "memory"
    event_persistence = getattr(service.broker, "persistence", "process_local")

    checks = {
        "cloud_contract": (not cloud) or bool(settings.google_cloud_project),
        "ai_configuration": settings.llm_backend == "mock" or bool(settings.adk_ready),
        "one_safety_cloud_gate": (not cloud) or bool(settings.one_safety_auto_enable_cloud and settings.model_armor_enabled),
        "device_credentials_restart_safe": (not cloud) or pairing_manager.credential_persistence == "restart_safe",
        "pairing_distributed": (not firestore) or pairing_persistence == "firestore_transactional",
        "events_distributed": (not firestore) or event_persistence == "firestore_snapshot_listener",
        "fcm_durable": (not firestore) or fcm_persistence == "firestore",
        "pairing_backend_present": (not firestore) or pairing_backend is not None,
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "pairing_persistence": pairing_persistence,
        "event_persistence": event_persistence,
        "fcm_persistence": fcm_persistence,
    }


async def runtime_readiness(
    service,
    settings,
    pairing_manager,
    fcm_registration_store,
    *,
    timeout_seconds: float = 3.0,
    force: bool = False,
) -> dict:
    """Return bounded, no-AI-spend readiness based on live mandatory dependencies."""

    now = time.monotonic()
    cached = _READINESS_CACHE.get("payload")
    if not force and cached is not None and now - float(_READINESS_CACHE.get("at") or 0.0) < _READINESS_CACHE_SECONDS:
        return copy.deepcopy(cached)

    config = _configuration_checks(service, settings, pairing_manager, fcm_registration_store)
    startup = await _probe_startup_recovery(service, timeout_seconds)
    store = await _probe_state_store(service, timeout_seconds)
    evidence = await _probe_evidence_store(settings, timeout_seconds)
    ready = bool(config["ready"] and startup["ready"] and store["ready"] and evidence["ready"])
    payload = {
        "ready": ready,
        "startup_error": service.startup_error,
        "startup": startup,
        "store": store,
        "evidence": evidence,
        "runtime": config,
        "probe_budget_seconds": timeout_seconds,
        "ai_probe_performed": False,
        "ai_spend": "zero",
    }
    _READINESS_CACHE["at"] = now
    _READINESS_CACHE["payload"] = copy.deepcopy(payload)
    return payload
