from __future__ import annotations

import threading

from healthia_one.google_constellation_runtime import (
    GoogleConstellationService,
    build_google_constellation_service,
)


_LOCK = threading.RLock()
_SERVICES: dict[tuple[str, str, str], GoogleConstellationService] = {}


def _key(settings) -> tuple[str, str, str]:
    return (
        str(settings.env),
        str(settings.store_backend),
        str(settings.data_path),
    )


def get_google_constellation_service(settings) -> GoogleConstellationService:
    """Return one process-local facade over the durable Google mission stores.

    In Firestore mode process-local identity is an optimization only; durable
    stores remain authoritative across Cloud Run instances. In Memory mode this
    singleton is essential so API/chat/ADK tests see the same mission state.
    """
    key = _key(settings)
    with _LOCK:
        service = _SERVICES.get(key)
        if service is None:
            service = build_google_constellation_service(settings)
            _SERVICES[key] = service
        return service


def reset_google_constellation_singletons_for_tests() -> None:
    with _LOCK:
        _SERVICES.clear()
