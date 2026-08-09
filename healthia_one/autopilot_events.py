from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from healthia_one.autopilot_runtime import AutopilotEvent


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stable_event_id(patient_id: str, event_type: str, dedupe_key: str) -> str:
    raw = f"{patient_id}|{event_type}|{dedupe_key}"
    return "event_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class OutboxRecord(BaseModel):
    id: str
    patient_id: str
    event: AutopilotEvent
    status: Literal["pending", "processed", "failed"] = "pending"
    attempts: int = 0
    last_error: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EventOutboxStore(Protocol):
    def put(self, event: AutopilotEvent) -> OutboxRecord:
        ...

    def get(self, event_id: str) -> OutboxRecord | None:
        ...

    def mark_processed(self, event_id: str) -> OutboxRecord:
        ...

    def mark_failed(self, event_id: str, error: str) -> OutboxRecord:
        ...


class MemoryEventOutboxStore:
    def __init__(self) -> None:
        self._values: dict[str, OutboxRecord] = {}
        self._lock = threading.RLock()

    def put(self, event: AutopilotEvent) -> OutboxRecord:
        with self._lock:
            existing = self._values.get(event.id)
            if existing:
                return existing.model_copy(deep=True)
            record = OutboxRecord(id=event.id, patient_id=event.patient_id, event=event)
            self._values[event.id] = record
            return record.model_copy(deep=True)

    def get(self, event_id: str) -> OutboxRecord | None:
        with self._lock:
            record = self._values.get(event_id)
            return record.model_copy(deep=True) if record else None

    def _mark(self, event_id: str, status: str, error: str = "") -> OutboxRecord:
        with self._lock:
            record = self._values[event_id]
            record.status = status
            record.attempts += 1
            record.last_error = str(error or "")[:500]
            record.updated_at = utc_now()
            return record.model_copy(deep=True)

    def mark_processed(self, event_id: str) -> OutboxRecord:
        return self._mark(event_id, "processed")

    def mark_failed(self, event_id: str, error: str) -> OutboxRecord:
        return self._mark(event_id, "failed", error)


class JsonEventOutboxStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, values: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def put(self, event: AutopilotEvent) -> OutboxRecord:
        with self._lock:
            values = self._read()
            raw = values.get(event.id)
            if raw:
                return OutboxRecord.model_validate(raw)
            record = OutboxRecord(id=event.id, patient_id=event.patient_id, event=event)
            values[event.id] = record.model_dump(mode="json")
            self._write(values)
            return record

    def get(self, event_id: str) -> OutboxRecord | None:
        with self._lock:
            raw = self._read().get(event_id)
            return OutboxRecord.model_validate(raw) if raw else None

    def _mark(self, event_id: str, status: str, error: str = "") -> OutboxRecord:
        with self._lock:
            values = self._read()
            raw = values.get(event_id)
            if not raw:
                raise KeyError(event_id)
            record = OutboxRecord.model_validate(raw)
            record.status = status
            record.attempts += 1
            record.last_error = str(error or "")[:500]
            record.updated_at = utc_now()
            values[event_id] = record.model_dump(mode="json")
            self._write(values)
            return record

    def mark_processed(self, event_id: str) -> OutboxRecord:
        return self._mark(event_id, "processed")

    def mark_failed(self, event_id: str, error: str) -> OutboxRecord:
        return self._mark(event_id, "failed", error)


class FirestoreEventOutboxStore:
    """Top-level collection intentionally shaped for a direct Eventarc trigger."""

    COLLECTION = "healthia_autopilot_events"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.client = firestore.Client(project=project)

    def _ref(self, event_id: str):
        return self.client.collection(self.COLLECTION).document(event_id)

    def put(self, event: AutopilotEvent) -> OutboxRecord:
        ref = self._ref(event.id)
        transaction = self.client.transaction()

        from google.cloud import firestore

        @firestore.transactional
        def transact(txn):
            snapshot = ref.get(transaction=txn)
            if snapshot.exists:
                return OutboxRecord.model_validate(snapshot.to_dict())
            record = OutboxRecord(id=event.id, patient_id=event.patient_id, event=event)
            txn.create(ref, record.model_dump(mode="json"))
            return record

        return transact(transaction)

    def get(self, event_id: str) -> OutboxRecord | None:
        snapshot = self._ref(event_id).get()
        return OutboxRecord.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def _mark(self, event_id: str, status: str, error: str = "") -> OutboxRecord:
        ref = self._ref(event_id)
        snapshot = ref.get()
        if not snapshot.exists:
            raise KeyError(event_id)
        record = OutboxRecord.model_validate(snapshot.to_dict())
        record.status = status
        record.attempts += 1
        record.last_error = str(error or "")[:500]
        record.updated_at = utc_now()
        ref.set(record.model_dump(mode="json"))
        return record

    def mark_processed(self, event_id: str) -> OutboxRecord:
        return self._mark(event_id, "processed")

    def mark_failed(self, event_id: str, error: str) -> OutboxRecord:
        return self._mark(event_id, "failed", error)


def build_event_outbox_store(settings) -> EventOutboxStore:
    if settings.store_backend == "memory":
        return MemoryEventOutboxStore()
    if settings.store_backend == "firestore":
        import os

        return FirestoreEventOutboxStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    data_path = Path(settings.data_path)
    return JsonEventOutboxStore(data_path.parent / "autopilot-events.json")
