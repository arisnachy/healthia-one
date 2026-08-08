from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from healthia_one.models import PatientState, utc_now
from healthia_one.tenant import DEFAULT_PATIENT_ID, current_patient_id


class StateStore(ABC):
    @abstractmethod
    async def load(self) -> PatientState:
        raise NotImplementedError

    @abstractmethod
    async def save(self, state: PatientState) -> None:
        raise NotImplementedError


class MemoryStore(StateStore):
    """Request-scoped in-memory state used by tests and zero-spend demos."""

    def __init__(self, initial: PatientState | None = None) -> None:
        self._states: dict[str, PatientState] = {}
        if initial is not None:
            self._states[DEFAULT_PATIENT_ID] = initial.model_copy(deep=True)
        self._lock = asyncio.Lock()

    async def load(self) -> PatientState:
        patient_id = current_patient_id()
        async with self._lock:
            state = self._states.get(patient_id)
            return state.model_copy(deep=True) if state is not None else PatientState()

    async def save(self, state: PatientState) -> None:
        patient_id = current_patient_id()
        async with self._lock:
            state.updated_at = utc_now()
            self._states[patient_id] = state.model_copy(deep=True)


class JsonStore(StateStore):
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    def _scoped_path(self) -> Path:
        patient_id = current_patient_id()
        if patient_id == DEFAULT_PATIENT_ID:
            return self.path
        safe_id = "".join(char for char in patient_id if char.isalnum() or char in {"-", "_"})[:96]
        if not safe_id:
            raise ValueError("Invalid local patient identity")
        return self.path.with_name(f"{self.path.stem}-{safe_id}{self.path.suffix}")

    async def load(self) -> PatientState:
        async with self._lock:
            path = self._scoped_path()
            if not path.exists():
                return PatientState()
            data = await asyncio.to_thread(path.read_text, "utf-8")
            return PatientState.model_validate_json(data)

    async def save(self, state: PatientState) -> None:
        async with self._lock:
            path = self._scoped_path()
            state.updated_at = utc_now()
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = state.model_dump_json(indent=2)
            temp = path.with_suffix(path.suffix + ".tmp")
            await asyncio.to_thread(temp.write_text, payload, "utf-8")
            await asyncio.to_thread(temp.replace, path)


class FirestoreStore(StateStore):
    """Per-user Firestore adapter keyed exclusively by the verified Identity Platform uid."""

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self.client = firestore.AsyncClient(project=project)
        self.collection = self.client.collection("healthia_one_patients")

    def _ref(self):
        return self.collection.document(current_patient_id())

    async def load(self) -> PatientState:
        snapshot = await self._ref().get()
        if not snapshot.exists:
            return PatientState()
        return PatientState.model_validate(snapshot.to_dict())

    async def save(self, state: PatientState) -> None:
        state.updated_at = utc_now()
        await self._ref().set(state.model_dump(mode="json"))
