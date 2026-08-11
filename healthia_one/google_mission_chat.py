from __future__ import annotations

import json
import re
import unicodedata

from healthia_one.control import audit
from healthia_one.conversation_brain import build_frame, explicit_topic, semantic_packet
from healthia_one.google_constellation import GrantBundle
from healthia_one.google_constellation_singleton import get_google_constellation_service
from healthia_one.google_mission_adk import AdkGoogleMissionRuntime, GoogleMissionToolFacade
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

_LOCATION_CONSENT_PATTERNS = (
    r"\bautorizo (?:usar )?(?:mi )?ubicacion para (?:esta|la) mision\b",
    r"\bautorizo (?:la )?ubicacion (?:solo )?para (?:esta|la) mision\b",
    r"\bpuedes usar (?:mi )?ubicacion para (?:esta|la) mision\b",
    r"\bauthorize (?:my )?location for this mission\b",
    r"\bi authorize (?:my )?location for this mission\b",
    r"\byou may use (?:my )?location for this mission\b",
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


def _is_location_consent(patient_text: str) -> bool:
    normalized = _normalize(patient_text)
    return any(re.search(pattern, normalized) for pattern in _LOCATION_CONSENT_PATTERNS)


def should_consider_google_mission(state: PatientState, patient_text: str) -> bool:
    normalized = _normalize(patient_text)
    if not normalized or any(item in normalized for item in _NEGATIVE_CONTEXTS):
        return False
    if any(re.search(pattern, normalized) for pattern in _NAVIGATION_PATTERNS):
        return True

    mission_id = latest_google_mission_id(state)
    if not mission_id:
        return False
    if _is_location_consent(patient_text):
        return True

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


def _public_step_labels(executed_tools: list[str], *, authorization_kind: str = "") -> list[str]:
    labels = {
        "inspect_google_health_mission": "Revisó el estado durable de la misión",
        "start_navigation_mission": "Creó la misión de navegación",
        "discover_care_options": (
            "Preparó la búsqueda y comprobó el consentimiento de ubicación"
            if authorization_kind == "maps_location_for_mission"
            else "Buscó opciones verificables"
        ),
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
        if receipt.get("authorization_kind") == "maps_location_for_mission":
            lines.append("- ⏸ Necesito tu permiso para usar la ubicación de esta misión en Google Places. Todavía no hice la búsqueda.")
            lines.append("- Para continuar puedes decir: **Autorizo ubicación para esta misión.**")
        else:
            lines.append("- ⏸ Detenido en autorización humana; HealthIA no ejecutó ese paso por su cuenta.")
    elif receipt.get("outcome") == "waiting_external_event":
        lines.append("- ⏳ Esperando una respuesta externa real; HealthIA no hará polling ni inventará una respuesta.")
    elif receipt.get("outcome") == "completed":
        lines.append("- ✓ Misión cerrada con resultado durable.")
    elif receipt.get("next_action"):
        lines.append(f"- Siguiente paso: {receipt['next_action']}")
    return "\n".join(lines)


def _durable_boundary(constellation, patient_id: str, mission_id: str) -> dict:
    if not mission_id:
        return {}
    try:
        mission = constellation.load_mission(patient_id, mission_id)
    except (KeyError, PermissionError):
        return {}
    boundary = mission.tool_outputs.get("authorization_boundary")
    if not isinstance(boundary, dict):
        return {}
    return dict(boundary)


class GoogleMissionConversationRouter:
    """Chat-first semantic entry to the shared Google mission runtime."""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.constellation = get_google_constellation_service(settings)
        self.adk = AdkGoogleMissionRuntime(settings, constellation=self.constellation)

    def _grant_explicit_location_consent(self, state: PatientState, patient_text: str) -> tuple[bool, str]:
        if not _is_location_consent(patient_text):
            return False, ""
        mission_id = latest_google_mission_id(state)
        if not mission_id:
            return False, ""
        boundary = _durable_boundary(self.constellation, state.profile.id, mission_id)
        if str(boundary.get("kind") or "") != "maps_location_for_mission":
            return False, mission_id
        grant = self.constellation.grant(
            state.profile.id,
            GrantBundle.MAPS_LOCATION,
            mission_id=mission_id,
            ttl_minutes=30,
        )
        audit(
            state,
            actor="patient",
            action="authorize_google_location_for_mission",
            resource_type="google_health_mission",
            resource_id=mission_id,
            details={
                "grant_bundle": str(GrantBundle.MAPS_LOCATION),
                "grant_id": grant.id,
                "mission_scoped": True,
                "expires_at": grant.expires_at.isoformat() if grant.expires_at else "",
                "external_action_performed": False,
            },
        )
        return True, mission_id

    async def respond(self, state: PatientState, patient_text: str) -> ChatResponse | None:
        if not should_consider_google_mission(state, patient_text):
            return None

        location_consent_granted, consent_mission_id = self._grant_explicit_location_consent(state, patient_text)

        # Exact mission-scoped location consent is the last human boundary before
        # the already-planned read-only Places lookup. Resume the same ADK tool
        # deterministically instead of asking Gemini to reinterpret the consent turn.
        if location_consent_granted and consent_mission_id:
            tool_result = GoogleMissionToolFacade(
                constellation=self.constellation,
                patient_id=state.profile.id,
                patient_text=patient_text,
            ).discover_care_options(consent_mission_id)
            consent_mission = self.constellation.load_mission(state.profile.id, consent_mission_id)
            candidates = (consent_mission.tool_outputs or {}).get("place_candidates") or []
            boundary = (consent_mission.tool_outputs or {}).get("authorization_boundary") or {}
            state_name = str(consent_mission.state)
            search_completed = not boundary and state_name == "awaiting_selection"
            next_action = (
                "patient_or_context_selects_candidate"
                if candidates
                else "refine_search_or_location"
            )
            english = "authorize" in _normalize(patient_text) or "location" in _normalize(patient_text)
            if search_completed and candidates:
                lead = (
                    f"Your location permission was applied only to this mission. I resumed the authorized Google Places search and found {len(candidates)} candidate(s). Choose the option you prefer."
                    if english else
                    f"Tu permiso de ubicación quedó limitado a esta misión. Reanudé la búsqueda autorizada en Google Places y encontré {len(candidates)} opción(es). Elige la que prefieras."
                )
            elif search_completed:
                lead = (
                    "Your location permission was applied only to this mission. I completed the authorized Google Places search, but it returned no candidates; I will not invent one."
                    if english else
                    "Tu permiso de ubicación quedó limitado a esta misión. Completé la búsqueda autorizada en Google Places, pero no devolvió candidatos; no voy a inventar uno."
                )
            else:
                lead = (
                    "Your mission-scoped location permission was recorded, but the authorized Google Places lookup could not complete. I did not invent a result."
                    if english else
                    "Tu permiso de ubicación quedó registrado sólo para esta misión, pero la búsqueda autorizada en Google Places no pudo completarse. No inventé resultados."
                )
            receipt = {
                "mission_id": consent_mission_id,
                "state": state_name,
                "outcome": "advanced" if search_completed else "blocked",
                "next_action": next_action,
                "requires_human_authorization": False,
                "authorization_kind": "",
                "executed_steps": [
                    "Registró consentimiento temporal de ubicación para esta misión",
                    (
                        "Buscó opciones verificables en Google Places"
                        if search_completed else
                        "Intentó la búsqueda autorizada en Google Places"
                    ),
                ],
                "tool_count": 1,
                "durable_mission": True,
            }
            audit(
                state,
                actor="google_adk_policy",
                action="resume_google_health_mission_after_location_consent",
                resource_type="google_health_mission",
                resource_id=consent_mission_id,
                details={
                    "state": state_name,
                    "candidate_count": len(candidates),
                    "search_completed": search_completed,
                    "executed_tool": "discover_care_options",
                    "external_mutation": False,
                },
            )
            return ChatResponse(
                message=ChatMessage(
                    patient_id=state.profile.id,
                    role="assistant",
                    author="HealthIA",
                    content=f"{lead}\n\n{_receipt_markdown(receipt)}",
                    metadata={
                        "google_constellation": True,
                        "google_mission_id": consent_mission_id,
                        "google_mission_state": state_name,
                        "google_mission_next_action": next_action,
                        "requires_human_authorization": False,
                        "authorization_kind": "",
                        "health_os_control": True,
                        "autonomy_policy": "advance_until_human_or_external_event_boundary",
                        "public_action_receipt": receipt,
                        "external_action_executed": search_completed,
                        "external_mutation_performed": False,
                        "policy_executed_tool": "discover_care_options",
                    },
                )
            )

        if not self.adk.ready:
            if not location_consent_granted:
                return None
            receipt = {
                "mission_id": consent_mission_id,
                "state": "authorized_location",
                "outcome": "advanced",
                "next_action": "continue_mission_when_agent_runtime_is_available",
                "requires_human_authorization": False,
                "authorization_kind": "",
                "executed_steps": ["Registró consentimiento temporal de ubicación para esta misión"],
                "tool_count": 0,
                "durable_mission": True,
            }
            return ChatResponse(
                message=ChatMessage(
                    patient_id=state.profile.id,
                    role="assistant",
                    author="HealthIA",
                    content=(
                        "Tu permiso de ubicación quedó limitado a esta misión y por tiempo limitado. "
                        "No ejecuté una búsqueda porque el runtime de misión no está disponible ahora.\n\n"
                        + _receipt_markdown(receipt)
                    ),
                    metadata={
                        "google_constellation": True,
                        "google_mission_id": consent_mission_id,
                        "public_action_receipt": receipt,
                        "external_action_executed": False,
                    },
                )
            )

        plan = await self.adk.run(
            patient_id=state.profile.id,
            patient_text=patient_text,
            conversation_context=_conversation_context(state, patient_text),
            authorized_location=None,
        )
        if not plan or str(plan.get("intent") or "") == "not_applicable":
            if not location_consent_granted:
                return None
            receipt = {
                "mission_id": consent_mission_id,
                "state": "authorized_location",
                "outcome": "advanced",
                "next_action": "continue_google_mission",
                "requires_human_authorization": False,
                "authorization_kind": "",
                "executed_steps": ["Registró consentimiento temporal de ubicación para esta misión"],
                "tool_count": 0,
                "durable_mission": True,
            }
            return ChatResponse(
                message=ChatMessage(
                    patient_id=state.profile.id,
                    role="assistant",
                    author="HealthIA",
                    content=(
                        "Tu permiso quedó registrado sólo para esta misión. La búsqueda todavía no se ejecutó; puedes pedirme que continúe.\n\n"
                        + _receipt_markdown(receipt)
                    ),
                    metadata={
                        "google_constellation": True,
                        "google_mission_id": consent_mission_id,
                        "public_action_receipt": receipt,
                        "external_action_executed": False,
                    },
                )
            )

        mission_id = str(plan.get("mission_id") or consent_mission_id or latest_google_mission_id(state))
        state_name = str(plan.get("state") or "")
        next_action = str(plan.get("next_action") or "")
        requires_auth = bool(plan.get("requires_human_authorization"))
        auth_kind = str(plan.get("authorization_kind") or "")
        content = str(plan.get("patient_message") or "").strip()
        if not content:
            content = "Organicé esta tarea como una misión de navegación sanitaria y conservaré cada acción verificable."

        boundary = _durable_boundary(self.constellation, state.profile.id, mission_id)
        boundary_kind = str(boundary.get("kind") or "")
        if boundary_kind == "maps_location_for_mission":
            requires_auth = True
            auth_kind = boundary_kind
            next_action = "authorize_location_for_mission"
            state_name = "blocked"

        execution = plan.get("_execution") if isinstance(plan.get("_execution"), dict) else {}
        executed_tools = [str(item) for item in execution.get("executed_tools", []) if str(item)]
        executed_steps = _public_step_labels(executed_tools, authorization_kind=auth_kind)
        if location_consent_granted:
            executed_steps.insert(0, "Registró consentimiento temporal de ubicación para esta misión")
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
            "executed_steps": executed_steps,
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
        if auth_kind == "maps_location_for_mission" and mission_id:
            metadata["ui_action"] = {
                "type": "authorize_google_location",
                "mission_id": mission_id,
                "ttl_minutes": 30,
                "label_es": "Autorizar ubicación para esta misión",
                "label_en": "Authorize location for this mission",
            }
        else:
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
                "location_consent_granted_this_turn": location_consent_granted,
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
