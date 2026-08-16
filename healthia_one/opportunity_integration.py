from __future__ import annotations

import json
import unicodedata

from healthia_one.autopilot_claims import build_event_claim_store
from healthia_one.autopilot_events import build_event_outbox_store, stable_event_id
from healthia_one.autopilot_receipts import build_autopilot_receipt_store
from healthia_one.autopilot_runtime import AutopilotEvent, OpportunityAutopilot
from healthia_one.config import settings
from healthia_one.models import ChatMessage, ChatResponse, PatientState
from healthia_one.opportunity_autopilot import sync_watch_topics
from healthia_one.opportunity_chat import OpportunityChatController
from healthia_one.opportunity_permissions import build_radar_permission_store
from healthia_one.opportunity_store import build_opportunity_store
from healthia_one.program_source_verifier import (
    GeminiProgramSourceExtractor,
    OfficialProgramVerifier,
    ProgramSourceLoader,
    build_program_verification_store,
)
from healthia_one.research_radar import GroundedResourceRadar, ScientificRadar, SourceFetchError


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


_STORE = build_opportunity_store(settings)
_CLAIMS = build_event_claim_store(settings)
_RECEIPTS = build_autopilot_receipt_store(settings)
_OUTBOX = build_event_outbox_store(settings)
_PERMISSIONS = build_radar_permission_store(settings)
_VERIFICATIONS = build_program_verification_store(settings)
_SCIENTIFIC = ScientificRadar()


def _paid_resource_ai_enabled() -> bool:
    return bool(
        settings.adk_ready
        and settings.ai_request_limit > 0
        and settings.cost_mode != "local"
        and settings.cost_guard_start_enabled
    )


def _new_resource_radar() -> GroundedResourceRadar:
    # One explicit request gets one bounded grounded-search call. The budget is
    # deliberately per request, not a singleton lifetime counter.
    return GroundedResourceRadar(
        settings,
        enabled=_paid_resource_ai_enabled(),
        max_calls=1,
    )


_RESOURCE = _new_resource_radar()
_AUTOPILOT = OpportunityAutopilot(
    _STORE,
    scientific_radar=_SCIENTIFIC,
    resource_radar=_RESOURCE,
    claim_store=_CLAIMS,
    receipt_store=_RECEIPTS,
)
_CONTROLLER = OpportunityChatController(_AUTOPILOT)
_AUTO_OPEN_ACTIONS = {
    "show_discoveries",
    "therapeutic_comparison",
    "show_programs",
    "application_prefilled",
    "show_application_missing_items",
}


def _sync_topics(state: PatientState) -> None:
    vault = _STORE.load(state.profile.id)
    before = {(item.subject_id, item.condition.lower()) for item in vault.watch_topics}
    sync_watch_topics(vault, state)
    after = {(item.subject_id, item.condition.lower()) for item in vault.watch_topics}
    if after != before:
        _STORE.save(vault)


def _chat_response(result, *, metadata: dict | None = None) -> ChatResponse:
    payload = dict(result.metadata)
    payload.update(metadata or {})
    payload["opportunity_autopilot"] = True
    payload["action_target"] = "discoveries"
    ui_action = result.ui_action
    if ui_action is None and result.action in _AUTO_OPEN_ACTIONS:
        ui_action = {"type": "open_view", "view": "discoveries"}
    if ui_action:
        payload["ui_action"] = ui_action
        payload["health_os_control"] = True
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="HealthIA",
            content=result.content,
            metadata=payload,
        )
    )


def _permission_response(state: PatientState, patient_text: str) -> ChatResponse | None:
    normalized = _normalize(patient_text)
    permissions = _PERMISSIONS.load(state.profile.id)
    action = ""

    enable_science = (
        "activa el radar cientifico",
        "activar radar cientifico",
        "quiero recibir novedades cientificas",
        "vigila investigaciones sobre mi salud",
        "enable scientific radar",
    )
    disable_science = (
        "desactiva el radar cientifico",
        "desactivar radar cientifico",
        "no vigiles investigaciones",
        "disable scientific radar",
    )
    enable_resources = (
        "activa el radar de ayudas",
        "activar radar de ayudas",
        "vigila ayudas y recursos",
        "enable assistance radar",
    )
    disable_resources = (
        "desactiva el radar de ayudas",
        "desactivar radar de ayudas",
        "no vigiles ayudas",
        "disable assistance radar",
    )

    if any(phrase in normalized for phrase in disable_science):
        permissions.scientific_enabled = False
        action = "scientific_radar_disabled"
    elif any(phrase in normalized for phrase in disable_resources):
        permissions.resource_enabled = False
        action = "resource_radar_disabled"
    elif any(phrase in normalized for phrase in enable_science):
        permissions.scientific_enabled = True
        action = "scientific_radar_enabled"
    elif any(phrase in normalized for phrase in enable_resources):
        permissions.resource_enabled = True
        action = "resource_radar_enabled"
    else:
        return None

    _PERMISSIONS.save(permissions)
    english = any(token in normalized for token in ("enable", "disable", "radar"))
    if action == "scientific_radar_enabled":
        content = (
            "I enabled the autonomous scientific radar. It will watch only authorized patient/family topics and keep relevant findings in Discoveries."
            if english else
            "Activé el radar científico autónomo. Revisará sólo tus temas de salud/familia autorizados y guardará las novedades relevantes sin convertir cada publicación en una alerta. Puedes desactivarlo desde este chat."
        )
    elif action == "scientific_radar_disabled":
        content = (
            "I disabled the autonomous scientific radar. Manual searches you explicitly request remain available."
            if english else
            "Desactivé el radar científico autónomo. Las búsquedas que tú pidas manualmente seguirán disponibles."
        )
    elif action == "resource_radar_enabled":
        content = (
            "I enabled the autonomous assistance radar. Grounded web search remains cost-bounded, and no program is treated as eligible until official requirements are verified."
            if english else
            "Activé el radar autónomo de ayudas y recursos. La búsqueda web seguirá limitada por el guard de costos y ningún programa se tratará como elegible hasta verificar requisitos oficiales. Puedes desactivarlo aquí."
        )
    else:
        content = (
            "I disabled the autonomous assistance radar. You can still request a manual assistance search whenever you want."
            if english else
            "Desactivé el radar autónomo de ayudas y recursos. Puedes seguir pidiéndome búsquedas manuales cuando quieras."
        )

    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="HealthIA",
            content=content,
            metadata={
                "opportunity_autopilot": True,
                "radar_permission_action": action,
                "scientific_radar_enabled": permissions.scientific_enabled,
                "resource_radar_enabled": permissions.resource_enabled,
                "action_target": "discoveries",
            },
        )
    )


def _resource_location(state: PatientState) -> dict[str, str]:
    """Return only patient-entered location evidence; locale is never residence."""
    return {
        "country": "",
        "region": "",
        "locality": str(state.profile.address or "")[:220],
    }


def enqueue_event(
    state: PatientState,
    event_type: str,
    *,
    dedupe_key: str,
    subject_id: str = "",
    condition: str = "",
    payload: dict | None = None,
) -> AutopilotEvent:
    """Persist one patient event without performing network/model work."""
    normalized_payload = payload or {}
    key_material = json.dumps(normalized_payload, sort_keys=True, ensure_ascii=False, default=str)
    event = AutopilotEvent(
        id=stable_event_id(state.profile.id, event_type, f"{dedupe_key}|{key_material}"),
        patient_id=state.profile.id,
        event_type=event_type,
        subject_id=subject_id,
        condition=condition,
        payload=normalized_payload,
    )
    _OUTBOX.put(event)
    return event


def _explicit_science_refresh(text: str) -> bool:
    normalized = _normalize(text)
    return any(
        phrase in normalized
        for phrase in (
            "que hay nuevo",
            "investigacion nueva",
            "novedades sobre",
            "new research",
            "what is new",
        )
    )


def _related_to_notice(text: str, condition: str, subject_label: str) -> bool:
    normalized = _normalize(text)
    needles = [_normalize(condition), _normalize(subject_label)]
    return any(needle and needle in normalized for needle in needles)


def _explicit_resource_topic(state: PatientState, patient_text: str) -> tuple[str, str]:
    """Narrow an explicit assistance search to a known patient/family topic when possible."""
    normalized = _normalize(patient_text)
    vault = _STORE.load(state.profile.id)
    aliases = {
        "autismo": ("autismo", "autism"),
        "autism": ("autism", "autismo"),
        "vih": ("vih", "hiv"),
        "hiv": ("hiv", "vih"),
        "cancer": ("cancer", "cáncer"),
    }
    scored: list[tuple[int, str, str]] = []
    for topic in vault.watch_topics:
        condition = _normalize(topic.condition)
        terms = {condition}
        for key, values in aliases.items():
            if key in condition:
                terms.update(_normalize(item) for item in values)
        score = max((len(term) for term in terms if term and term in normalized), default=0)
        if score:
            scored.append((score, topic.subject_id, topic.condition))
    if not scored:
        return "", ""
    scored.sort(reverse=True)
    return scored[0][1], scored[0][2]


def _application_request(text: str) -> bool:
    normalized = _normalize(text)
    return any(
        phrase in normalized
        for phrase in (
            "completa el formulario",
            "completar formulario",
            "prepara la solicitud",
            "aplica a esa ayuda",
            "aplicar a esa ayuda",
            "fill the form",
            "prepare the application",
            "apply for that program",
        )
    )


def _program_for_text(state: PatientState, text: str):
    vault = _STORE.load(state.profile.id)
    normalized = _normalize(text)
    candidates = []
    for program in vault.programs:
        title = _normalize(program.title)
        provider = _normalize(program.provider)
        score = 0
        if title and title in normalized:
            score += 4
        if provider and provider in normalized:
            score += 2
        score += sum(1 for token in set(title.split()) if len(token) >= 4 and token in normalized)
        if score:
            candidates.append((score, program))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    return vault.programs[-1] if len(vault.programs) == 1 else None


def _program_needs_verification(program) -> bool:
    requirements = list(getattr(program, "requirements", []) or [])
    if not requirements:
        return True
    return any(bool((item.rule or {}).get("source_verification_required")) for item in requirements)


def _verify_program_before_prefill(state: PatientState, patient_text: str) -> dict:
    if not _application_request(patient_text):
        return {}
    program = _program_for_text(state, patient_text)
    if program is None or not _program_needs_verification(program):
        return {}
    if not _paid_resource_ai_enabled():
        return {
            "program_source_verification": "blocked_cost_guard",
            "program_id": getattr(program, "id", ""),
        }

    verifier = OfficialProgramVerifier(
        loader=ProgramSourceLoader(),
        extractor=GeminiProgramSourceExtractor(settings, enabled=True, max_calls=1),
        store=_VERIFICATIONS,
    )
    try:
        verification = verifier.verify(state.profile.id, program)
    except Exception as exc:
        # Fail closed. The application engine will keep unknown requirements as
        # missing instead of converting a source problem into eligibility.
        return {
            "program_source_verification": "failed_closed",
            "program_id": getattr(program, "id", ""),
            "error_type": type(exc).__name__,
        }

    vault = _STORE.load(state.profile.id)
    for index, item in enumerate(vault.programs):
        if item.id == program.id:
            vault.programs[index] = verification.apply(item)
            _STORE.save(vault)
            break
    return {
        "program_source_verification": "completed",
        "program_id": program.id,
        "source_url": verification.final_url,
        "source_sha256": verification.source_sha256,
        "verified_requirements": len(verification.requirements),
        "verified_documents": len(verification.required_documents),
    }


def respond(state: PatientState, patient_text: str) -> ChatResponse | None:
    """Handle Opportunity Autopilot intents before generic clinical routing."""
    _sync_topics(state)

    permission_response = _permission_response(state, patient_text)
    if permission_response is not None:
        return permission_response

    verification_meta = _verify_program_before_prefill(state, patient_text)
    result = _CONTROLLER.handle(state, patient_text)
    if result is not None:
        if result.action == "show_discoveries" and result.metadata.get("new_discoveries", 0) == 0 and _explicit_science_refresh(patient_text):
            event = AutopilotEvent(
                patient_id=state.profile.id,
                event_type="manual.discovery_refresh",
            )
            try:
                report = _AUTOPILOT.process(
                    state,
                    event,
                    allow_scientific_network=True,
                    allow_paid_resource_search=False,
                )
                refreshed = _CONTROLLER.handle(state, patient_text)
                if refreshed is not None:
                    return _chat_response(
                        refreshed,
                        metadata={
                            "scientific_refresh": report.model_dump(mode="json"),
                            "model_spend_for_retrieval": 0,
                        },
                    )
            except SourceFetchError:
                result.content = (
                    "Intenté revisar las fuentes científicas, pero una fuente externa no respondió correctamente. "
                    "No inventé resultados ni gasté una llamada de Gemini para rellenar el vacío."
                )
                return _chat_response(result, metadata={"scientific_refresh_failed_closed": True})

        if result.action == "request_resource_refresh":
            subject_id, condition = _explicit_resource_topic(state, patient_text)
            event = AutopilotEvent(
                patient_id=state.profile.id,
                event_type="manual.resource_refresh",
                subject_id=subject_id,
                condition=condition,
                payload=_resource_location(state),
            )
            radar = _new_resource_radar()
            if not radar.enabled:
                result.content += (
                    " Grounded web search is disabled by the current cost guard, so I did not make a hidden paid call."
                    if "find " in _normalize(patient_text) else
                    " En este entorno la búsqueda web pagada está desactivada por el guard de costos; no haré llamadas ocultas."
                )
                return _chat_response(result, metadata={"paid_search_enabled": False})
            _AUTOPILOT.resource_radar = radar
            report = _AUTOPILOT.process(
                state,
                event,
                allow_scientific_network=False,
                allow_paid_resource_search=True,
            )
            refreshed = _CONTROLLER.handle(
                state,
                "financial assistance" if "find " in _normalize(patient_text) else "ayuda económica",
            )
            if refreshed is not None:
                return _chat_response(
                    refreshed,
                    metadata={
                        "resource_refresh": report.model_dump(mode="json"),
                        "resource_topic_subject_id": subject_id,
                        "resource_topic_condition": condition,
                        "grounded_search_calls": radar.calls,
                    },
                )

        return _chat_response(result, metadata=verification_meta)

    notice = _AUTOPILOT.next_notice(state.profile.id)
    if notice and _related_to_notice(patient_text, notice.condition, notice.subject_label):
        _AUTOPILOT.mark_discovery_seen(state.profile.id, notice.id, save=True)
        scope = "tu salud" if notice.relation == "self" else f"{notice.subject_label} ({notice.relation})"
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                author="HealthIA",
                content=(
                    f"Por cierto, como estás hablando de {scope}, guardé una novedad que puede interesarte: "
                    f"**{notice.title}**. No cambia por sí sola ningún tratamiento. "
                    "Si quieres, te explico qué encontró la fuente y cómo se compara con lo que tenemos registrado."
                ),
                metadata={
                    "opportunity_autopilot": True,
                    "contextual_discovery": True,
                    "discovery_id": notice.id,
                    "action_target": "discoveries",
                },
            )
        )
    return None


def autopilot() -> OpportunityAutopilot:
    return _AUTOPILOT


def outbox():
    return _OUTBOX


def radar_permissions():
    return _PERMISSIONS