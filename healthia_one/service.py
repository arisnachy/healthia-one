from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

from healthia_one.config import Settings
from healthia_one.models import (
    ActivityRecord,
    ChatMessage,
    ClinicalDocument,
    FamilyCondition,
    FamilyMember,
    PatientState,
    VitalRecord,
    WeightRecord,
)
from healthia_one.orchestrator import respond
from healthia_one.proactive import evaluate_state
from healthia_one.store import FirestoreStore, JsonStore, MemoryStore, StateStore


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()

    async def publish(self, payload: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                self._subscribers.discard(queue)

    async def subscribe(self) -> AsyncIterator[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


def seed_state() -> PatientState:
    now = datetime.now(timezone.utc)
    state = PatientState()
    state.weights = [
        WeightRecord(measured_at=now - timedelta(days=12), weight_kg=78.0),
        WeightRecord(measured_at=now - timedelta(days=3), weight_kg=80.4, note="Misma balanza"),
    ]
    state.vitals = [
        VitalRecord(measured_at=now - timedelta(days=5), systolic=148, diastolic=92, pulse=78),
    ]
    state.activity = [
        ActivityRecord(measured_at=now - timedelta(days=3), steps=2400, active_minutes=12),
        ActivityRecord(measured_at=now - timedelta(days=2), steps=1800, active_minutes=8),
        ActivityRecord(measured_at=now - timedelta(days=1), steps=2100, active_minutes=10),
    ]
    state.family_members = [
        FamilyMember(
            display_name="Madre",
            relation="madre",
            generation=-1,
            lineage="maternal",
            sex_at_birth="female",
            conditions=[FamilyCondition(name="Diabetes", age_at_diagnosis=52, confirmed=True)],
        ),
        FamilyMember(
            display_name="Padre",
            relation="padre",
            generation=-1,
            lineage="paternal",
            sex_at_birth="male",
            conditions=[FamilyCondition(name="Hipertensión arterial", age_at_diagnosis=44, confirmed=True)],
        ),
        FamilyMember(
            display_name="Abuela materna",
            relation="abuela materna",
            generation=-2,
            lineage="maternal",
            sex_at_birth="female",
            conditions=[FamilyCondition(name="Diabetes", age_at_diagnosis=48, confirmed=False)],
        ),
        FamilyMember(
            display_name="Hermano",
            relation="hermano",
            generation=0,
            lineage="both",
            sex_at_birth="male",
            conditions=[FamilyCondition(name="Hipertensión arterial", age_at_diagnosis=39, confirmed=True)],
        ),
    ]
    state.messages = [
        ChatMessage(
            role="assistant",
            author="KIRA Health",
            content=(
                "Hola, Ana. Mantengo tus mediciones, documentos, historia familiar y misiones de salud "
                "en una sola conversación. Solo vigilo las señales que autorizaste y te explicaré por qué intervengo."
            ),
        )
    ]
    return state


class HealthIAService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = self._build_store()
        self.broker = EventBroker()
        self._mutation_lock = asyncio.Lock()

    def _build_store(self) -> StateStore:
        if self.settings.store_backend == "memory":
            return MemoryStore(seed_state())
        if self.settings.store_backend == "firestore":
            import os
            return FirestoreStore(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
        return JsonStore(Path(self.settings.data_path))

    async def initialize(self) -> None:
        state = await self.store.load()
        if not state.messages and not state.vitals and not state.weights:
            await self.store.save(seed_state())

    async def snapshot(self) -> PatientState:
        return await self.store.load()

    async def add_patient_message(self, content: str):
        async with self._mutation_lock:
            state = await self.store.load()
            patient_message = ChatMessage(role="patient", author=state.profile.display_name, content=content)
            state.messages.append(patient_message)
            response = respond(state, content)
            state.messages.append(response.message)
            await self.store.save(state)
        await self.broker.publish({"type": "message", "message": response.message.model_dump(mode="json")})
        return response

    async def add_vital(self, vital: VitalRecord) -> VitalRecord:
        async with self._mutation_lock:
            state = await self.store.load()
            state.vitals.append(vital)
            state.vitals.sort(key=lambda item: item.measured_at)
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "vitals"})
        return vital

    async def add_weight(self, weight: WeightRecord) -> WeightRecord:
        async with self._mutation_lock:
            state = await self.store.load()
            state.weights.append(weight)
            state.weights.sort(key=lambda item: item.measured_at)
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "weight"})
        return weight

    async def add_activity(self, activity: ActivityRecord) -> ActivityRecord:
        async with self._mutation_lock:
            state = await self.store.load()
            state.activity.append(activity)
            state.activity.sort(key=lambda item: item.measured_at)
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "activity"})
        return activity

    async def add_family_member(self, member: FamilyMember) -> FamilyMember:
        async with self._mutation_lock:
            state = await self.store.load()
            state.family_members.append(member)
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "family"})
        return member

    async def add_document(self, document: ClinicalDocument) -> ClinicalDocument:
        async with self._mutation_lock:
            state = await self.store.load()
            state.documents.append(document)
            state.documents.sort(key=lambda item: item.uploaded_at)
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "documents"})
        return document

    async def get_document(self, document_id: str) -> ClinicalDocument | None:
        state = await self.store.load()
        return next((item for item in state.documents if item.id == document_id), None)

    async def run_proactive_check(self) -> list[ChatMessage]:
        created: list[ChatMessage] = []
        async with self._mutation_lock:
            state = await self.store.load()
            findings = evaluate_state(state)
            for finding in findings:
                if finding.key in state.emitted_rule_keys:
                    continue
                state.emitted_rule_keys.append(finding.key)
                content = (
                    f"### {finding.title}\n\n"
                    f"**Qué detecté:** {finding.summary}\n\n"
                    f"**Por qué importa:** {finding.why_it_matters}\n\n"
                    f"**Qué te propongo ahora:** {finding.next_action}"
                )
                message = ChatMessage(
                    role="assistant",
                    author="KIRA Health",
                    content=content,
                    risk_level=finding.risk_level,
                    agent_plan=finding.agent_plan,
                    metadata={"proactive": True, "rule_key": finding.key, "evidence_ids": finding.evidence_ids},
                )
                state.messages.append(message)
                created.append(message)
            await self.store.save(state)
        for message in created:
            await self.broker.publish({"type": "message", "message": message.model_dump(mode="json")})
        return created

    async def background_loop(self, stop: asyncio.Event) -> None:
        interval = max(self.settings.proactive_interval_seconds, 5)
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                break
            except TimeoutError:
                pass
            try:
                await self.run_proactive_check()
            except Exception as exc:  # pragma: no cover - runtime protection
                await self.broker.publish({"type": "runtime_error", "message": str(exc)[:300]})
