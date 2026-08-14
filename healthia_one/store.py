from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from healthia_one.auth import current_patient_id
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
        state = initial or PatientState()
        patient_id = state.profile.id or "patient_demo"
        self._states: dict[str, PatientState] = {patient_id: state.model_copy(deep=True)}
        self._lock = asyncio.Lock()

    async def load(self) -> PatientState:
        patient_id = current_patient_id()
        async with self._lock:
            state = self._states.get(patient_id)
            return (state or PatientState()).model_copy(deep=True)

    async def save(self, state: PatientState) -> None:
        patient_id = current_patient_id()
        async with self._lock:
            state.profile.id = patient_id
            state.updated_at = utc_now()
            self._states[patient_id] = state.model_copy(deep=True)


class JsonStore(StateStore):
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    def _patient_path(self) -> Path:
        patient_id = current_patient_id()
        if patient_id == "patient_demo":
            return self.path
        safe_id = "".join(char for char in patient_id if char.isalnum() or char in {"-", "_"})[:100]
        if not safe_id or safe_id != patient_id:
            raise ValueError("Invalid patient identity")
        return self.path.parent / "patients" / f"{safe_id}.json"

    async def load(self) -> PatientState:
        async with self._lock:
            path = self._patient_path()
            if not path.exists():
                return PatientState()
            data = await asyncio.to_thread(path.read_text, "utf-8")
            state = PatientState.model_validate_json(data)
            expected = current_patient_id()
            if expected != "patient_demo" and state.profile.id != expected:
                raise ValueError("Stored patient identity does not match authenticated principal")
            return state

    async def save(self, state: PatientState) -> None:
        async with self._lock:
            path = self._patient_path()
            patient_id = current_patient_id()
            state.profile.id = patient_id
            state.updated_at = utc_now()
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = state.model_dump_json(indent=2)
            temp = path.with_suffix(path.suffix + ".tmp")
            await asyncio.to_thread(temp.write_text, payload, "utf-8")
            await asyncio.to_thread(temp.replace, path)


class FirestoreStore(StateStore):
    """Patient-scoped Firestore adapter selected from the authenticated principal."""

    _RETRY_DELAYS = (0.0, 0.25, 0.5, 1.0)

    def __init__(self, project: str | None = None) -> None:
        from google.api_core.exceptions import (
            Aborted,
            DeadlineExceeded,
            InternalServerError,
            ServiceUnavailable,
            TooManyRequests,
        )
        from google.cloud import firestore

        self.client = firestore.AsyncClient(project=project)
        self._transient_errors = (
            Aborted,
            DeadlineExceeded,
            InternalServerError,
            ServiceUnavailable,
            TooManyRequests,
        )

    def _ref(self):
        patient_id = current_patient_id()
        return self.client.collection("healthia_one_patients").document(patient_id)

    async def _with_transient_retry(self, operation):
        """Retry only transient Google API failures; validation/auth errors still fail closed."""
        last_error = None
        for delay in self._RETRY_DELAYS:
            if delay:
                await asyncio.sleep(delay)
            try:
                return await operation()
            except self._transient_errors as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    async def load(self) -> PatientState:
        patient_id = current_patient_id()
        ref = self._ref()
        snapshot = await self._with_transient_retry(ref.get)
        if not snapshot.exists:
            return PatientState()
        state = PatientState.model_validate(snapshot.to_dict())
        if state.profile.id != patient_id:
            raise ValueError("Firestore patient identity does not match authenticated principal")
        return state

    async def save(self, state: PatientState) -> None:
        patient_id = current_patient_id()
        state.profile.id = patient_id
        state.updated_at = utc_now()
        ref = self._ref()
        payload = state.model_dump(mode="json")

        async def write():
            return await ref.set(payload)

        await self._with_transient_retry(write)
