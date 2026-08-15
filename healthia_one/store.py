from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from healthia_one.auth import current_patient_id
from healthia_one.models import PatientState, utc_now


PATIENT_STATE_COLLECTION = "healthia_one_patients"


def _prepare_autonomous_state(state: PatientState) -> bool:
    """Reconcile state-only autonomous work before the canonical commit."""
    from healthia_one.appointment_guardian import reconcile_appointment_guardian
    from healthia_one.bp_followup_guardian import reconcile_bp_followup_guardian
    from healthia_one.medication_followup_guardian import reconcile_medication_followup_guardian
    from healthia_one.postvisit_guardian import reconcile_postvisit_guardian
    from healthia_one.result_guardian import reconcile_result_guardian

    result_report = reconcile_result_guardian(state)
    appointment_report = reconcile_appointment_guardian(state)
    postvisit_report = reconcile_postvisit_guardian(state)
    bp_report = reconcile_bp_followup_guardian(state)
    medication_report = reconcile_medication_followup_guardian(state)
    result_changed = bool(
        result_report.get("opened")
        or result_report.get("resolved")
        or result_report.get("new_result_ids")
    )
    appointment_changed = any(
        appointment_report.get(key)
        for key in ("created", "waiting", "completed", "cancelled")
    )
    postvisit_changed = any(
        postvisit_report.get(key)
        for key in ("created", "waiting", "completed")
    )
    bp_changed = any(
        bp_report.get(key)
        for key in ("created", "waiting", "completed", "safety_handoff")
    )
    medication_changed = any(
        medication_report.get(key)
        for key in ("created", "waiting", "completed", "review_handoff")
    )
    return (
        result_changed
        or appointment_changed
        or postvisit_changed
        or bp_changed
        or medication_changed
    )


async def _flush_post_commit_intents(state: PatientState) -> bool:
    """Flush staged Autopilot work only after PatientState is durable."""
    from healthia_one.autopilot_event_intents import flush_event_intents, pending_event_intents

    if not pending_event_intents(state):
        return False
    from healthia_one.opportunity_integration import outbox

    report = await asyncio.to_thread(flush_event_intents, state, outbox())
    return bool(report.get("state_changed"))


class StateStore(ABC):
    def __init__(self, *, autonomous_enabled: bool = True) -> None:
        self.autonomous_enabled = bool(autonomous_enabled)

    def _reconcile_if_enabled(self, state: PatientState) -> bool:
        if not self.autonomous_enabled:
            return False
        return _prepare_autonomous_state(state)

    @abstractmethod
    async def load(self) -> PatientState:
        raise NotImplementedError

    @abstractmethod
    async def save(self, state: PatientState) -> None:
        raise NotImplementedError


class MemoryStore(StateStore):
    def __init__(self, initial: PatientState | None = None, *, autonomous_enabled: bool = True) -> None:
        super().__init__(autonomous_enabled=autonomous_enabled)
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
            self._reconcile_if_enabled(state)
            state.updated_at = utc_now()
            self._states[patient_id] = state.model_copy(deep=True)
            if await _flush_post_commit_intents(state):
                state.updated_at = utc_now()
                self._states[patient_id] = state.model_copy(deep=True)


class JsonStore(StateStore):
    def __init__(self, path: Path, *, autonomous_enabled: bool = True) -> None:
        super().__init__(autonomous_enabled=autonomous_enabled)
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

    async def _write(self, path: Path, state: PatientState) -> None:
        payload = state.model_dump_json(indent=2)
        temp = path.with_suffix(path.suffix + ".tmp")
        await asyncio.to_thread(temp.write_text, payload, "utf-8")
        await asyncio.to_thread(temp.replace, path)

    async def save(self, state: PatientState) -> None:
        async with self._lock:
            path = self._patient_path()
            patient_id = current_patient_id()
            state.profile.id = patient_id
            self._reconcile_if_enabled(state)
            state.updated_at = utc_now()
            path.parent.mkdir(parents=True, exist_ok=True)
            await self._write(path, state)
            if await _flush_post_commit_intents(state):
                state.updated_at = utc_now()
                await self._write(path, state)


class FirestoreStore(StateStore):
    """Patient-scoped Firestore adapter selected from the authenticated principal."""

    def __init__(self, project: str | None = None, *, autonomous_enabled: bool = True) -> None:
        super().__init__(autonomous_enabled=autonomous_enabled)
        from google.cloud import firestore

        self.client = firestore.AsyncClient(project=project)

    def _ref(self):
        patient_id = current_patient_id()
        return self.client.collection(PATIENT_STATE_COLLECTION).document(patient_id)

    async def load(self) -> PatientState:
        patient_id = current_patient_id()
        snapshot = await self._ref().get()
        if not snapshot.exists:
            return PatientState()
        state = PatientState.model_validate(snapshot.to_dict())
        if state.profile.id != patient_id:
            raise ValueError("Firestore patient identity does not match authenticated principal")
        return state

    async def save(self, state: PatientState) -> None:
        patient_id = current_patient_id()
        state.profile.id = patient_id
        self._reconcile_if_enabled(state)
        state.updated_at = utc_now()
        await self._ref().set(state.model_dump(mode="json"))
        if await _flush_post_commit_intents(state):
            state.updated_at = utc_now()
            await self._ref().set(state.model_dump(mode="json"))
