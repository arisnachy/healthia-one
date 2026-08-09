from __future__ import annotations

import unicodedata

from healthia_one.autopilot_runtime import AutopilotEvent, OpportunityAutopilot
from healthia_one.config import settings
from healthia_one.models import ChatMessage, ChatResponse, PatientState
from healthia_one.opportunity_autopilot import sync_watch_topics
from healthia_one.opportunity_chat import OpportunityChatController
from healthia_one.opportunity_store import build_opportunity_store
from healthia_one.research_radar import GroundedResourceRadar, ScientificRadar, SourceFetchError


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


_STORE = build_opportunity_store(settings)
_SCIENTIFIC = ScientificRadar()
_RESOURCE = GroundedResourceRadar(
    settings,
    enabled=bool(
        settings.adk_ready
        and settings.ai_request_limit > 0
        and settings.cost_mode != "local"
        and settings.cost_guard_start_enabled
    ),
    max_calls=1,
)
_AUTOPILOT = OpportunityAutopilot(
    _STORE,
    scientific_radar=_SCIENTIFIC,
    resource_radar=_RESOURCE,
)
_CONTROLLER = OpportunityChatController(_AUTOPILOT)


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
    if result.ui_action:
        payload["ui_action"] = result.ui_action
        payload["health_os_control"] = True
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="HealthIA",
            content=result.content,
            metadata=payload,
        )
    )


def _country_from_locale(state: PatientState) -> str:
    locale = str(state.profile.locale or "")
    return locale.rsplit("-", 1)[-1].upper() if "-" in locale else ""


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


def respond(state: PatientState, patient_text: str) -> ChatResponse | None:
    """Handle Opportunity Autopilot intents before generic clinical routing.

    Cheap scientific refreshes can occur on an explicit patient request. Paid
    grounded resource search is still gated by the existing cost-start setting.
    """
    _sync_topics(state)

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
            event = AutopilotEvent(
                patient_id=state.profile.id,
                event_type="manual.resource_refresh",
                payload={
                    "country": _country_from_locale(state),
                    "region": "",
                    "locality": state.profile.address[:220],
                },
            )
            if not _RESOURCE.enabled:
                result.content += (
                    " En este entorno la búsqueda web pagada está desactivada por el guard de costos; "
                    "no haré llamadas ocultas."
                )
                return _chat_response(result, metadata={"paid_search_enabled": False})
            report = _AUTOPILOT.process(
                state,
                event,
                allow_scientific_network=False,
                allow_paid_resource_search=True,
            )
            refreshed = _CONTROLLER.handle(state, "ayuda económica")
            if refreshed is not None:
                return _chat_response(
                    refreshed,
                    metadata={"resource_refresh": report.model_dump(mode="json")},
                )

        return _chat_response(result)

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
