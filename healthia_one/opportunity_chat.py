from __future__ import annotations

import unicodedata
from typing import Any

from pydantic import BaseModel, Field

from healthia_one.autopilot_runtime import AutopilotEvent, OpportunityAutopilot
from healthia_one.models import PatientState
from healthia_one.opportunity_autopilot import (
    DiscoveryStatus,
    OpportunityVault,
    opportunity_snapshot,
    therapeutic_comparison,
)


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


class OpportunityChatResult(BaseModel):
    handled: bool = True
    content: str
    action: str = ""
    resource_id: str = ""
    ui_action: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _mentions(text: str, phrases: tuple[str, ...]) -> bool:
    normalized = _normalize(text)
    return any(_normalize(phrase) in normalized for phrase in phrases)


def _find_program(vault: OpportunityVault, text: str):
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


def _latest_application(vault: OpportunityVault):
    return vault.applications[-1] if vault.applications else None


def _latest_discovery(vault: OpportunityVault):
    if not vault.discoveries:
        return None
    return sorted(vault.discoveries, key=lambda item: item.created_at, reverse=True)[0]


def _source_link(title: str, url: str) -> str:
    safe_title = str(title or "Fuente original").replace("[", "(").replace("]", ")")
    return f"[{safe_title}]({url})" if url else safe_title


class OpportunityChatController:
    """Chat-first control surface for discoveries, programs and applications."""

    def __init__(self, autopilot: OpportunityAutopilot) -> None:
        self.autopilot = autopilot

    def handle(self, state: PatientState, text: str) -> OpportunityChatResult | None:
        normalized = _normalize(text)
        if not normalized:
            return None
        vault = self.autopilot.load(state.profile.id)

        if _mentions(
            text,
            (
                "que hay nuevo sobre mi salud",
                "qué hay nuevo sobre mi salud",
                "descubrimientos de salud",
                "investigacion nueva sobre",
                "investigación nueva sobre",
                "novedades sobre mi salud",
                "what is new about my health",
                "new research about",
                "health discoveries",
            ),
        ):
            snapshot = opportunity_snapshot(vault)
            new_items = [item for item in vault.discoveries if item.status == DiscoveryStatus.NEW]
            if not new_items:
                content = (
                    "No tengo ningún descubrimiento nuevo que haya superado el filtro de relevancia. "
                    "Sigo conservando tus temas autorizados sin convertir cada publicación en una alerta."
                )
            else:
                item = sorted(new_items, key=lambda value: value.created_at, reverse=True)[0]
                scope = "tu salud" if item.relation == "self" else f"tu contexto familiar ({item.subject_label})"
                content = (
                    f"Encontré algo que pasó el filtro de relevancia para {scope}: **{item.title}**. "
                    f"{item.summary[:700]} "
                    f"Fuente original: {_source_link(item.source.publisher or item.source.title, item.source.url)}. "
                    "Esto no cambia por sí solo ningún tratamiento. ¿Quieres que lo compare con lo que tienes registrado?"
                )
            return OpportunityChatResult(
                content=content,
                action="show_discoveries",
                metadata=snapshot,
            )

        if _mentions(
            text,
            (
                "comparalo con mi medicacion",
                "compáralo con mi medicación",
                "comparalo con lo que tomo",
                "compáralo con lo que tomo",
                "compara esto con mi tratamiento",
                "compare it with my medication",
                "compare this with my treatment",
            ),
        ):
            discovery = _latest_discovery(vault)
            if discovery is None:
                return OpportunityChatResult(
                    content=(
                        "No tengo una novedad científica guardada para comparar todavía. "
                        "Puedes pedirme que revise novedades sobre una condición concreta."
                    ),
                    action="comparison_source_needed",
                )
            comparison = therapeutic_comparison(state, discovery)
            medications = comparison["current_medications"]
            current = "; ".join(
                " ".join(part for part in (item["name"], item["strength"], item["schedule"]) if part)
                for item in medications
            ) or "No tengo medicación activa confirmada en el registro."
            benefits = discovery.potential_benefits or [
                "La fuente encontrada no trae todavía un beneficio estructurado que pueda atribuir con seguridad."
            ]
            limitations = discovery.limitations or [
                "La aplicabilidad individual necesita revisar la fuente completa y el contexto clínico con un profesional."
            ]
            content = (
                f"La comparé con tu registro actual. **Tratamiento registrado:** {current}. "
                f"**Lo que la fuente reporta como posible beneficio:** {'; '.join(benefits[:4])}. "
                f"**Límites/precauciones:** {'; '.join(limitations[:4])}. "
                f"Fuente original: {_source_link(discovery.source.publisher or discovery.source.title, discovery.source.url)}. "
                "Esto organiza evidencia para conversar con tu profesional; no demuestra que la nueva opción sea mejor para ti "
                "y no inicia, suspende, sustituye ni cambia dosis."
            )
            return OpportunityChatResult(
                content=content,
                action="therapeutic_comparison",
                resource_id=discovery.id,
                metadata={"comparison": comparison},
            )

        if _mentions(
            text,
            (
                "ayuda economica",
                "ayuda económica",
                "beneficios disponibles",
                "beneficio estatal",
                "programas de ayuda",
                "recursos estatales",
                "recursos comunitarios",
                "fundaciones para",
                "community resources",
                "financial assistance",
                "government benefits",
            ),
        ):
            if not vault.programs:
                return OpportunityChatResult(
                    content=(
                        "Todavía no tengo un programa oficial verificado guardado para tu contexto. "
                        "Puedo iniciar una búsqueda acotada por enfermedad, relación familiar y ubicación; "
                        "las búsquedas web con Gemini se ejecutan sólo cuando están autorizadas para controlar el gasto."
                    ),
                    action="resource_refresh_available",
                )
            program = vault.programs[-1]
            content = (
                f"Tengo {len(vault.programs)} recurso(s) guardado(s). El más reciente es **{program.title}** "
                f"de {program.provider}. {program.benefit_summary} "
                f"Fuente: {_source_link(program.provider, program.url)}. "
                "Puedo revisar los requisitos contra tus datos y decirte exactamente qué falta, sin asumir elegibilidad."
            )
            return OpportunityChatResult(
                content=content,
                action="show_programs",
                resource_id=program.id,
            )

        if _mentions(
            text,
            (
                "completa el formulario",
                "completar formulario",
                "prepara la solicitud",
                "aplica a esa ayuda",
                "aplicar a esa ayuda",
                "fill the form",
                "prepare the application",
                "apply for that program",
            ),
        ):
            program = _find_program(vault, text)
            if program is None:
                return OpportunityChatResult(
                    content=(
                        "Necesito que me indiques cuál de las ayudas guardadas quieres preparar. "
                        "No voy a escoger ni enviar una solicitud sensible por mi cuenta."
                    ),
                    action="application_program_needed",
                )
            packet = self.autopilot.prepare_application(state, program.id)
            parts = [
                f"Preparé el borrador para **{program.title}**. Fuente: {_source_link(program.provider, program.url)}."
            ]
            if packet.missing_documents:
                parts.append("Documentos que faltan: " + ", ".join(packet.missing_documents) + ".")
            if packet.missing_fields:
                parts.append("Datos que necesitan confirmación o faltan: " + ", ".join(packet.missing_fields) + ".")
            if not packet.missing_documents and not packet.missing_fields:
                parts.append(
                    "La información disponible permite dejar el paquete prellenado. "
                    "Todavía necesito tu revisión explícita antes de cualquier envío externo."
                )
            return OpportunityChatResult(
                content=" ".join(parts),
                action="application_prefilled",
                resource_id=packet.id,
                metadata={"application_status": str(packet.status)},
            )

        if _mentions(
            text,
            (
                "que documento falta para la solicitud",
                "qué documento falta para la solicitud",
                "que documentos faltan para aplicar",
                "qué documentos faltan para aplicar",
                "que falta para la solicitud",
                "qué falta para la solicitud",
                "missing document for the application",
                "what is missing for the application",
            ),
        ):
            packet = _latest_application(vault)
            if packet is None:
                return OpportunityChatResult(
                    content="No tengo una solicitud activa para revisar documentos pendientes.",
                    action="no_active_application",
                )
            missing = [*packet.missing_documents, *packet.missing_fields]
            content = (
                "No falta nada en el borrador según los requisitos estructurados; queda tu revisión antes del envío."
                if not missing
                else "Para continuar me falta: " + ", ".join(missing) + ". Puedes subir los documentos aquí."
            )
            return OpportunityChatResult(
                content=content,
                action="show_application_missing_items",
                resource_id=packet.id,
                metadata={"missing": missing, "status": str(packet.status)},
            )

        if _mentions(
            text,
            (
                "busca ayudas para",
                "buscar ayudas para",
                "busca recursos para",
                "buscar recursos para",
                "find assistance for",
                "find programs for",
            ),
        ):
            return OpportunityChatResult(
                content=(
                    "Puedo buscar recursos actuales usando sólo fuentes oficiales o claramente identificadas. "
                    "La búsqueda se limita a tus temas autorizados y a la ubicación que compartas, "
                    "y no se ejecuta como un ciclo permanente."
                ),
                action="request_resource_refresh",
                metadata={
                    "event": AutopilotEvent(
                        patient_id=state.profile.id,
                        event_type="manual.resource_refresh",
                    ).model_dump(mode="json")
                },
            )

        if _mentions(
            text,
            (
                "no me avises sobre",
                "no busques mas sobre",
                "no busques más sobre",
                "deja de vigilar",
                "stop watching",
                "stop notifying me about",
            ),
        ):
            topic_matches = [
                item for item in vault.watch_topics if _normalize(item.condition) in normalized
            ]
            if len(topic_matches) != 1:
                return OpportunityChatResult(
                    content=(
                        "Puedo detener ese seguimiento. Dime el tema concreto que quieres desactivar "
                        "(por ejemplo, hipertensión, autismo o artritis) para no apagar otro seguimiento por error."
                    ),
                    action="watch_topic_needed",
                )
            topic_matches[0].enabled = False
            self.autopilot.store.save(vault)
            return OpportunityChatResult(
                content=f"Listo. Dejé de vigilar novedades sobre {topic_matches[0].condition}.",
                action="watch_topic_disabled",
                resource_id=topic_matches[0].id,
            )

        return None
