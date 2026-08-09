from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AutopilotReceipt(BaseModel):
    """Judge/patient-visible execution receipt; never private chain-of-thought."""

    id: str
    patient_id: str
    event_id: str
    event_type: str
    status: str = "completed"
    cost_class: str = "zero_llm"
    actions: list[dict[str, Any]] = Field(default_factory=list)
    discovery_ids: list[str] = Field(default_factory=list)
    program_ids: list[str] = Field(default_factory=list)
    application_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class AutopilotReceiptStore(Protocol):
    def get(self, patient_id: str, receipt_id: str) -> AutopilotReceipt | None:
        ...

    def save(self, receipt: AutopilotReceipt) -> None:
        ...

    def list_recent(self, patient_id: str, limit: int = 20) -> list[AutopilotReceipt]:
        ...


class MemoryAutopilotReceiptStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], AutopilotReceipt] = {}
        self._lock = threading.RLock()

    def get(self, patient_id: str, receipt_id: str) -> AutopilotReceipt | None:
        with self._lock:
            item = self._values.get((patient_id, receipt_id))
            return item.model_copy(deep=True) if item else None

    def save(self, receipt: AutopilotReceipt) -> None:
        with self._lock:
            self._values[(receipt.patient_id, receipt.id)] = receipt.model_copy(deep=True)

    def list_recent(self, patient_id: str, limit: int = 20) -> list[AutopilotReceipt]:
        with self._lock:
            values = [item for (pid, _), item in self._values.items() if pid == patient_id]
            values.sort(key=lambda item: item.created_at, reverse=True)
            return [item.model_copy(deep=True) for item in values[: max(1, min(limit, 100))]]


class JsonAutopilotReceiptStore:
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

    def get(self, patient_id: str, receipt_id: str) -> AutopilotReceipt | None:
        with self._lock:
            raw = self._read().get(patient_id, {}).get(receipt_id)
            return AutopilotReceipt.model_validate(raw) if raw else None

    def save(self, receipt: AutopilotReceipt) -> None:
        with self._lock:
            values = self._read()
            patient = values.setdefault(receipt.patient_id, {})
            patient[receipt.id] = receipt.model_dump(mode="json")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)

    def list_recent(self, patient_id: str, limit: int = 20) -> list[AutopilotReceipt]:
        with self._lock:
            values = [
                AutopilotReceipt.model_validate(raw)
                for raw in self._read().get(patient_id, {}).values()
            ]
        values.sort(key=lambda item: item.created_at, reverse=True)
        return values[: max(1, min(limit, 100))]


class FirestoreAutopilotReceiptStore:
    COLLECTION = "healthia_autopilot_receipts"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.client = firestore.Client(project=project)

    def _document(self, patient_id: str, receipt_id: str):
        return (
            self.client.collection(self.COLLECTION)
            .document(patient_id)
            .collection("receipts")
            .document(receipt_id)
        )

    def get(self, patient_id: str, receipt_id: str) -> AutopilotReceipt | None:
        snapshot = self._document(patient_id, receipt_id).get()
        return AutopilotReceipt.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, receipt: AutopilotReceipt) -> None:
        self._document(receipt.patient_id, receipt.id).set(receipt.model_dump(mode="json"))

    def list_recent(self, patient_id: str, limit: int = 20) -> list[AutopilotReceipt]:
        from google.cloud import firestore

        query = (
            self.client.collection(self.COLLECTION)
            .document(patient_id)
            .collection("receipts")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(max(1, min(limit, 100)))
        )
        return [AutopilotReceipt.model_validate(item.to_dict()) for item in query.stream()]


def build_autopilot_receipt_store(settings) -> AutopilotReceiptStore:
    if settings.store_backend == "memory":
        return MemoryAutopilotReceiptStore()
    if settings.store_backend == "firestore":
        import os

        return FirestoreAutopilotReceiptStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    data_path = Path(settings.data_path)
    return JsonAutopilotReceiptStore(data_path.parent / "autopilot-receipts.json")
