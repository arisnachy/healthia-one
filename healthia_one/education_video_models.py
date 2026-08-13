from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from healthia_one.models import PatientState


VIDEO_REQUEST_PATTERNS = (
    r"\b(?:crea|creame|hazme|genera|preparame)\b.{0,28}\bvideo\b",
    r"\b(?:quiero|necesito)\b.{0,20}\bvideo\b",
    r"\b(?:explica|explicame)\b.{0,40}\ben video\b",
    r"\b(?:create|make|generate|prepare)\b.{0,28}\bvideo\b",
    r"\b(?:explain|teach me)\b.{0,40}\bin (?:a )?video\b",
)
EXPLANATION_PATTERNS = (
    r"\bexplicame\b",
    r"\bque significa\b",
    r"\bque es\b",
    r"\bno entiendo\b",
    r"\bayudame a entender\b",
    r"\bexplain\b",
    r"\bwhat does\b.{0,30}\bmean\b",
    r"\bwhat is\b",
    r"\bi don'?t understand\b",
)
ACCEPT_PATTERNS = (
    r"^(?:si|dale|hazlo|crealo|preparalo|por favor|claro|ok|okay)$",
    r"^(?:yes|yeah|sure|do it|make it|create it|please|go ahead)$",
)
REJECT_PATTERNS = (r"^(?:no|ahora no|no gracias|despues|later|not now|no thanks)$",)
GENERIC_REFERENCE = {
    "eso", "esto", "esa", "ese", "lo anterior", "that", "this", "it", "that result", "the result",
}
MEDICATION_CHANGE_PATTERNS = (
    r"\b(?:suspende|suspender|deja de tomar|aumenta|aumentar|reduce|reducir|duplica|duplicar)\b",
    r"\b(?:stop taking|increase|decrease|double|change your dose)\b",
)


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip()


def is_english(value: str) -> bool:
    text = f" {normalize(value)} "
    signals = (" explain ", " video ", " what ", " my ", " please ", " make ", " create ", " yes ")
    return sum(signal in text for signal in signals) >= 2


def is_video_request(value: str) -> bool:
    text = normalize(value)
    return any(re.search(pattern, text) for pattern in VIDEO_REQUEST_PATTERNS)


def is_explanation_request(value: str) -> bool:
    text = normalize(value)
    return any(re.search(pattern, text) for pattern in EXPLANATION_PATTERNS)


def is_acceptance(value: str) -> bool:
    text = re.sub(r"[.!?]+$", "", normalize(value)).strip()
    return any(re.fullmatch(pattern, text) for pattern in ACCEPT_PATTERNS)


def is_rejection(value: str) -> bool:
    text = re.sub(r"[.!?]+$", "", normalize(value)).strip()
    return any(re.fullmatch(pattern, text) for pattern in REJECT_PATTERNS)


def requested_duration_seconds(value: str, default: int = 90) -> int:
    text = normalize(value)
    match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:min|minuto|minutos|minute|minutes)\b", text)
    if match:
        minutes = float(match.group(1).replace(",", "."))
        return min(max(int(minutes * 60), 45), 300)
    if any(token in text for token in ("rapido", "corto", "quick", "short")):
        return 60
    if any(token in text for token in ("profundo", "profundidad", "detallado", "in depth", "deep")):
        return 300
    if any(token in text for token in ("completo", "complete")):
        return 180
    return min(max(int(default), 45), 300)


def _clean_topic(raw: str) -> str:
    text = str(raw or "").strip(" \t\n\r.,;:!?")
    text = re.sub(
        r"(?i)\b(?:por favor|please|un video|a video|en video|in a video|explicando|que explique|sobre|acerca de|about|para entender|to explain)\b",
        " ", text,
    )
    text = re.sub(
        r"(?i)\b(?:crea|creame|hazme|genera|preparame|quiero|necesito|create|make|generate|prepare|i want|i need|explicame|explain)\b",
        " ", text,
    )
    return re.sub(r"\s+", " ", text).strip(" -")[:180]


def topic_from_text(value: str) -> str:
    text = str(value or "").strip()
    patterns = (
        r"(?i)\b(?:sobre|acerca de|about)\s+(.+)$",
        r"(?i)\b(?:mi|my)\s+([a-zA-Z0-9áéíóúñÁÉÍÓÚÑ][^,.!?]{2,120})$",
        r"(?i)\b(?:explicame|explícame|explain)\s+(.+?)(?:\s+en video|\s+in a video|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            topic = _clean_topic(match.group(1))
            if topic and normalize(topic) not in GENERIC_REFERENCE:
                return topic
    topic = _clean_topic(text)
    return "" if normalize(topic) in GENERIC_REFERENCE else topic


def latest_offer(state: PatientState) -> dict | None:
    for message in reversed(state.messages[-8:]):
        if message.role != "assistant":
            continue
        offer = (message.metadata or {}).get("education_video_offer")
        if isinstance(offer, dict) and offer.get("topic"):
            return dict(offer)
    return None


class EducationFact(BaseModel):
    key: str
    label: str
    value: str
    source_id: str
    source_type: str
    certainty: Literal["confirmed", "recorded", "patient_reported"] = "recorded"


class EducationScene(BaseModel):
    heading: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=2, max_length=600)
    narration: str = Field(min_length=2, max_length=1200)
    visual_kind: Literal["card", "veo"] = "card"
    veo_prompt: str = Field(default="", max_length=1200)


class EducationVideoPlan(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    summary: str = Field(default="", max_length=400)
    patient_fact_keys: list[str] = Field(default_factory=list)
    scenes: list[EducationScene] = Field(min_length=3, max_length=8)


class NarrationAudio(BaseModel):
    data: bytes
    suffix: str = ".mp3"
    mime_type: str = "audio/mpeg"


def collect_topic_facts(state: PatientState, topic: str) -> list[EducationFact]:
    """Select only topic-relevant facts; never dump the whole patient chart."""
    normalized = normalize(topic)
    terms = {item for item in re.split(r"[^a-z0-9]+", normalized) if len(item) > 2}
    facts: list[EducationFact] = []

    def related(value: str) -> bool:
        candidate = normalize(value)
        if not terms:
            return False
        candidate_terms = {item for item in re.split(r"[^a-z0-9]+", candidate) if len(item) > 2}
        return bool(terms & candidate_terms) or any(term in candidate for term in terms)

    for index, condition in enumerate(state.profile.confirmed_conditions):
        if related(condition):
            facts.append(EducationFact(
                key=f"condition_{index}", label="Diagnóstico confirmado en el expediente", value=condition,
                source_id=f"profile:confirmed_condition:{index}", source_type="patient_profile", certainty="confirmed",
            ))

    bp_topic = any(term in normalized for term in ("hipertension", "presion", "tension", "blood pressure", "hypertension"))
    if bp_topic and state.vitals:
        vital = max(state.vitals, key=lambda item: item.measured_at)
        if vital.systolic and vital.diastolic:
            facts.append(EducationFact(
                key="latest_blood_pressure", label="Última presión registrada",
                value=f"{vital.systolic}/{vital.diastolic} mmHg", source_id=vital.id,
                source_type="vital_record", certainty="recorded",
            ))

    for medication in state.medication_plans:
        if not medication.active or medication.verification_status != "professional_confirmed":
            continue
        relevant = related(medication.purpose) or related(medication.name)
        if bp_topic and any(term in normalize(medication.purpose) for term in ("presion", "hipertension", "blood pressure")):
            relevant = True
        if relevant:
            value = " ".join(part for part in (medication.name, medication.strength, medication.schedule) if str(part or "").strip()).strip()
            if value:
                facts.append(EducationFact(
                    key=f"medication_{medication.id}", label="Tratamiento registrado", value=value,
                    source_id=medication.id, source_type="medication_plan", certainty="confirmed",
                ))

    for result in reversed(state.results[-12:]):
        matching = [item for item in result.items if related(item.name) or related(result.panel)]
        if not matching:
            continue
        for item in matching[:3]:
            facts.append(EducationFact(
                key=f"result_{result.id}_{normalize(item.name).replace(' ', '_')[:30]}",
                label=f"{result.panel}: {item.name}", value=f"{item.value} {item.unit}".strip(),
                source_id=result.id, source_type="health_result", certainty="recorded",
            ))
        break
    return facts[:5]


def validate_plan(plan: EducationVideoPlan, facts: list[EducationFact], patient_name: str) -> EducationVideoPlan:
    allowed = {item.key for item in facts}
    if any(key not in allowed for key in plan.patient_fact_keys):
        raise ValueError("Education plan referenced a patient fact outside the authorized evidence set")
    private_tokens = {normalize(patient_name)} if patient_name else set()
    private_tokens.update(normalize(item.value) for item in facts if item.value)
    veo_count = 0
    for scene in plan.scenes:
        combined = normalize(f"{scene.heading} {scene.body} {scene.narration}")
        if any(re.search(pattern, combined) for pattern in MEDICATION_CHANGE_PATTERNS):
            raise ValueError("Education plan crossed the medication-change safety boundary")
        if scene.visual_kind == "veo":
            veo_count += 1
            prompt = normalize(scene.veo_prompt)
            if not prompt:
                raise ValueError("Veo scene requires a generic prompt")
            if any(token and token in prompt for token in private_tokens):
                raise ValueError("Patient-specific information must never be sent to Veo")
            if re.search(r"\b\d+(?:[./-]\d+)*\b", prompt):
                raise ValueError("Exact numbers are not allowed in Veo education prompts")
    if veo_count > 1:
        raise ValueError("HealthIA Explain allows at most one Veo scene per video")
    return plan


def compose_narration(plan: EducationVideoPlan, facts: list[EducationFact], locale: str) -> str:
    selected = {item.key: item for item in facts if item.key in plan.patient_fact_keys}
    parts: list[str] = []
    if selected:
        rendered = "; ".join(f"{fact.label}: {fact.value}" for fact in selected.values())
        parts.append(f"Primero, tu información registrada. {rendered}." if locale == "es" else f"First, your recorded information. {rendered}.")
    parts.extend(scene.narration.strip() for scene in plan.scenes)
    ending = (
        "Esta explicación es educativa y no cambia tu tratamiento ni sustituye la valoración de un profesional."
        if locale == "es" else
        "This explanation is educational and does not change your treatment or replace professional care."
    )
    parts.append(ending)
    text = " ".join(part for part in parts if part).strip()
    if len(text) > 4800:
        text = text[:4700].rsplit(".", 1)[0].strip() + ". " + ending
    return text
