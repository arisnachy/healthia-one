from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

# Opportunity integration is imported by the central orchestrator after the core
# Google mission module is loaded. Installing the Wave 4 vocabulary here widens
# only the deterministic mission entry phrases; the existing Google mission
# consent/policy/runtime continues to own every actual external action.
from healthia_one import wave4_resource_routing as _wave4_resource_routing  # noqa: F401


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RadarPermissions(BaseModel):
    patient_id: str
    scientific_enabled: bool = False
    resource_enabled: bool = False
    updated_at: datetime = Field(default_factory=utc_now)


class RadarPermissionStore(Protocol):
    def load(self, patient_id: str) -> RadarPermissions:
        ...

    def save(self, permissions: RadarPermissions) -> None:
        ...


class MemoryRadarPermissionStore:
    def __init__(self) -> None:
        self._values: dict[str, RadarPermissions] = {}
        self._lock = threading.RLock()

    def load(self, patient_id: str) -> RadarPermissions:
        with self._lock:
            value = self._values.get(patient_id) or RadarPermissions(patient_id=patient_id)
            return value.model_copy(deep=True)

    def save(self, permissions: RadarPermissions) -> None:
        with self._lock:
            permissions.updated_at = utc_now()
            self._values[permissions.patient_id] = permissions.model_copy(deep=True)


class JsonRadarPermissionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def load(self, patient_id: str) -> RadarPermissions:
        with self._lock:
            raw = self._read().get(patient_id)
            return RadarPermissions.model_validate(raw) if raw else RadarPermissions(patient_id=patient_id)

    def save(self, permissions: RadarPermissions) -> None:
        with self._lock:
            values = self._read()
            permissions.updated_at = utc_now()
            values[permissions.patient_id] = permissions.model_dump(mode="json")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)


class FirestoreRadarPermissionStore:
    COLLECTION = "healthia_opportunity_permissions"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.client = firestore.Client(project=project)

    def load(self, patient_id: str) -> RadarPermissions:
        snapshot = self.client.collection(self.COLLECTION).document(patient_id).get()
        return (
            RadarPermissions.model_validate(snapshot.to_dict())
            if snapshot.exists
            else RadarPermissions(patient_id=patient_id)
        )

    def save(self, permissions: RadarPermissions) -> None:
        permissions.updated_at = utc_now()
        self.client.collection(self.COLLECTION).document(permissions.patient_id).set(
            permissions.model_dump(mode="json")
        )


def build_radar_permission_store(settings) -> RadarPermissionStore:
    if settings.store_backend == "memory":
        return MemoryRadarPermissionStore()
    if settings.store_backend == "firestore":
        import os

        return FirestoreRadarPermissionStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    data_path = Path(settings.data_path)
    return JsonRadarPermissionStore(data_path.parent / "opportunity-permissions.json")