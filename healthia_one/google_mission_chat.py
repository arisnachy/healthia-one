from __future__ import annotations

import re
import unicodedata

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
    r"\bel (?:lunes|martes|miercoles|jueves|viernes|sabado|domingo) me sirve\b",
    r"\bagenda (?:esa|la) cita\b",
    r"\bagendala\b",
    r"\bcontact (?:that|the) (?:center|clinic|provider)\b",
    r"\bwhat did they (?:say|reply)\b",
    r"\bbook (?:that|the) appointment\b",
)

_NEGATIVE_CONTEXTS = (
    "beneficios de caminar",
    "beneficios del ejercicio",
    "benefits of walking",
    "benefits of exercise",
)


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
    if latest_google_mission_id(state) and any(
        re.search(pattern, normalized) for pattern in _CONTINUATION_PATTERNS
    ):
        return True
    return False


def _conversation_context(state: PatientState) -> str:
    lines: list[str] = []
    for item in state.messages[-10:]:
        content = " ".join(str(item.content or "").split())[:700]
        if content:
            lines.append(f"{item.role}: {content}")
    mission_id = latest_google_mission_id(state)
    if mission_id:
        lines.append(f"active_google_mission_id: {mission_id}")
    return "\n".join(lines)[-6000:]


class GoogleMissionConversationRouter:
    """Chat-first semantic entry to the shared Google mission runtime.

    This router must be invoked only after deterministic clinical safety. It has
    no authorization-creation method. Gemini can inspect/start/advance a mission,
    but exact external mutations still stop at the durable human authorization
    boundary.
    """

    def __init__(self, settings) -> None:
        self.settings = settings
        self.constellation = get_google_constellation_service(settings)
        self.adk = AdkGoogleMissionRuntime(settings, constellation=self.constellation)

    async def respond(self, state: PatientState, patient_text: str) -> ChatResponse | None:
        if not should_consider_google_mission(state, patient_text):
            return None
        if not self.adk.ready:
            # Do not replace a normal HealthIA reply with a pretend Google action
            # when the real Gemini/ADK mission runtime is unavailable.
            return None

        plan = await self.adk.run(
            patient_id=state.profile.id,
            patient_text=patient_text,
            conversation_context=_conversation_context(state),
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

        metadata = {
            "google_constellation": True,
            "google_mission_id": mission_id,
            "google_mission_state": state_name,
            "google_mission_next_action": next_action,
            "requires_human_authorization": requires_auth,
            "authorization_kind": auth_kind,
            "health_os_control": bool(mission_id),
        }
        ui_action = plan.get("ui_action")
        if isinstance(ui_action, dict):
            # The model may request only ordinary Health OS navigation metadata;
            # authorization remains a deterministic patient action outside ADK.
            metadata["ui_action"] = ui_action

        return ChatResponse(
            message=ChatMessage(
                patient_id=state.profile.id,
                role="assistant",
                author="HealthIA",
                content=content,
                metadata=metadata,
            )
        )
