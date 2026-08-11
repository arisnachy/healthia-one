from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from healthia_one.models import ChatMessage, PatientState

ANSWER_PREFIX = "[ENTREVISTA_CLINICA]"

REFERENCE_SIGNALS = (
    "eso", "esa", "ese", "esto", "esta", "este", "aquello", "aquella", "aquel",
    "el de ayer", "la de ayer", "lo de ayer", "el anterior", "la anterior", "lo anterior",
    "el primero", "la primera", "el segundo", "la segunda", "el ultimo", "la ultima",
    "that", "this", "it", "the one from yesterday", "the previous one", "the first one", "the second one",
)
CORRECTION_SIGNALS = (
    "no,", "no me refiero", "me referia", "me refería", "quise decir", "hablaba de",
    "i meant", "no, i mean", "i was talking about", "not that",
)
CONTINUATION_SIGNALS = (
    "y si", "y entonces", "entonces", "pero", "por que", "por qué", "como asi", "cómo así",
    "what about", "and if", "so", "but", "why", "how so",
)

# Canonical current-turn topics. An explicit current noun always outranks a stale
# contextual referent. This is intentionally deterministic: Gemini may explain a
# resolved reference, but it is never allowed to invent which patient object the
# user was referring to.
TOPIC_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("results", ("resultado", "resultados", "result", "results", "laboratorio", "laboratory", "lab", "scan", "imaging", "xray", "x-ray", "ultrasound", "ecg", "ekg")),
    ("treatment", ("medicamento", "medicación", "medicacion", "medication", "medicine", "treatment", "tratamiento", "dosis", "dose")),
    ("measurements", ("presión", "presion", "blood pressure", "peso", "weight", "actividad", "activity", "steps", "medición", "medicion", "measurement")),
    ("appointments", ("cita", "appointment", "specialist", "consulta", "consultation", "medical visit", "visit")),
    ("family", ("familia", "family", "genograma", "genogram", "antecedente familiar")),
    ("documents", ("documento", "documentos", "document", "documents", "expediente", "health record", "archivo", "file")),
    ("devices", ("dispositivo", "dispositivos", "device", "devices", "wearable", "health connect", "reloj", "watch")),
    ("control", ("privacidad", "privacy", "permisos", "permissions", "consent", "consentimiento")),
    ("timeline", ("línea de tiempo", "linea de tiempo", "timeline", "health history", "historia completa")),
)

ACTION_HINTS: dict[str, str] = {
    "results": "resultado estudio laboratorio imagen",
    "measurements": "medicion presion peso actividad",
    "treatment": "tratamiento medicamento dosis",
    "appointments": "cita consulta especialista",
    "timeline": "linea de salud historia cronologia",
    "family": "familia genograma antecedente familiar",
    "documents": "documento archivo expediente informe",
    "devices": "dispositivo reloj health connect",
    "clinical_interview": "consulta sintomas problema actual",
    "control": "privacidad permisos consentimiento",
}

MISSION_HINTS: dict[str, str] = {
    "result_explanation": "resultado estudio laboratorio imagen",
    "blood_pressure": "presion arterial medicion",
    "weight_followup": "peso tendencia",
    "activity_plan": "actividad pasos ejercicio",
    "medication_management": "tratamiento medicamento dosis",
    "consultation_preparation": "cita consulta especialista",
    "timeline_review": "linea de salud historia cronologia",
    "family_history": "familia genograma antecedente familiar",
    "document_management": "documento archivo expediente informe",
    "device_connection": "dispositivo reloj health connect",
    "clinical_interview": "consulta sintomas problema actual",
}

MISSION_TO_TARGET: dict[str, str] = {
    "result_explanation": "results",
    "blood_pressure": "measurements",
    "weight_followup": "measurements",
    "activity_plan": "measurements",
    "medication_management": "treatment",
    "consultation_preparation": "appointments",
    "timeline_review": "timeline",
    "family_history": "family",
    "document_management": "documents",
    "device_connection": "devices",
    "clinical_interview": "clinical_interview",
}


@dataclass(frozen=True)
class ConversationFrame:
    recent_turns: list[dict[str, str]]
    compact_summary: dict[str, Any]
    last_action_target: str | None
    last_mission_type: str | None
    ambiguous_reference: bool
    correction: bool
    current_topic: str | None
    reference_status: str
    resolved_reference: dict[str, Any] | None
    needs_clarification: bool
    routing_text: str

    def as_prompt_payload(self) -> dict[str, Any]:
        return {
            "recent_turns": self.recent_turns,
            "compact_summary": self.compact_summary,
            "last_action_target": self.last_action_target,
            "last_mission_type": self.last_mission_type,
            "ambiguous_reference": self.ambiguous_reference,
            "correction": self.correction,
            "current_topic": self.current_topic,
            "reference_status": self.reference_status,
            "resolved_reference": self.resolved_reference,
            "needs_clarification": self.needs_clarification,
        }


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = _normalize(text)
    needle = _normalize(phrase)
    if not normalized or not needle:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", normalized))


def explicit_topic(text: str) -> str | None:
    """Return the strongest canonical topic explicitly named in the current turn."""
    for target, signals in TOPIC_SIGNALS:
        if any(_contains_phrase(text, signal) for signal in signals):
            return target
    return None


def _public_message_text(message: ChatMessage) -> str:
    text = str(message.content or "").strip()
    if not text or text.startswith(ANSWER_PREFIX):
        return ""
    return text


def selective_memory(state: PatientState, *, max_turns: int = 12, char_budget: int = 6000) -> list[dict[str, str]]:
    """Return a small, patient-visible conversation window without dumping the full record."""
    selected: list[dict[str, str]] = []
    used = 0
    for message in reversed(state.messages):
        if message.role not in {"patient", "assistant"}:
            continue
        if message.metadata.get("proactive") and selected:
            continue
        text = _public_message_text(message)
        if not text:
            continue
        clipped = text[:1400]
        cost = len(clipped)
        if selected and used + cost > char_budget:
            break
        selected.append({"role": message.role, "content": clipped})
        used += cost
        if len(selected) >= max_turns:
            break
    selected.reverse()
    return selected


def _latest_topic_metadata(state: PatientState) -> tuple[str | None, str | None, str | None, str | None]:
    for message in reversed(state.messages):
        if message.role != "assistant":
            continue
        target = str(message.metadata.get("action_target") or "").strip() or None
        mission_type = str(message.metadata.get("mission_type") or "").strip() or None
        mission_id = str(message.mission_id or "").strip() or None
        if not mission_type and mission_id:
            mission = next((item for item in reversed(state.missions) if item.id == mission_id), None)
            mission_type = mission.mission_type if mission else None
        if target or mission_type:
            return target, mission_type, message.id, mission_id
    return None, None, None, None


def _is_ambiguous_followup(text: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    if any(_normalize(signal) in normalized for signal in REFERENCE_SIGNALS):
        return True
    if any(normalized.startswith(_normalize(signal)) for signal in CONTINUATION_SIGNALS):
        return True
    words = re.findall(r"[a-z0-9]+", normalized)
    return len(words) <= 5 and normalized not in {"hola", "hello", "gracias", "thanks", "thank you"}


def _is_correction(text: str) -> bool:
    normalized = _normalize(text)
    return any(_normalize(signal) in normalized for signal in CORRECTION_SIGNALS)


def _compact_summary(state: PatientState) -> dict[str, Any]:
    latest_result = state.results[-1] if state.results else None
    latest_document = state.documents[-1] if state.documents else None
    latest_vital = state.vitals[-1] if state.vitals else None
    latest_weight = state.weights[-1] if state.weights else None
    upcoming_appointment = next((item for item in state.appointments if str(item.status) == "scheduled"), None)
    active_missions = [
        item for item in reversed(state.missions)
        if str(getattr(item.status, "value", item.status)) not in {"completed", "cancelled"}
    ][:3]
    return {
        "latest_result": {"id": latest_result.id, "panel": latest_result.panel, "uploaded_at": latest_result.uploaded_at.isoformat()} if latest_result else None,
        "latest_document": {"id": latest_document.id, "title": latest_document.title, "category": str(getattr(latest_document.category, "value", latest_document.category)), "uploaded_at": latest_document.uploaded_at.isoformat()} if latest_document else None,
        "latest_blood_pressure": {"systolic": latest_vital.systolic, "diastolic": latest_vital.diastolic, "measured_at": latest_vital.measured_at.isoformat()} if latest_vital and latest_vital.systolic and latest_vital.diastolic else None,
        "latest_weight": {"kg": latest_weight.weight_kg, "measured_at": latest_weight.measured_at.isoformat()} if latest_weight else None,
        "upcoming_appointment": {"id": upcoming_appointment.id, "title": upcoming_appointment.title, "scheduled_at": upcoming_appointment.scheduled_at.isoformat()} if upcoming_appointment else None,
        "active_missions": [
            {"id": mission.id, "type": mission.mission_type, "title": mission.title, "next_action": mission.next_action, "status": str(getattr(mission.status, "value", mission.status))}
            for mission in active_missions
        ],
    }


def _resolve_reference(*, patient_text: str, ambiguous: bool, current_topic: str | None, prior_target: str | None, prior_mission_type: str | None, prior_message_id: str | None, prior_mission_id: str | None) -> tuple[str, dict[str, Any] | None, bool]:
    if current_topic:
        return "explicit_current_topic", {"target": current_topic, "mission_type": None, "mission_id": None, "source": "current_message", "evidence_message_id": None, "confidence": 1.0}, False
    if not ambiguous:
        return "none", None, False
    resolved_target = prior_target or MISSION_TO_TARGET.get(prior_mission_type or "")
    if resolved_target or prior_mission_type:
        return "resolved_recent_context", {"target": resolved_target, "mission_type": prior_mission_type, "mission_id": prior_mission_id, "source": "recent_assistant_context", "evidence_message_id": prior_message_id, "confidence": 0.92 if resolved_target else 0.82}, False
    return "needs_clarification", None, True


def build_frame(state: PatientState, patient_text: str) -> ConversationFrame:
    target, mission_type, message_id, mission_id = _latest_topic_metadata(state)
    ambiguous = _is_ambiguous_followup(patient_text)
    correction = _is_correction(patient_text)
    current_topic = explicit_topic(patient_text)
    reference_status, resolved_reference, needs_clarification = _resolve_reference(
        patient_text=patient_text,
        ambiguous=ambiguous,
        current_topic=current_topic,
        prior_target=target,
        prior_mission_type=mission_type,
        prior_message_id=message_id,
        prior_mission_id=mission_id,
    )
    routing_text = patient_text
    if reference_status == "resolved_recent_context" and resolved_reference:
        resolved_target = str(resolved_reference.get("target") or "")
        resolved_mission = str(resolved_reference.get("mission_type") or "")
        hint = ACTION_HINTS.get(resolved_target) or MISSION_HINTS.get(resolved_mission)
        if hint:
            routing_text = f"{patient_text} | CONTEXTUAL_ROUTING_HINT: {hint}"
    return ConversationFrame(
        recent_turns=selective_memory(state),
        compact_summary=_compact_summary(state),
        last_action_target=target,
        last_mission_type=mission_type,
        ambiguous_reference=ambiguous,
        correction=correction,
        current_topic=current_topic,
        reference_status=reference_status,
        resolved_reference=resolved_reference,
        needs_clarification=needs_clarification,
        routing_text=routing_text,
    )


def semantic_packet(state: PatientState, patient_text: str) -> dict[str, Any]:
    frame = build_frame(state, patient_text)
    return {
        "current_message": patient_text,
        "conversation": frame.as_prompt_payload(),
        "instruction": (
            "Use only the evidence-backed resolved_reference and authorized compact summary to resolve pronouns, corrections, ellipsis and ordinals. "
            "The current explicit topic/correction overrides older context. If needs_clarification is true, ask one concise clarifying question instead of guessing. "
            "Never invent a referenced result, document, appointment, mission, device or clinical fact that is absent."
        ),
    }
