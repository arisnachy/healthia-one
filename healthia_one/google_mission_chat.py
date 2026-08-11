from __future__ import annotations

import json
import re
import unicodedata

from healthia_one.control import audit
from healthia_one.conversation_brain import build_frame, explicit_topic, semantic_packet
from healthia_one.google_constellation_singleton import get_google_constellation_service
from healthia_one.google_mission_adk import AdkGoogleMissionRuntime
from healthia_one.models import ChatMessage, ChatResponse, PatientState


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


_NAVIGATION_PATTERNS = (
    r"\bbuscame (?:un |una |los |las )?(?:centro|clinica|fundacion|terapia|especialista)",
    r"\bbusca (?:un |una |los |las )?(?:centro|clinica|fundacion|terapia|especialista).*(?:cerca|en )",
    r"\bcentros? (?:cerca|en )",
    r"\bdonde puedo (?:ir|llevar|encontrar)",
    r"\bconsigueme (?:una )?cita",
    r"\bfind (?:a |an )?(?:clinic|center|provider|therapist|specialist).*(?:near| in )",
    r"\bwhere can i (?:go|take|find)",
    r"\bget me an appointment",
)

_CONTINUATION_PATTERNS = (
    r"\bcontacta (?:ese|ese centro|esa clinica|esa fundacion)",
    r"\bescribeles\b",
    r"\bescribe(?:le|les)\b.*(?:centro|clinica|fundacion|doctor)",
    r"\bque contestaron\b",
    r"\bque respondieron\b",
    r"\bque paso con (?:la cita|el centro|la solicitud)\b",
    r"\b(?:el|la) (?:primero|primera|segundo|segunda|tercero|tercera)\b",
    r"\bese me sirve\b",
    r"\besa me sirve\b",
    r"\bme sirve (?:ese|esa|el primero|la primera|el segundo|la segunda)\b",
    r"\bel (?:lunes|martes|miercoles|jueves|viernes|sabado|domingo) me sirve\b",
    r"\bagenda (?:esa|la) cita\b",
    r"\bagendala\b",
    r"\breservala\b",
    r"\bcontinua con (?:eso|esa|ese|la mision|la misión)\b",
    r"\bcontact (?:that|the) (?:center|clinic|provider)\b",
    r"\bwhat did they (?:say|reply)\b",
    r"\bbook (?:that|the) appointment\b",
    r"\bthe (?:first|second|third) one\b",
    r"\bthat one works\b",
    r"\bcontinue (?:that|the mission)\b",
)

_STRONG_GENERIC_CONTINUATIONS = {
    "dale con eso",
    "continua con eso",
    "continúa con eso",
    "sigue con eso",
    "hazlo con ese",
    "hazlo con esa",
    "go ahead with that",
    "continue with that",
}

_NEGATIVE_CONTEXTS = (
    "beneficios de caminar",
    "beneficios del ejercicio",
    "benefits of walking",
    "benefits of exercise",
)

_NON_GOOGLE_EXPLICIT_TOPICS = {"results", "measurements", "treatment", "family", "documents", "devices", "control", "timeline"}


def latest_google_mission_id(state: PatientState) -> str:
    for message in reversed(state.messages[-24:]):
        metadata = message.metadata or {}
        mission_id = str(metadata.get("google_mission_id") or "").strip()
        if mission_id:
            return mission_id
    return ""


def should_consider_google_mission(state: PatientState, patient_text: str) -> bool:
    normalized = _normalize(patient_text)
    if not normalized or any(item in normalized for item in _NEGATIVE_CONTEXTS):
        return False
    if any(re.search(pattern, normalized) for pattern in _NAVIGATION_PATTERNS):
        return True

    mission_id = latest_google_mission_id(state)
    if not mission_id:
        return False

    topic = explicit_topic(patient_text)
    if topic in _NON_GOOGLE_EXPLICIT_TOPICS:
        return False

    frame = build_frame(state, patient_text)
    if any(re.search(pattern, normalized) for pattern in _CONTINUATION_PATTERNS):
        return True
    if normalized in {_normalize(item) for item in _STRONG_GENERIC_CONTINUATIONS}:
        return True
    return bool(frame.ambiguous_reference and (frame.correction or len(normalized.split()) >= 2))


def _conversation_context(state: PatientState, patient_text: str) -> str:
    packet = semantic_packet(state, patient_text)
    packet["active_google_mission_id"] = latest_google_mission_id(state)
    packet["mission_policy"] = (
        "Advance every verifiable non-mutating/read-only step until the next patient choice, exact authorization, "
        "or real external event boundary. Never infer an external reply or consent."
    )
    return json.dumps(packet, ensure_ascii=False, default=str)[:6000]


def _public_step_labels(executed_tools: list[str]) -> list[str]:
    labels = {
        "inspect_google_health_mission": "Revisó el estado durable de la misión",
        "start_navigation_mission": "Creó la misión de navegación",
        "discover_care_options": "Buscó opciones verificables",
        "select_discovered_candidate": "Aplicó la selección del paciente",
        "check_calendar_window": "Revisó disponibilidad autorizada",
        "contact_selected_provider": "Intentó avanzar el contacto bajo autorización",
        "select_offered_slot": "Aplicó el horario ofrecido elegido",
        "finalize_selected_appointment": "Intentó cerrar cita/seguimiento bajo autorización",
    }
    return [labels[name] for name in executed_tools if name in labels]


def _receipt_markdown(receipt: dict) -> str:
    steps = [str(item) for item in receipt.get("executed_steps", []) if str(item)]
    lines = ["### Comprobante de misión"]
    if steps:
        lines.extend(f"- ✓ {step}" for step in steps)
    if receipt.get("requires_human_authorization"):
        lines.append("- ⏸ Detenido en autorización humana; HealthIA no ejecutó ese paso por su cuenta.")
    elif receipt.get("outcome") == "waiting_external_event":
        lines.append("- ⏳ Esperando una respuesta externa real; HealthIA no hará polling ni inventará una respuesta.")
    elif receipt.get("outcome") == "completed":
        lines.append("- ✓ Misión cerrada con resultado durable.")
    elif receipt.get("next_action"):
        lines.append(f"- Siguiente paso: {receipt['next_action']}")
    return "\n".join(lines)


class GoogleMissionConversationRouter:
    """Chat-first semantic entry to the shared Google mission runtime."""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.constellation = get_google_constellation_service(settings)
        self.adk = AdkGoogleMissionRuntime(settings, constellation=self.constellation)

    async def respond(self, state: PatientState, patient_text: str) -> ChatResponse | None:
        if not should_consider_google_mission(state, patient_text):
            return None
        if not self.adk.ready:
            return None

        plan = await self.adk.run(
            patient_id=state.profile.id,
            patient_text=patient_text,
            conversation_context=_conversation_context(state, patient_text),
            authorized_location=None,
        )
        if not plan or str(plan.get("intent") or "") == "not_applicable":
            return None

        mission_id = str(plan.get("mission_id") or latest_google_mission_id(state))
        state_name = str(plan.get("state") or "")
        next_action = str(plan.get("next_action") or "")
        requires_auth = bool(plan.get("requires_human_authorization"))
        auth_kind = str(plan.get("authorization_kind") or "")
        content = str(plan.get("patient_message") or "").strip()
        if not content:
            content = "Organicé esta tarea como una misión de navegación sanitaria y conservaré cada acción verificable."

        execution = plan.get("_execution") if isinstance(plan.get("_execution"), dict) else {}
        executed_tools = [str(item) for item in execution.get("executed_tools", []) if str(item)]
        outcome = (
            "waiting_authorization" if requires_auth else
            "waiting_external_event" if state_name == "awaiting_external_event" else
            "completed" if state_name == "completed" else
            "advanced"
        )
        receipt = {
            "mission_id": mission_id,
            "state": state_name,
            "outcome": outcome,
            "next_action": next_action,
            "requires_human_authorization": requires_auth,
            "authorization_kind": auth_kind,
            "executed_steps": _public_step_labels(executed_tools),
            "tool_count": len(executed_tools),
            "durable_mission": bool(mission_id),
        }
        content = f"{content}\n\n{_receipt_markdown(receipt)}"

        metadata = {
            "google_constellation": True,
            "google_mission_id": mission_id,
            "google_mission_state": state_name,
            "google_mission_next_action": next_action,
            "requires_human_authorization": requires_auth,
            "authorization_kind": auth_kind,
            "health_os_control": bool(mission_id),
            "autonomy_policy": "advance_until_human_or_external_event_boundary",
            "public_action_receipt": receipt,
        }
        ui_action = plan.get("ui_action")
        if isinstance(ui_action, dict):
            metadata["ui_action"] = ui_action

        audit(
            state,
            actor="google_adk",
            action="advance_google_health_mission",
            resource_type="google_health_mission",
            resource_id=mission_id,
            details={
                "state": state_name,
                "next_action": next_action,
                "requires_human_authorization": requires_auth,
                "authorization_kind": auth_kind,
                "executed_tools": executed_tools,
                "tool_count": len(executed_tools),
            },
        )

        return ChatResponse(
            message=ChatMessage(
                patient_id=state.profile.id,
                role="assistant",
                author="HealthIA",
                content=content,
                metadata=metadata,
            )
        )
