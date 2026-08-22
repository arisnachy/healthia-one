from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from healthia_one.auth import current_patient_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FirestoreEventBroker:
    """Cross-instance event fan-out for SSE clients.

    Canonical patient state remains in the normal PatientState store. These
    short-lived documents are only delivery hints for connected clients; a
    reconnect always rebuilds the UI from `/api/bootstrap`. Firestore snapshot
    listeners make the fan-out work across Cloud Run instances without an
    in-process queue dependency.
    """

    COLLECTION = "healthia_event_streams"
    persistence = "firestore_snapshot_listener"

    def __init__(self, project: str | None = None, *, retention_minutes: int = 15) -> None:
        self.project = project
        self.retention_minutes = max(5, min(int(retention_minutes), 60))
        self._firestore = None
        self._client = None

    @property
    def firestore(self):
        if self._firestore is None:
            from google.cloud import firestore

            self._firestore = firestore
        return self._firestore

    @property
    def client(self):
        if self._client is None:
            self._client = self.firestore.Client(project=self.project)
        return self._client

    @property
    def client_initialized(self) -> bool:
        return self._client is not None

    @staticmethod
    def _stream_id(patient_id: str) -> str:
        # Avoid putting raw patient identifiers in Firestore document paths.
        return hashlib.sha256(patient_id.encode("utf-8")).hexdigest()

    def _events(self, patient_id: str):
        return self.client.collection(self.COLLECTION).document(self._stream_id(patient_id)).collection("events")

    async def publish(self, payload: dict, patient_id: str | None = None) -> None:
        target_patient = patient_id or current_patient_id()
        created_at = utc_now()
        event_id = f"evt_{created_at.strftime('%Y%m%d%H%M%S%f')}_{secrets.token_hex(6)}"
        record = {
            "event_id": event_id,
            "payload": payload,
            "created_at": created_at,
            # Configure this field as a Firestore TTL policy. Correctness never
            # depends on deletion because subscribers ignore pre-subscription
            # events and canonical state is stored elsewhere.
            "expires_at": created_at + timedelta(minutes=self.retention_minutes),
        }
        await asyncio.to_thread(self._events(target_patient).document(event_id).create, record)

    async def subscribe(self, patient_id: str | None = None) -> AsyncIterator[dict]:
        target_patient = patient_id or current_patient_id()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        started_at = utc_now()
        seen: set[str] = set()

        def enqueue(event_id: str, payload: dict) -> None:
            if event_id in seen:
                return
            seen.add(event_id)
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

        def on_snapshot(_documents, changes, _read_time) -> None:
            for change in changes:
                document = change.document
                event_id = document.id
                data = document.to_dict() or {}
                created_at = data.get("created_at")
                if isinstance(created_at, datetime):
                    created_at = created_at.astimezone(timezone.utc)
                    if created_at < started_at:
                        continue
                payload = data.get("payload")
                if not isinstance(payload, dict):
                    continue
                loop.call_soon_threadsafe(enqueue, event_id, payload)

        watch = await asyncio.to_thread(self._events(target_patient).on_snapshot, on_snapshot)
        try:
            while True:
                yield await queue.get()
        finally:
            await asyncio.to_thread(watch.unsubscribe)
