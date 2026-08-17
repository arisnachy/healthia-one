from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Protocol

from pydantic import BaseModel, Field

from healthia_one.google_constellation import ACTION_POLICIES, GoogleAction, GoogleActionRequest, new_id
from healthia_one.google_constellation_store import build_action_intent_key


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HealthActionTicket(BaseModel):
    """Ephemeral, one-time execution capability issued by ONE SAFETY.

    Patient authorization answers *may this exact action be attempted?*.
    The ticket answers *may this exact execution attempt cross the connector
    boundary now?*. A connector receipt remains the only proof that external
    work actually happened.
    """

    id: str = Field(default_factory=lambda: new_id("hat"))
    patient_id: str
    mission_id: str
    action: GoogleAction
    intent_key: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=64, max_length=64)
    authorization_id: str = ""
    payload_hash: str = Field(min_length=64, max_length=64)
    trace_id: str = ""
    issued_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    consumed_at: datetime | None = None
    receipt_id: str = ""
    outcome_status: str = "pending"

    @property
    def status(self) -> str:
        now = utc_now()
        if self.consumed_at is not None:
            return "consumed"
        if self.expires_at <= now:
            return "expired"
        return "issued"


class HealthActionTicketStore(Protocol):
    def save(self, ticket: HealthActionTicket) -> None: ...
    def get(self, patient_id: str, ticket_id: str) -> HealthActionTicket | None: ...
    def consume(self, patient_id: str, ticket_id: str) -> HealthActionTicket: ...
    def record_outcome(self, patient_id: str, ticket_id: str, *, receipt_id: str, status: str) -> HealthActionTicket: ...
    def recent(self, patient_id: str, *, limit: int = 20) -> list[HealthActionTicket]: ...


class MemoryHealthActionTicketStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], HealthActionTicket] = {}
        self._lock = threading.RLock()

    def save(self, ticket: HealthActionTicket) -> None:
        with self._lock:
            self._values[(ticket.patient_id, ticket.id)] = ticket.model_copy(deep=True)

    def get(self, patient_id: str, ticket_id: str) -> HealthActionTicket | None:
        with self._lock:
            value = self._values.get((patient_id, ticket_id))
            return value.model_copy(deep=True) if value else None

    def consume(self, patient_id: str, ticket_id: str) -> HealthActionTicket:
        with self._lock:
            value = self._values.get((patient_id, ticket_id))
            if value is None:
                raise KeyError(ticket_id)
            if value.expires_at <= utc_now():
                raise PermissionError("HealthActionTicket expired")
            if value.consumed_at is not None:
                raise PermissionError("HealthActionTicket was already consumed")
            value.consumed_at = utc_now()
            self._values[(patient_id, ticket_id)] = value
            return value.model_copy(deep=True)

    def record_outcome(self, patient_id: str, ticket_id: str, *, receipt_id: str, status: str) -> HealthActionTicket:
        with self._lock:
            value = self._values.get((patient_id, ticket_id))
            if value is None:
                raise KeyError(ticket_id)
            value.receipt_id = receipt_id
            value.outcome_status = status
            self._values[(patient_id, ticket_id)] = value
            return value.model_copy(deep=True)

    def recent(self, patient_id: str, *, limit: int = 20) -> list[HealthActionTicket]:
        with self._lock:
            items = [value.model_copy(deep=True) for (pid, _), value in self._values.items() if pid == patient_id]
        items.sort(key=lambda item: item.issued_at, reverse=True)
        return items[: max(1, min(int(limit), 100))]


class FirestoreHealthActionTicketStore:
    COLLECTION = "healthia_action_tickets"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.firestore = firestore
        self.client = firestore.Client(project=project)

    def _collection(self, patient_id: str):
        return self.client.collection(self.COLLECTION).document(patient_id).collection("tickets")

    def _doc(self, patient_id: str, ticket_id: str):
        return self._collection(patient_id).document(ticket_id)

    def save(self, ticket: HealthActionTicket) -> None:
        self._doc(ticket.patient_id, ticket.id).set(ticket.model_dump(mode="json"))

    def get(self, patient_id: str, ticket_id: str) -> HealthActionTicket | None:
        snapshot = self._doc(patient_id, ticket_id).get()
        return HealthActionTicket.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def consume(self, patient_id: str, ticket_id: str) -> HealthActionTicket:
        ref = self._doc(patient_id, ticket_id)
        transaction = self.client.transaction()

        @self.firestore.transactional
        def _consume(tx):
            snapshot = ref.get(transaction=tx)
            if not snapshot.exists:
                raise KeyError(ticket_id)
            ticket = HealthActionTicket.model_validate(snapshot.to_dict())
            if ticket.expires_at <= utc_now():
                raise PermissionError("HealthActionTicket expired")
            if ticket.consumed_at is not None:
                raise PermissionError("HealthActionTicket was already consumed")
            ticket.consumed_at = utc_now()
            tx.set(ref, ticket.model_dump(mode="json"))
            return ticket

        return _consume(transaction)

    def record_outcome(self, patient_id: str, ticket_id: str, *, receipt_id: str, status: str) -> HealthActionTicket:
        ref = self._doc(patient_id, ticket_id)
        snapshot = ref.get()
        if not snapshot.exists:
            raise KeyError(ticket_id)
        ticket = HealthActionTicket.model_validate(snapshot.to_dict())
        ticket.receipt_id = receipt_id
        ticket.outcome_status = status
        ref.set(ticket.model_dump(mode="json"))
        return ticket

    def recent(self, patient_id: str, *, limit: int = 20) -> list[HealthActionTicket]:
        query = self._collection(patient_id).order_by("issued_at", direction=self.firestore.Query.DESCENDING).limit(max(1, min(int(limit), 100)))
        return [HealthActionTicket.model_validate(snapshot.to_dict()) for snapshot in query.stream()]


class HealthIASafetyKernel:
    """Deterministic final gate before any Google connector execution."""

    def __init__(self, ticket_store: HealthActionTicketStore, *, ticket_ttl_seconds: int = 90) -> None:
        self.ticket_store = ticket_store
        self.ticket_ttl_seconds = max(15, min(int(ticket_ttl_seconds), 300))

    @staticmethod
    def _payload_hash(request: GoogleActionRequest) -> str:
        payload = json.dumps(request.payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def issue(
        self,
        request: GoogleActionRequest,
        *,
        authorization_id: str,
        idempotency_key: str,
        trace_id: str = "",
    ) -> HealthActionTicket:
        if not request.patient_id.strip() or not request.mission_id.strip():
            raise PermissionError("Safety Kernel requires patient and mission binding")
        policy = ACTION_POLICIES[request.action]
        if policy.explicit_authorization_required and not authorization_id.strip():
            raise PermissionError("Safety Kernel requires explicit action authorization")
        normalized_trace = trace_id.strip().lower()
        if normalized_trace and (len(normalized_trace) != 32 or any(ch not in "0123456789abcdef" for ch in normalized_trace)):
            raise ValueError("Safety Kernel requires a canonical 32-hex trace id")
        now = utc_now()
        ticket = HealthActionTicket(
            patient_id=request.patient_id,
            mission_id=request.mission_id,
            action=request.action,
            intent_key=build_action_intent_key(request),
            idempotency_key=idempotency_key,
            authorization_id=authorization_id.strip(),
            payload_hash=self._payload_hash(request),
            trace_id=normalized_trace,
            issued_at=now,
            expires_at=now + timedelta(seconds=self.ticket_ttl_seconds),
        )
        self.ticket_store.save(ticket)
        return ticket

    def consume(self, ticket: HealthActionTicket, request: GoogleActionRequest, *, idempotency_key: str) -> HealthActionTicket:
        if ticket.patient_id != request.patient_id or ticket.mission_id != request.mission_id or ticket.action != request.action:
            raise PermissionError("HealthActionTicket scope mismatch")
        if ticket.intent_key != build_action_intent_key(request):
            raise PermissionError("HealthActionTicket intent mismatch")
        if ticket.payload_hash != self._payload_hash(request):
            raise PermissionError("HealthActionTicket payload mismatch")
        if ticket.idempotency_key != idempotency_key:
            raise PermissionError("HealthActionTicket idempotency mismatch")
        return self.ticket_store.consume(request.patient_id, ticket.id)

    def record_outcome(self, ticket: HealthActionTicket, *, receipt_id: str, status: str) -> HealthActionTicket:
        return self.ticket_store.record_outcome(
            ticket.patient_id,
            ticket.id,
            receipt_id=receipt_id,
            status=status,
        )
