from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventClaim(BaseModel):
    id: str
    patient_id: str
    event_id: str
    event_type: str
    status: Literal["running", "completed", "failed"] = "running"
    attempts: int = 1
    lease_until: datetime
    last_error: str = ""
    updated_at: datetime = Field(default_factory=utc_now)


class ClaimResult(BaseModel):
    acquired: bool
    duplicate_completed: bool = False
    busy: bool = False
    claim: EventClaim


class EventClaimStore(Protocol):
    def claim(
        self,
        *,
        claim_id: str,
        patient_id: str,
        event_id: str,
        event_type: str,
        lease_seconds: int = 120,
    ) -> ClaimResult:
        ...

    def complete(self, patient_id: str, claim_id: str) -> EventClaim:
        ...

    def fail(self, patient_id: str, claim_id: str, error: str) -> EventClaim:
        ...

    def get(self, patient_id: str, claim_id: str) -> EventClaim | None:
        ...


class MemoryEventClaimStore:
    def __init__(self) -> None:
        self._claims: dict[tuple[str, str], EventClaim] = {}
        self._lock = threading.RLock()

    def claim(self, *, claim_id: str, patient_id: str, event_id: str, event_type: str, lease_seconds: int = 120) -> ClaimResult:
        now = utc_now()
        with self._lock:
            existing = self._claims.get((patient_id, claim_id))
            if existing and existing.status == "completed":
                return ClaimResult(acquired=False, duplicate_completed=True, claim=existing.model_copy(deep=True))
            if existing and existing.status == "running" and existing.lease_until > now:
                return ClaimResult(acquired=False, busy=True, claim=existing.model_copy(deep=True))
            attempts = (existing.attempts + 1) if existing else 1
            claim = EventClaim(
                id=claim_id,
                patient_id=patient_id,
                event_id=event_id,
                event_type=event_type,
                status="running",
                attempts=attempts,
                lease_until=now + timedelta(seconds=max(10, lease_seconds)),
                updated_at=now,
            )
            self._claims[(patient_id, claim_id)] = claim
            return ClaimResult(acquired=True, claim=claim.model_copy(deep=True))

    def complete(self, patient_id: str, claim_id: str) -> EventClaim:
        with self._lock:
            claim = self._claims[(patient_id, claim_id)]
            claim.status = "completed"
            claim.lease_until = utc_now()
            claim.updated_at = utc_now()
            claim.last_error = ""
            return claim.model_copy(deep=True)

    def fail(self, patient_id: str, claim_id: str, error: str) -> EventClaim:
        with self._lock:
            claim = self._claims[(patient_id, claim_id)]
            claim.status = "failed"
            claim.lease_until = utc_now()
            claim.updated_at = utc_now()
            claim.last_error = str(error or "")[:500]
            return claim.model_copy(deep=True)

    def get(self, patient_id: str, claim_id: str) -> EventClaim | None:
        with self._lock:
            claim = self._claims.get((patient_id, claim_id))
            return claim.model_copy(deep=True) if claim else None


class JsonEventClaimStore:
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

    def _write(self, values: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def claim(self, *, claim_id: str, patient_id: str, event_id: str, event_type: str, lease_seconds: int = 120) -> ClaimResult:
        now = utc_now()
        with self._lock:
            values = self._read()
            patient = values.setdefault(patient_id, {})
            raw = patient.get(claim_id)
            existing = EventClaim.model_validate(raw) if raw else None
            if existing and existing.status == "completed":
                return ClaimResult(acquired=False, duplicate_completed=True, claim=existing)
            if existing and existing.status == "running" and existing.lease_until > now:
                return ClaimResult(acquired=False, busy=True, claim=existing)
            claim = EventClaim(
                id=claim_id,
                patient_id=patient_id,
                event_id=event_id,
                event_type=event_type,
                status="running",
                attempts=(existing.attempts + 1) if existing else 1,
                lease_until=now + timedelta(seconds=max(10, lease_seconds)),
                updated_at=now,
            )
            patient[claim_id] = claim.model_dump(mode="json")
            self._write(values)
            return ClaimResult(acquired=True, claim=claim)

    def _mutate(self, patient_id: str, claim_id: str, *, status: str, error: str = "") -> EventClaim:
        with self._lock:
            values = self._read()
            raw = values.get(patient_id, {}).get(claim_id)
            if not raw:
                raise KeyError(claim_id)
            claim = EventClaim.model_validate(raw)
            claim.status = status
            claim.lease_until = utc_now()
            claim.updated_at = utc_now()
            claim.last_error = str(error or "")[:500]
            values[patient_id][claim_id] = claim.model_dump(mode="json")
            self._write(values)
            return claim

    def complete(self, patient_id: str, claim_id: str) -> EventClaim:
        return self._mutate(patient_id, claim_id, status="completed")

    def fail(self, patient_id: str, claim_id: str, error: str) -> EventClaim:
        return self._mutate(patient_id, claim_id, status="failed", error=error)

    def get(self, patient_id: str, claim_id: str) -> EventClaim | None:
        with self._lock:
            raw = self._read().get(patient_id, {}).get(claim_id)
            return EventClaim.model_validate(raw) if raw else None


class FirestoreEventClaimStore:
    COLLECTION = "healthia_autopilot_claims"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.firestore = firestore
        self.client = firestore.Client(project=project)

    def _doc(self, patient_id: str, claim_id: str):
        return (
            self.client.collection(self.COLLECTION)
            .document(patient_id)
            .collection("claims")
            .document(claim_id)
        )

    def claim(self, *, claim_id: str, patient_id: str, event_id: str, event_type: str, lease_seconds: int = 120) -> ClaimResult:
        now = utc_now()
        ref = self._doc(patient_id, claim_id)
        transaction = self.client.transaction()

        @self.firestore.transactional
        def transact(txn):
            snapshot = ref.get(transaction=txn)
            existing = EventClaim.model_validate(snapshot.to_dict()) if snapshot.exists else None
            if existing and existing.status == "completed":
                return ClaimResult(acquired=False, duplicate_completed=True, claim=existing)
            if existing and existing.status == "running" and existing.lease_until > now:
                return ClaimResult(acquired=False, busy=True, claim=existing)
            claim = EventClaim(
                id=claim_id,
                patient_id=patient_id,
                event_id=event_id,
                event_type=event_type,
                status="running",
                attempts=(existing.attempts + 1) if existing else 1,
                lease_until=now + timedelta(seconds=max(10, lease_seconds)),
                updated_at=now,
            )
            txn.set(ref, claim.model_dump(mode="json"))
            return ClaimResult(acquired=True, claim=claim)

        return transact(transaction)

    def _mutate(self, patient_id: str, claim_id: str, *, status: str, error: str = "") -> EventClaim:
        ref = self._doc(patient_id, claim_id)
        snapshot = ref.get()
        if not snapshot.exists:
            raise KeyError(claim_id)
        claim = EventClaim.model_validate(snapshot.to_dict())
        claim.status = status
        claim.lease_until = utc_now()
        claim.updated_at = utc_now()
        claim.last_error = str(error or "")[:500]
        ref.set(claim.model_dump(mode="json"))
        return claim

    def complete(self, patient_id: str, claim_id: str) -> EventClaim:
        return self._mutate(patient_id, claim_id, status="completed")

    def fail(self, patient_id: str, claim_id: str, error: str) -> EventClaim:
        return self._mutate(patient_id, claim_id, status="failed", error=error)

    def get(self, patient_id: str, claim_id: str) -> EventClaim | None:
        snapshot = self._doc(patient_id, claim_id).get()
        return EventClaim.model_validate(snapshot.to_dict()) if snapshot.exists else None


def build_event_claim_store(settings) -> EventClaimStore:
    if settings.store_backend == "memory":
        return MemoryEventClaimStore()
    if settings.store_backend == "firestore":
        import os

        return FirestoreEventClaimStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    data_path = Path(settings.data_path)
    return JsonEventClaimStore(data_path.parent / "autopilot-claims.json")
