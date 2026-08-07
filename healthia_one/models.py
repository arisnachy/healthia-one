from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


DEFAULT_SIGNAL_TYPES = [
    "vitals",
    "weight",
    "activity",
    "results",
    "missions",
    "family_history",
    "documents",
    "medications",
    "appointments",
    "device_data",
    "reproductive_health",
]


class RiskLevel(StrEnum):
    INFO = "info"
    WATCH = "watch"
    PRIORITY = "priority"
    URGENT = "urgent"


class MissionStatus(StrEnum):
    ACTIVE = "active"
    WAITING_PATIENT = "waiting_patient"
    WAITING_PROFESSIONAL = "waiting_professional"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DocumentCategory(StrEnum):
    LABORATORY = "laboratory"
    IMAGING = "imaging"
    PRESCRIPTION = "prescription"
    CONSULTATION = "consultation"
    DISCHARGE = "discharge"
    VACCINE = "vaccine"
    INSURANCE = "insurance"
    IDENTITY = "identity"
    OTHER = "other"


class SourceRef(BaseModel):
    source_type: str
    source_id: str
    captured_at: datetime = Field(default_factory=utc_now)
    verified: bool = False


class CarePlan(BaseModel):
    conditions: list[str] = Field(default_factory=lambda: ["hypertension", "weight_management"])
    weight_due_days: int = 7
    blood_pressure_due_days: int = 3
    activity_goal_steps: int = 6000
    weight_change_watch_kg: float = 2.0


class LifestyleHistory(BaseModel):
    smoking_status: Literal["never", "former", "current", "unknown"] = "unknown"
    cigarettes_per_day: float | None = Field(default=None, ge=0, le=200)
    pack_years: float | None = Field(default=None, ge=0, le=500)
    alcohol_status: Literal["never", "former", "current", "unknown"] = "unknown"
    alcohol_notes: str = Field(default="", max_length=500)
    drug_use_status: Literal["never", "former", "current", "unknown"] = "unknown"
    drug_use_notes: str = Field(default="", max_length=500)
    coffee_cups_per_day: float | None = Field(default=None, ge=0, le=30)
    tea_cups_per_day: float | None = Field(default=None, ge=0, le=30)
    physical_activity_notes: str = Field(default="", max_length=500)
    nutrition_notes: str = Field(default="", max_length=500)


class PersonalHistory(BaseModel):
    chronic_conditions: list[str] = Field(default_factory=list)
    transfusion_history: list[str] = Field(default_factory=list)
    traumatic_history: list[str] = Field(default_factory=list)
    surgical_history: list[str] = Field(default_factory=list)
    hospitalizations: list[str] = Field(default_factory=list)
    non_pathological_history: list[str] = Field(default_factory=list)
    immunizations: list[str] = Field(default_factory=list)


class ReproductiveHealth(BaseModel):
    applicable: bool = False
    menarche_age: int | None = Field(default=None, ge=7, le=25)
    cycle_length_days: int | None = Field(default=None, ge=15, le=90)
    last_menstrual_period: date | None = None
    menstruation_notes: str = Field(default="", max_length=500)
    menopause: bool = False
    contraception: str = Field(default="", max_length=200)
    pregnancies: int | None = Field(default=None, ge=0, le=30)
    births: int | None = Field(default=None, ge=0, le=30)
    cesareans: int | None = Field(default=None, ge=0, le=30)
    miscarriages_or_losses: int | None = Field(default=None, ge=0, le=30)
    pregnancy_status: Literal["not_pregnant", "pregnant", "postpartum", "unknown"] = "unknown"
    estimated_due_date: date | None = None
    delivery_date: date | None = None
    breastfeeding: bool | None = None
    pregnancy_notes: str = Field(default="", max_length=800)


class EmergencyContact(BaseModel):
    name: str = Field(default="", max_length=160)
    relationship: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=80)


class PatientProfile(BaseModel):
    id: str = "patient_demo"
    display_name: str = "Ana Martínez"
    legal_name: str = ""
    birth_date: date = date(1982, 2, 20)
    sex_at_birth: Literal["female", "male", "intersex", "unknown"] = "female"
    gender_identity: str = ""
    preferred_pronouns: str = ""
    blood_type: str = ""
    height_cm: float | None = Field(default=165.0, ge=50, le=250)
    email: str = ""
    phone: str = ""
    address: str = ""
    occupation: str = ""
    locale: str = "es-DO"
    timezone: str = "America/Santo_Domingo"
    allergies: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=lambda: ["Losartán 50 mg cada 24 horas"])
    confirmed_conditions: list[str] = Field(default_factory=lambda: ["Hipertensión arterial"])
    lifestyle: LifestyleHistory = Field(default_factory=LifestyleHistory)
    personal_history: PersonalHistory = Field(default_factory=PersonalHistory)
    reproductive_health: ReproductiveHealth = Field(default_factory=ReproductiveHealth)
    emergency_contact: EmergencyContact = Field(default_factory=EmergencyContact)
    care_plan: CarePlan = Field(default_factory=CarePlan)
    consented_signal_types: list[str] = Field(default_factory=lambda: list(DEFAULT_SIGNAL_TYPES))


class PatientConsent(BaseModel):
    proactive_enabled: bool = True
    signal_types: list[str] = Field(default_factory=lambda: list(DEFAULT_SIGNAL_TYPES))
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    snoozed_until: datetime | None = None
    muted_rule_prefixes: list[str] = Field(default_factory=list)
    allow_urgent_safety_bypass: bool = True
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def valid_clock(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("quiet hours must use HH:MM")
        hour, minute = map(int, parts)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("quiet hours must use HH:MM")
        return f"{hour:02d}:{minute:02d}"


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("audit"))
    patient_id: str = "patient_demo"
    created_at: datetime = Field(default_factory=utc_now)
    actor: str
    action: str
    resource_type: str
    resource_id: str = ""
    outcome: Literal["success", "blocked", "failed"] = "success"
    details: dict[str, Any] = Field(default_factory=dict)


class FamilyCondition(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    age_at_diagnosis: int | None = Field(default=None, ge=0, le=120)
    confirmed: bool = False
    notes: str = Field(default="", max_length=500)


class FamilyMember(BaseModel):
    id: str = Field(default_factory=lambda: new_id("family"))
    display_name: str = Field(min_length=1, max_length=120)
    relation: str = Field(min_length=2, max_length=80)
    generation: Literal[-2, -1, 0, 1, 2] = 0
    lineage: Literal["maternal", "paternal", "both", "unknown"] = "unknown"
    sex_at_birth: Literal["female", "male", "unknown"] = "unknown"
    biological_relative: bool = True
    alive: bool | None = None
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    death_year: int | None = Field(default=None, ge=1900, le=2100)
    conditions: list[FamilyCondition] = Field(default_factory=list)
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="patient_report", source_id="family_form"))


class ClinicalDocument(BaseModel):
    id: str = Field(default_factory=lambda: new_id("doc"))
    patient_id: str = "patient_demo"
    title: str = Field(min_length=1, max_length=220)
    filename: str
    category: DocumentCategory = DocumentCategory.OTHER
    mime_type: str = "application/octet-stream"
    size_bytes: int = Field(default=0, ge=0)
    uploaded_at: datetime = Field(default_factory=utc_now)
    document_date: date | None = None
    storage_path: str = ""
    status: Literal["stored", "parsed", "pending_review", "invalid"] = "stored"
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    related_result_id: str | None = None
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="patient_upload", source_id="documents"))


class MedicationPlan(BaseModel):
    id: str = Field(default_factory=lambda: new_id("med"))
    patient_id: str = "patient_demo"
    original_text: str = Field(default="", max_length=500)
    name: str = Field(min_length=2, max_length=160)
    generic_name: str = Field(default="", max_length=160)
    strength: str = Field(default="", max_length=80)
    dose_value: float | None = Field(default=None, ge=0)
    dose_unit: str = Field(default="", max_length=30)
    dosage_form: str = Field(default="", max_length=80)
    route: str = Field(default="oral", max_length=60)
    schedule: str = Field(default="", max_length=160)
    frequency_times_per_day: float | None = Field(default=None, ge=0, le=24)
    duration: str = Field(default="", max_length=100)
    purpose: str = Field(default="", max_length=220)
    instructions: str = Field(default="", max_length=500)
    precautions: list[str] = Field(default_factory=list)
    prescribed_by: str = Field(default="", max_length=160)
    verification_status: Literal["unverified", "patient_confirmed", "professional_confirmed"] = "unverified"
    active: bool = True
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="patient_report", source_id="medication_form"))


class MedicationCheckIn(BaseModel):
    id: str = Field(default_factory=lambda: new_id("dose"))
    patient_id: str = "patient_demo"
    medication_id: str
    recorded_at: datetime = Field(default_factory=utc_now)
    status: Literal["taken", "late", "skipped", "unknown"]
    note: str = Field(default="", max_length=500)
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="patient_entry", source_id="medication_checkin"))


class Appointment(BaseModel):
    id: str = Field(default_factory=lambda: new_id("appt"))
    patient_id: str = "patient_demo"
    title: str = Field(min_length=2, max_length=180)
    specialty: str = Field(default="", max_length=120)
    scheduled_at: datetime
    location: str = Field(default="", max_length=220)
    status: Literal["scheduled", "completed", "cancelled"] = "scheduled"
    required_documents: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=800)
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="patient_entry", source_id="appointment_form"))


class HealthGoal(BaseModel):
    id: str = Field(default_factory=lambda: new_id("goal"))
    patient_id: str = "patient_demo"
    title: str = Field(min_length=2, max_length=180)
    metric: str = Field(default="", max_length=100)
    target: str = Field(default="", max_length=120)
    status: Literal["active", "paused", "completed"] = "active"
    review_at: datetime | None = None
    notes: str = Field(default="", max_length=500)


class VitalRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("vital"))
    patient_id: str = "patient_demo"
    measured_at: datetime = Field(default_factory=utc_now)
    systolic: int | None = None
    diastolic: int | None = None
    pulse: int | None = None
    respiratory_rate: float | None = Field(default=None, ge=1, le=100)
    oxygen_saturation: float | None = Field(default=None, ge=1, le=100)
    temperature_c: float | None = Field(default=None, ge=25, le=45)
    blood_glucose_mg_dl: float | None = Field(default=None, ge=1, le=2000)
    cholesterol_mg_dl: float | None = Field(default=None, ge=1, le=1500)
    symptoms: list[str] = Field(default_factory=list)
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="patient_entry", source_id="web"))

    @field_validator("systolic", "diastolic", "pulse")
    @classmethod
    def positive_int(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("measurement must be positive")
        return value


class WeightRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("weight"))
    patient_id: str = "patient_demo"
    measured_at: datetime = Field(default_factory=utc_now)
    weight_kg: float
    note: str = ""
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="patient_entry", source_id="web"))

    @field_validator("weight_kg")
    @classmethod
    def plausible_weight(cls, value: float) -> float:
        if not 20 <= value <= 400:
            raise ValueError("weight is outside the supported range")
        return round(value, 2)


class ActivityRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("activity"))
    patient_id: str = "patient_demo"
    measured_at: datetime = Field(default_factory=utc_now)
    steps: int = Field(default=0, ge=0)
    active_minutes: int = Field(default=0, ge=0)
    note: str = ""
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="patient_entry", source_id="web"))


class DeviceMetric(StrEnum):
    STEPS = "steps"
    HEART_RATE = "heart_rate"
    BLOOD_PRESSURE = "blood_pressure"
    WEIGHT = "weight"
    HEIGHT = "height"
    OXYGEN_SATURATION = "oxygen_saturation"
    RESPIRATORY_RATE = "respiratory_rate"
    BODY_TEMPERATURE = "body_temperature"
    BLOOD_GLUCOSE = "blood_glucose"
    CHOLESTEROL = "cholesterol"
    MENSTRUATION_PERIOD = "menstruation_period"


class DeviceObservation(BaseModel):
    id: str = Field(default_factory=lambda: new_id("device"))
    patient_id: str = "patient_demo"
    external_id: str = Field(min_length=1, max_length=240)
    metric: DeviceMetric
    observed_at: datetime
    value: float
    secondary_value: float | None = None
    unit: str = Field(default="", max_length=40)
    source_package: str = Field(default="", max_length=240)
    source_name: str = Field(default="Health Connect", max_length=160)
    device_manufacturer: str = Field(default="", max_length=120)
    device_model: str = Field(default="", max_length=120)
    device_type: str = Field(default="", max_length=80)
    recording_method: str = Field(default="", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthConnectSyncBatch(BaseModel):
    device_id: str = Field(min_length=1, max_length=200)
    source_package: str = Field(default="", max_length=240)
    synced_at: datetime = Field(default_factory=utc_now)
    background_read: bool = False
    records: list[DeviceObservation] = Field(default_factory=list, max_length=5000)


class DeviceConnection(BaseModel):
    id: str = Field(default_factory=lambda: new_id("connection"))
    provider: Literal["health_connect", "wear_os", "manual", "other"] = "health_connect"
    device_id: str
    display_name: str = "Android Health Connect"
    status: Literal["connected", "paused", "disconnected", "error"] = "connected"
    permissions: list[str] = Field(default_factory=list)
    background_read: bool = False
    last_sync_at: datetime | None = None
    last_error: str = ""


class ResultItem(BaseModel):
    name: str
    value: float | str
    unit: str = ""
    reference: str = ""
    flag: str | None = None


class HealthResult(BaseModel):
    id: str = Field(default_factory=lambda: new_id("result"))
    patient_id: str = "patient_demo"
    uploaded_at: datetime = Field(default_factory=utc_now)
    filename: str
    panel: str = "Resultado cargado"
    items: list[ResultItem] = Field(default_factory=list)
    status: Literal["parsed", "pending_multimodal", "invalid"] = "parsed"
    explained: bool = False
    explanation: str = ""
    source: SourceRef = Field(default_factory=lambda: SourceRef(source_type="patient_upload", source_id="web"))


class AgentStep(BaseModel):
    agent: str
    action: str
    reason: str
    status: Literal["planned", "running", "completed", "blocked"] = "planned"


class HealthMission(BaseModel):
    id: str = Field(default_factory=lambda: new_id("mission"))
    patient_id: str = "patient_demo"
    title: str
    mission_type: str
    status: MissionStatus = MissionStatus.ACTIVE
    risk_level: RiskLevel = RiskLevel.INFO
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    next_action: str
    evidence_ids: list[str] = Field(default_factory=list)
    agent_plan: list[AgentStep] = Field(default_factory=list)
    closure_evidence: list[str] = Field(default_factory=list)


class AgenticEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("event"))
    event_type: Literal["vital_recorded", "device_sync", "scheduled_tick", "manual_demo"]
    patient_id: str = "patient_demo"
    source_id: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class MissionTraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("trace"))
    created_at: datetime = Field(default_factory=utc_now)
    stage: Literal["trigger", "decision", "tool", "persistence", "closure", "error"]
    actor: str
    action: str
    status: Literal["queued", "running", "completed", "blocked", "failed"] = "completed"
    evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class MissionArtifact(BaseModel):
    id: str = Field(default_factory=lambda: new_id("artifact"))
    patient_id: str = "patient_demo"
    mission_id: str
    artifact_type: str
    title: str
    created_at: datetime = Field(default_factory=utc_now)
    source_evidence_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    verified: bool = True


class MissionRun(BaseModel):
    id: str = Field(default_factory=lambda: new_id("run"))
    correlation_id: str = Field(default_factory=lambda: new_id("corr"))
    patient_id: str = "patient_demo"
    mission_id: str | None = None
    trigger_type: str
    runtime: Literal["google_adk", "deterministic_fallback", "deterministic_test"]
    status: Literal["queued", "running", "completed", "blocked", "failed"] = "queued"
    model: str = ""
    provider_requests_reserved: int = 0
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    events: list[MissionTraceEvent] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    public_summary: str = ""
    error: str = ""


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    patient_id: str = "patient_demo"
    role: Literal["patient", "assistant", "system"]
    author: str
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    risk_level: RiskLevel = RiskLevel.INFO
    mission_id: str | None = None
    agent_plan: list[AgentStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatientState(BaseModel):
    profile: PatientProfile = Field(default_factory=PatientProfile)
    consent: PatientConsent = Field(default_factory=PatientConsent)
    vitals: list[VitalRecord] = Field(default_factory=list)
    weights: list[WeightRecord] = Field(default_factory=list)
    activity: list[ActivityRecord] = Field(default_factory=list)
    results: list[HealthResult] = Field(default_factory=list)
    family_members: list[FamilyMember] = Field(default_factory=list)
    documents: list[ClinicalDocument] = Field(default_factory=list)
    medication_plans: list[MedicationPlan] = Field(default_factory=list)
    medication_checkins: list[MedicationCheckIn] = Field(default_factory=list)
    device_observations: list[DeviceObservation] = Field(default_factory=list)
    device_connections: list[DeviceConnection] = Field(default_factory=list)
    synced_external_ids: list[str] = Field(default_factory=list)
    appointments: list[Appointment] = Field(default_factory=list)
    goals: list[HealthGoal] = Field(default_factory=list)
    missions: list[HealthMission] = Field(default_factory=list)
    mission_runs: list[MissionRun] = Field(default_factory=list)
    mission_artifacts: list[MissionArtifact] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    audit_events: list[AuditEvent] = Field(default_factory=list)
    emitted_rule_keys: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


class MedicationNormalizeRequest(BaseModel):
    text: str = Field(min_length=2, max_length=500)


class DevicePairingClaim(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    device_id: str = Field(min_length=3, max_length=200)
    display_name: str = Field(default="Android Health Connect", max_length=160)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    message: ChatMessage
    mission: HealthMission | None = None


class ProactiveFinding(BaseModel):
    key: str
    title: str
    risk_level: RiskLevel
    summary: str
    why_it_matters: str
    next_action: str
    evidence_ids: list[str] = Field(default_factory=list)
    agent_plan: list[AgentStep] = Field(default_factory=list)


class SnoozeRequest(BaseModel):
    hours: int = Field(default=24, ge=1, le=720)


class MuteRuleRequest(BaseModel):
    prefix: str = Field(min_length=1, max_length=120)
