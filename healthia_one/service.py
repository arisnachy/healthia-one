from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator, Callable

from healthia_one.config import Settings
from healthia_one.continuity import evaluate_continuity
from healthia_one.devices import ingest_health_connect_batch
from healthia_one.gemini import GeminiResponder
from healthia_one.control import audit, finding_allowed, snooze_consent, sync_consent_to_profile
from healthia_one.models import (
    ActivityRecord,
    Appointment,
    ChatMessage,
    ClinicalDocument,
    FamilyCondition,
    FamilyMember,
    HealthConnectSyncBatch,
    HealthGoal,
    HealthResult,
    MedicationCheckIn,
    MedicationPlan,
    PatientConsent,
    PatientProfile,
    PatientState,
    VitalRecord,
    WeightRecord,
)
from healthia_one.orchestrator import respond
from healthia_one.patient_control import maybe_control_response
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
    state.vitals = [VitalRecord(measured_at=now - timedelta(days=5), systolic=148, diastolic=92, pulse=78)]
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
    state.profile.personal_history.chronic_conditions = ["Hipertensión arterial"]
    state.profile.lifestyle.smoking_status = "never"
    state.profile.lifestyle.alcohol_status = "unknown"
    medication = MedicationPlan(
        original_text="Losartán 50 mg por vía oral cada 24 horas",
        name="Losartán",
        generic_name="losartán",
        strength="50 mg",
        dose_value=50,
        dose_unit="mg",
        dosage_form="tableta",
        route="oral",
        schedule="cada 24 horas",
        frequency_times_per_day=1,
        purpose="Control de presión arterial",
        instructions="Seguir únicamente el esquema indicado por el profesional.",
        prescribed_by="Profesional tratante (dato sintético)",
        verification_status="professional_confirmed",
    )
    state.medication_plans = [medication]
    state.medication_checkins = [
        MedicationCheckIn(medication_id=medication.id, recorded_at=now - timedelta(days=2), status="taken"),
        MedicationCheckIn(medication_id=medication.id, recorded_at=now - timedelta(days=1), status="taken"),
    ]
    state.appointments = [
        Appointment(
            title="Consulta de medicina familiar",
            specialty="Medicina familiar",
            scheduled_at=now + timedelta(hours=40),
            location="Centro de salud sintético",
            required_documents=["Resultados recientes", "Lista de medicamentos"],
            questions=["¿Qué objetivo de presión debo seguir?"],
        )
    ]
    state.goals = [
        HealthGoal(
            title="Completar serie de presión",
            metric="mediciones válidas",
            target="2 mediciones por sesión durante 3 días",
            review_at=now + timedelta(days=4),
        )
    ]
    state.messages = [
        ChatMessage(
            role="assistant",
            author="HealthIA",
            content="Hola, Ana. Ya revisé tus datos recientes. ¿Qué te gustaría revisar hoy?",
        )
    ]
    audit(
        state,
        actor="system",
        action="initialize_synthetic_patient",
        resource_type="patient_state",
        resource_id=state.profile.id,
        details={"synthetic": True},
    )
    return state


SORT_KEYS: dict[str, Callable] = {
    "vitals": lambda item: item.measured_at,
    "weights": lambda item: item.measured_at,
    "activity": lambda item: item.measured_at,
    "results": lambda item: item.uploaded_at,
    "documents": lambda item: item.uploaded_at,
    "medication_checkins": lambda item: item.recorded_at,
    "appointments": lambda item: item.scheduled_at,
    "missions": lambda item: item.updated_at,
    "device_observations": lambda item: item.observed_at,
}


class HealthIAService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = self._build_store()
        self.broker = EventBroker()
        self.gemini = GeminiResponder(settings)
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

    async def reset_demo(self) -> PatientState:
        async with self._mutation_lock:
            state = seed_state()
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "reset"})
        return state

    async def update_profile(self, profile: PatientProfile) -> PatientProfile:
        async with self._mutation_lock:
            state = await self.store.load()
            state.profile = profile
            audit(
                state,
                actor="patient",
                action="update_patient_profile",
                resource_type="patient_profile",
                resource_id=profile.id,
            )
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "profile"})
        return profile

    async def ingest_health_connect(self, batch: HealthConnectSyncBatch) -> dict:
        async with self._mutation_lock:
            state = await self.store.load()
            result = ingest_health_connect_batch(state, batch)
            audit(
                state,
                actor="android_health_connect",
                action="sync_device_batch",
                resource_type="device_connection",
                resource_id=batch.device_id,
                details={
                    "accepted": result["accepted"],
                    "duplicates": result["duplicates"],
                    "background_read": batch.background_read,
                },
            )
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "devices"})
        return result

    async def add_patient_message(self, content: str):
        async with self._mutation_lock:
            state = await self.store.load()
            patient_message = ChatMessage(role="patient", author=state.profile.display_name, content=content)
            state.messages.append(patient_message)
            audit(state, actor="patient", action="send_chat_message", resource_type="chat_message", resource_id=patient_message.id)
            controlled_response = maybe_control_response(state, content)
            response = controlled_response or respond(state, content)
            if controlled_response is None:
                response = await self.gemini.enhance(state, content, response)
            state.messages.append(response.message)
            audit(
                state,
                actor="healthia",
                action="respond_and_route",
                resource_type="chat_message",
                resource_id=response.message.id,
                details={"mission_id": response.message.mission_id or "", "action_target": response.message.metadata.get("action_target")},
            )
            await self.store.save(state)
        await self.broker.publish({"type": "message", "message": response.message.model_dump(mode="json")})
        await self.broker.publish({"type": "state", "section": "chat"})
        return response

    async def _append_and_publish(self, collection: str, item, section: str, *, actor: str = "patient", action: str = "create"):
        async with self._mutation_lock:
            state = await self.store.load()
            values = getattr(state, collection)
            values.append(item)
            sort_key = SORT_KEYS.get(collection)
            if sort_key:
                values.sort(key=sort_key)
            audit(state, actor=actor, action=action, resource_type=section, resource_id=getattr(item, "id", ""))
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": section})
        return item

    async def add_vital(self, vital: VitalRecord) -> VitalRecord:
        return await self._append_and_publish("vitals", vital, "vitals", action="record_vital")

    async def add_weight(self, weight: WeightRecord) -> WeightRecord:
        return await self._append_and_publish("weights", weight, "weight", action="record_weight")

    async def add_activity(self, activity: ActivityRecord) -> ActivityRecord:
        return await self._append_and_publish("activity", activity, "activity", action="record_activity")

    async def add_family_member(self, member: FamilyMember) -> FamilyMember:
        return await self._append_and_publish("family_members", member, "family", action="add_family_member")

    async def add_document(self, document: ClinicalDocument) -> ClinicalDocument:
        return await self._append_and_publish("documents", document, "documents", action="upload_document")

    async def add_result_evidence(self, result: HealthResult, document: ClinicalDocument) -> HealthResult:
        """Persist the structured result and its original evidence link in one state commit."""
        async with self._mutation_lock:
            state = await self.store.load()
            state.documents.append(document)
            state.documents.sort(key=SORT_KEYS["documents"])
            state.results.append(result)
            state.results.sort(key=SORT_KEYS["results"])
            audit(
                state,
                actor="patient",
                action="upload_result_evidence",
                resource_type="results",
                resource_id=result.id,
                details={"document_id": document.id, "evidence_status": document.status},
            )
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "results"})
        return result

    async def get_document(self, document_id: str) -> ClinicalDocument | None:
        state = await self.store.load()
        return next((item for item in state.documents if item.id == document_id), None)

    async def add_medication_plan(self, plan: MedicationPlan) -> MedicationPlan:
        async with self._mutation_lock:
            state = await self.store.load()
            state.medication_plans.append(plan)
            label = " ".join(part for part in [plan.name, plan.strength, plan.schedule] if part).strip()
            if label and label not in state.profile.medications:
                state.profile.medications.append(label)
            audit(state, actor="patient", action="add_medication_plan", resource_type="medications", resource_id=plan.id)
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "medications"})
        return plan

    async def add_medication_checkin(self, checkin: MedicationCheckIn) -> MedicationCheckIn:
        state = await self.store.load()
        if not any(item.id == checkin.medication_id for item in state.medication_plans):
            raise ValueError("Medication plan not found")
        return await self._append_and_publish("medication_checkins", checkin, "medications", action="record_medication_checkin")

    async def add_appointment(self, appointment: Appointment) -> Appointment:
        return await self._append_and_publish("appointments", appointment, "appointments", action="add_appointment")

    async def add_goal(self, goal: HealthGoal) -> HealthGoal:
        return await self._append_and_publish("goals", goal, "goals", action="add_health_goal")

    async def update_consent(self, consent: PatientConsent) -> PatientConsent:
        async with self._mutation_lock:
            state = await self.store.load()
            previous = state.consent.model_dump(mode="json")
            state.consent = consent
            sync_consent_to_profile(state)
            audit(
                state,
                actor="patient",
                action="update_consent",
                resource_type="consent",
                resource_id=state.profile.id,
                details={"previous_signal_types": previous.get("signal_types", []), "signal_types": state.consent.signal_types},
            )
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "consent"})
        return consent

    async def snooze(self, hours: int) -> datetime:
        async with self._mutation_lock:
            state = await self.store.load()
            until = snooze_consent(state, hours)
            audit(
                state,
                actor="patient",
                action="snooze_proactive_interventions",
                resource_type="consent",
                resource_id=state.profile.id,
                details={"hours": hours, "until": until.isoformat()},
            )
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "consent"})
        return until

    async def mute_rule(self, prefix: str) -> PatientConsent:
        async with self._mutation_lock:
            state = await self.store.load()
            if prefix not in state.consent.muted_rule_prefixes:
                state.consent.muted_rule_prefixes.append(prefix)
            state.consent.updated_at = datetime.now(timezone.utc)
            audit(
                state,
                actor="patient",
                action="mute_rule_prefix",
                resource_type="consent",
                resource_id=state.profile.id,
                details={"prefix": prefix},
            )
            await self.store.save(state)
        await self.broker.publish({"type": "state", "section": "consent"})
        return state.consent

    async def run_proactive_check(self, *, manual_requested: bool = False) -> list[ChatMessage]:
        """Run continuity rules only after an explicit event/manual request; never on a timer."""
        created: list[ChatMessage] = []
        async with self._mutation_lock:
            state = await self.store.load()
            findings = evaluate_state(state)
            findings.extend(evaluate_continuity(state))
            for finding in findings:
                if finding.key in state.emitted_rule_keys:
                    continue
                allowed, reason = finding_allowed(state, finding, manual_requested=manual_requested)
                if not allowed:
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
                    author="HealthIA",
                    content=content,
                    risk_level=finding.risk_level,
                    agent_plan=finding.agent_plan,
                    metadata={"proactive": True, "rule_key": finding.key, "evidence_ids": finding.evidence_ids, "consent_reason": reason},
                )
                state.messages.append(message)
                audit(
                    state,
                    actor="healthia",
                    action="emit_event_driven_intervention",
                    resource_type="chat_message",
                    resource_id=message.id,
                    details={
                        "rule_key": finding.key,
                        "risk_level": str(finding.risk_level),
                        "consent_reason": reason,
                        "manual_requested": manual_requested,
                    },
                )
                created.append(message)
            await self.store.save(state)
        for message in created:
            await self.broker.publish({"type": "message", "message": message.model_dump(mode="json")})
        return created
