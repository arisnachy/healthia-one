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


class PatientProfile(BaseModel):
    id: str = "patient_demo"
    display_name: str = "Ana Martínez"
    birth_date: date = date(1982, 2, 20)
    locale: str = "es-DO"
    timezone: str = "America/Santo_Domingo"
    allergies: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=lambda: ["Losartán 50 mg cada 24 horas"])
    confirmed_conditions: list[str] = Field(default_factory=lambda: ["Hipertensión arterial"])
    care_plan: CarePlan = Field(default_factory=CarePlan)
    consented_signal_types: list[str] = Field(
        default_factory=lambda: [
            "vitals",
            "weight",
            "activity",
            "results",
            "missions",
            "family_history",
            "documents",
        ]
    )


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
    source: SourceRef = Field(
        default_factory=lambda: SourceRef(source_type="patient_report", source_id="family_form")
    )


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
    source: SourceRef = Field(
        default_factory=lambda: SourceRef(source_type="patient_upload", source_id="documents")
    )


class VitalRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("vital"))
    patient_id: str = "patient_demo"
    measured_at: datetime = Field(default_factory=utc_now)
    systolic: int | None = None
    diastolic: int | None = None
    pulse: int | None = None
    oxygen_saturation: float | None = None
    temperature_c: float | None = None
    symptoms: list[str] = Field(default_factory=list)
    source: SourceRef = Field(
        default_factory=lambda: SourceRef(source_type="patient_entry", source_id="web")
    )

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
    source: SourceRef = Field(
        default_factory=lambda: SourceRef(source_type="patient_entry", source_id="web")
    )

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
    steps: int = 0
    active_minutes: int = 0
    note: str = ""


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
    source: SourceRef = Field(
        default_factory=lambda: SourceRef(source_type="patient_upload", source_id="web")
    )


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
    vitals: list[VitalRecord] = Field(default_factory=list)
    weights: list[WeightRecord] = Field(default_factory=list)
    activity: list[ActivityRecord] = Field(default_factory=list)
    results: list[HealthResult] = Field(default_factory=list)
    family_members: list[FamilyMember] = Field(default_factory=list)
    documents: list[ClinicalDocument] = Field(default_factory=list)
    missions: list[HealthMission] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    emitted_rule_keys: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


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
