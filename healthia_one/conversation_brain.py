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

# Strong current-turn topics. These suppress a stale contextual routing hint even
# if the same sentence also contains a pronoun such as "it"/"eso". The current
# explicit noun wins; prior context is only used when the turn is genuinely
# elliptical.
EXPLICIT_TOPIC_SIGNALS = (
    "resultado", "resultados", "result", "results", "laboratorio", "laboratory", "lab", "scan", "imaging", "xray", "x-ray", "ultrasound", "ecg", "ekg",
    "medicamento", "medicación", "medicacion", "medication", "medicine", "treatment", "tratamiento", "dosis", "dose",
    "presión", "presion", "blood pressure", "peso", "weight", "actividad", "activity", "steps",
    "cita", "appointment", "specialist", "consulta",
    "familia", "family", "genograma", "genogram",
    "documento", "documentos", "document", "documents", "expediente", "health record",
    "dispositivo", "dispositivos", "device", "devices", "wearable", "health connect",
    "privacidad", "privacy", "permisos", "permissions", "consent",
    "línea de tiempo", "linea de tiempo", "timeline", "health history",
)

ACTION_HINTS: dict[str, str] = {
    "results": "resultado estudio laboratorio imagen",
    "measurements": "medicion presion peso actividad",
    "treatment": "tratamiento medicamento dosis",
    "appointments": "cita consulta especialista",
    "timeline": "linea de salud historia cronologia",
    "family": "familia genograma antecedente familiar",
    "documents": "documento archivo expediente informe",
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
    "clinical_interview": "consulta sintomas problema actual",
}


@dataclass(frozen=True)
class ConversationFrame:
    recent_turns: list[dict[str, str]]
    compact_summary: dict[str, Any]
    last_action_target: str | None
    last_mission_type: str | None
    ambiguous_reference: bool
    correction: bool
    routing_text: str

    def as_prompt_payload(self) -> dict[str, Any]:
        return {
            "recent_turns": self.recent_turns,
            "compact_summary": self.compact_summary,
            "last_action_target": self.last_action_target,
            "last_mission_type": self.last_mission_type,
            "ambiguous_reference": self.ambiguous_reference,
            "correction": self.correction,
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


def _has_explicit_current_topic(text: str) -> bool:
    return any(_contains_phrase(text, signal) for signal in EXPLICIT_TOPIC_SIGNALS)


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
            # Event-driven observations are persisted elsewhere; do not crowd out
            # the conversational thread unless they are the only recent context.
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


def _latest_topic_metadata(state: PatientState) -> tuple[str | None, str | None]:
    for message in reversed(state.messages):
        if message.role != "assistant":
            continue
        target = str(message.metadata.get("action_target") or "").strip() or None
        mission_type = str(message.metadata.get("mission_type") or "").strip() or None
        if not mission_type and message.mission_id:
            mission = next((item for item in reversed(state.missions) if item.id == message.mission_id), None)
            mission_type = mission.mission_type if mission else None
        if target or mission_type:
            return target, mission_type
    return None, None


def _is_ambiguous_followup(text: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    if any(_normalize(signal) in normalized for signal in REFERENCE_SIGNALS):
        return True
    if any(normalized.startswith(_normalize(signal)) for signal in CONTINUATION_SIGNALS):
        return True
    # Very short follow-ups are often semantically dependent on the prior turn.
    words = re.findall(r"[a-z0-9]+", normalized)
    return len(words) <= 5 and normalized not in {"hola", "hello", "gracias", "thanks", "thank you"}


def _is_correction(text: str) -> bool:
    normalized = _normalize(text)
    return any(_normalize(signal) in normalized for signal in CORRECTION_SIGNALS)


def _compact_summary(state: PatientState) -> dict[str, Any]:
    latest_result = state.results[-1] if state.results else None
    latest_vital = state.vitals[-1] if state.vitals else None
    latest_weight = state.weights[-1] if state.weights else None
    active_mission = next(
        (item for item in reversed(state.missions) if str(item.status) not in {"completed", "cancelled"}),
        None,
    )
    return {
        "latest_result": {
            "id": latest_result.id,
            "panel": latest_result.panel,
            "uploaded_at": latest_result.uploaded_at.isoformat(),
        } if latest_result else None,
        "latest_blood_pressure": {
            "systolic": latest_vital.systolic,
            "diastolic": latest_vital.diastolic,
            "measured_at": latest_vital.measured_at.isoformat(),
        } if latest_vital and latest_vital.systolic and latest_vital.diastolic else None,
        "latest_weight": {
            "kg": latest_weight.weight_kg,
            "measured_at": latest_weight.measured_at.isoformat(),
        } if latest_weight else None,
        "active_mission": {
            "id": active_mission.id,
            "type": active_mission.mission_type,
            "title": active_mission.title,
            "next_action": active_mission.next_action,
        } if active_mission else None,
    }


def build_frame(state: PatientState, patient_text: str) -> ConversationFrame:
    target, mission_type = _latest_topic_metadata(state)
    ambiguous = _is_ambiguous_followup(patient_text)
    correction = _is_correction(patient_text)
    routing_text = patient_text
    use_prior_hint = (
        not patient_text.startswith(ANSWER_PREFIX)
        and ambiguous
        and not _has_explicit_current_topic(patient_text)
    )
    if use_prior_hint:
        hint = ACTION_HINTS.get(target or "") or MISSION_HINTS.get(mission_type or "")
        if hint:
            # Preserve the exact patient words; append only a private routing hint.
            routing_text = f"{patient_text} | CONTEXTUAL_ROUTING_HINT: {hint}"
    return ConversationFrame(
        recent_turns=selective_memory(state),
        compact_summary=_compact_summary(state),
        last_action_target=target,
        last_mission_type=mission_type,
        ambiguous_reference=ambiguous,
        correction=correction,
        routing_text=routing_text,
    )


def semantic_packet(state: PatientState, patient_text: str) -> dict[str, Any]:
    """Compact context packet for the LLM's semantic reference resolution."""
    frame = build_frame(state, patient_text)
    return {
        "current_message": patient_text,
        "conversation": frame.as_prompt_payload(),
        "instruction": (
            "Resolve pronouns, corrections, ellipsis and references using only this recent conversation and authorized summary. "
            "If the user corrects the topic, follow the correction. Never invent a referenced fact that is absent."
        ),
    }
