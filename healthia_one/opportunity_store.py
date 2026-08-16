from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Protocol

from healthia_one.opportunity_autopilot import OpportunityVault, utc_now


class OpportunityStore(Protocol):
    def load(self, patient_id: str) -> OpportunityVault:
        ...

    def save(self, vault: OpportunityVault) -> None:
        ...


class MemoryOpportunityStore:
    def __init__(self) -> None:
        self._values: dict[str, OpportunityVault] = {}
        self._lock = threading.RLock()

    def load(self, patient_id: str) -> OpportunityVault:
        with self._lock:
            value = self._values.get(patient_id)
            if value is None:
                value = OpportunityVault(patient_id=patient_id)
                self._values[patient_id] = value
            return value.model_copy(deep=True)

    def save(self, vault: OpportunityVault) -> None:
        with self._lock:
            vault.updated_at = utc_now()
            self._values[vault.patient_id] = vault.model_copy(deep=True)


class JsonOpportunityStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read_all(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def load(self, patient_id: str) -> OpportunityVault:
        with self._lock:
            payload = self._read_all().get(patient_id)
            if not payload:
                return OpportunityVault(patient_id=patient_id)
            return OpportunityVault.model_validate(payload)

    def save(self, vault: OpportunityVault) -> None:
        with self._lock:
            values = self._read_all()
            vault.updated_at = utc_now()
            values[vault.patient_id] = vault.model_dump(mode="json")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(values, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            temporary.replace(self.path)


class FirestoreOpportunityStore:
    COLLECTION = "healthia_opportunity_vaults"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.client = firestore.Client(project=project)

    def load(self, patient_id: str) -> OpportunityVault:
        snapshot = self.client.collection(self.COLLECTION).document(patient_id).get()
        if not snapshot.exists:
            return OpportunityVault(patient_id=patient_id)
        payload = snapshot.to_dict() or {}
        payload["patient_id"] = patient_id
        return OpportunityVault.model_validate(payload)

    def save(self, vault: OpportunityVault) -> None:
        vault.updated_at = utc_now()
        self.client.collection(self.COLLECTION).document(vault.patient_id).set(
            vault.model_dump(mode="json")
        )


def build_opportunity_store(settings) -> OpportunityStore:
    if settings.store_backend == "memory":
        return MemoryOpportunityStore()
    if settings.store_backend == "firestore":
        import os

        return FirestoreOpportunityStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    data_path = Path(settings.data_path)
    return JsonOpportunityStore(data_path.parent / "opportunity-vaults.json")
