from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from healthia_one.models import PatientState, utc_now


class StateStore(ABC):
    @abstractmethod
    async def load(self) -> PatientState:
        raise NotImplementedError

    @abstractmethod
    async def save(self, state: PatientState) -> None:
        raise NotImplementedError


class MemoryStore(StateStore):
    def __init__(self, initial: PatientState | None = None) -> None:
        self._state = initial or PatientState()
        self._lock = asyncio.Lock()

    async def load(self) -> PatientState:
        async with self._lock:
            return self._state.model_copy(deep=True)

    async def save(self, state: PatientState) -> None:
        async with self._lock:
            state.updated_at = utc_now()
            self._state = state.model_copy(deep=True)


class JsonStore(StateStore):
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def load(self) -> PatientState:
        async with self._lock:
            if not self.path.exists():
                return PatientState()
            data = await asyncio.to_thread(self.path.read_text, "utf-8")
            return PatientState.model_validate_json(data)

    async def save(self, state: PatientState) -> None:
        async with self._lock:
            state.updated_at = utc_now()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = state.model_dump_json(indent=2)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            await asyncio.to_thread(temp.write_text, payload, "utf-8")
            await asyncio.to_thread(temp.replace, self.path)


class FirestoreStore(StateStore):
    """Production adapter for one demo patient document.

    The class is intentionally small: it keeps the state contract identical to the local store,
    while Firestore transactions/idempotency can be hardened without changing the UI or agents.
    """

    def __init__(self, project: str | None = None, patient_id: str = "patient_demo") -> None:
        from google.cloud import firestore

        self.client = firestore.AsyncClient(project=project)
        self.ref = self.client.collection("healthia_one_patients").document(patient_id)

    async def load(self) -> PatientState:
        snapshot = await self.ref.get()
        if not snapshot.exists:
            return PatientState()
        return PatientState.model_validate(snapshot.to_dict())

    async def save(self, state: PatientState) -> None:
        state.updated_at = utc_now()
        await self.ref.set(state.model_dump(mode="json"))
