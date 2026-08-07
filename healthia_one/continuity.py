from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from healthia_one.models import AgentStep, PatientState, ProactiveFinding, RiskLevel


CONDITION_PACKS: dict[str, dict[str, Any]] = {
    "hypertension": {
        "label": "Hipertensión",
        "signals": ["presión arterial", "síntomas de alarma", "adherencia reportada", "actividad", "peso"],
        "questions": [
            "¿Las mediciones se tomaron con técnica comparable?",
            "¿Hubo dolor de pecho, falta de aire, debilidad o dificultad para hablar?",
            "¿Se omitió alguna toma del tratamiento registrado?",
        ],
    },
    "weight_management": {
        "label": "Seguimiento de peso",
        "signals": ["peso", "actividad", "alimentación reportada", "hinchazón", "sueño"],
        "questions": [
            "¿Se utilizó la misma balanza y horario?",
            "¿Cambió la actividad, alimentación, sueño o medicación?",
            "¿Existe hinchazón, falta de aire u otro síntoma nuevo?",
        ],
    },
}


def condition_pack_summary(state: PatientState) -> list[dict[str, Any]]:
    output = []
    for key in state.profile.care_plan.conditions:
        pack = CONDITION_PACKS.get(key)
        if pack:
            output.append({"key": key, **pack})
    return output


def medication_summary(state: PatientState) -> dict[str, Any]:
    active = [item for item in state.medication_plans if item.active]
    recent = sorted(state.medication_checkins, key=lambda item: item.recorded_at)[-14:]
    counts = {"taken": 0, "late": 0, "skipped": 0, "unknown": 0}
    for event in recent:
        counts[event.status] += 1
    known = counts["taken"] + counts["late"] + counts["skipped"]
    adherence = round((counts["taken"] + counts["late"]) / known * 100, 1) if known else None
    return {
        "active_plans": [item.model_dump(mode="json") for item in active],
        "recent_checkins": [item.model_dump(mode="json") for item in recent],
        "counts": counts,
        "reported_adherence_percent": adherence,
        "truth_boundary": "Registro informado por el paciente; no demuestra absorción ni autoriza cambios de tratamiento.",
    }


def build_timeline(state: PatientState) -> list[dict[str, Any]]:
    """Build the patient timeline using clinical event time, not upload time.

    New longitudinal facts flow through `twin_events`. Legacy collections remain as
    a compatibility source only when the same entity has not already been reduced
    into the Twin. Timeline rows expose both the append-only event id and the linked
    clinical entity id so callers can trace an event back to the original result,
    measurement or interview without collapsing event sourcing semantics.
    """
    events: list[dict[str, Any]] = []
    twin_entity_keys: set[tuple[str, str]] = set()

    def add(
        event_id: str,
        event_type: str,
        occurred_at: datetime,
        title: str,
        detail: str,
        source: str,
        *,
        entity_id: str | None = None,
        recorded_at: datetime | None = None,
        certainty: str = "unknown",
        verification_status: str = "unverified",
    ) -> None:
        events.append(
            {
                "id": event_id,
                "entity_id": entity_id or event_id,
                "type": event_type,
                "occurred_at": occurred_at.isoformat(),
                "recorded_at": (recorded_at or occurred_at).isoformat(),
                "title": title,
                "detail": detail,
                "source": source,
                "certainty": certainty,
                "verification_status": verification_status,
            }
        )

    for event in state.twin_events:
        twin_entity_keys.add((event.entity_type, event.entity_id))
        add(
            event.id,
            event.entity_type,
            event.event_at,
            event.title or event.entity_type.replace("_", " ").title(),
            event.summary,
            event.source.source_type,
            entity_id=event.entity_id,
            recorded_at=event.recorded_at,
            certainty=event.certainty,
            verification_status=event.verification_status,
        )

    for item in state.vitals:
        if ("vital", item.id) in twin_entity_keys:
            continue
        bp = f"{item.systolic or '—'}/{item.diastolic or '—'}"
        add(item.id, "vital", item.measured_at, f"Presión {bp}", f"Pulso {item.pulse or '—'}", item.source.source_type)
    for item in state.weights:
        if ("weight", item.id) in twin_entity_keys:
            continue
        add(item.id, "weight", item.measured_at, f"Peso {item.weight_kg:.1f} kg", item.note or "Registro del paciente", item.source.source_type)
    for item in state.activity:
        if ("activity", item.id) in twin_entity_keys:
            continue
        add(item.id, "activity", item.measured_at, f"Actividad: {item.steps} pasos", f"{item.active_minutes} minutos activos", item.source.source_type)
    for item in state.results:
        if ("result", item.id) in twin_entity_keys:
            continue
        occurred_at = (
            datetime.combine(item.exam_date, datetime.min.time(), tzinfo=timezone.utc)
            if item.exam_date
            else item.uploaded_at
        )
        add(item.id, "result", occurred_at, item.panel, f"{item.filename} · {item.status}", item.source.source_type, recorded_at=item.uploaded_at)
    for item in state.documents:
        add(item.id, "document", item.uploaded_at, item.title, f"{item.category} · {item.status}", item.source.source_type)
    for item in state.medication_checkins:
        if ("medication_checkin", item.id) in twin_entity_keys:
            continue
        plan = next((plan for plan in state.medication_plans if plan.id == item.medication_id), None)
        add(item.id, "medication", item.recorded_at, f"Tratamiento: {plan.name if plan else 'medicamento'}", item.status, item.source.source_type)
    for item in state.appointments:
        add(item.id, "appointment", item.scheduled_at, item.title, f"{item.specialty} · {item.status}", item.source.source_type)
    for item in state.missions:
        add(item.id, "mission", item.updated_at, item.title, f"{item.status} · {item.next_action}", "healthia_mission")
    return sorted(events, key=lambda item: (item["occurred_at"], item["recorded_at"]), reverse=True)


def consultation_brief(state: PatientState, appointment_id: str | None = None) -> dict[str, Any]:
    appointment = None
    if appointment_id:
        appointment = next((item for item in state.appointments if item.id == appointment_id), None)
    if appointment is None:
        scheduled = [item for item in state.appointments if item.status == "scheduled"]
        appointment = min(scheduled, key=lambda item: item.scheduled_at) if scheduled else None

    latest_vital = state.vitals[-1] if state.vitals else None
    latest_weight = state.weights[-1] if state.weights else None
    recent_results = state.results[-3:]
    active_missions = [item for item in state.missions if item.status not in {"completed", "cancelled"}]
    from healthia_one.family import family_summary

    family_clusters = [item["condition"] for item in family_summary(state)["clusters"]]
    questions = list(appointment.questions if appointment else [])
    if latest_vital:
        questions.append("¿Cómo interpretar la tendencia reciente de presión y cuál es el objetivo acordado?")
    if recent_results:
        questions.append("¿Qué resultados requieren seguimiento y en qué plazo?")
    if family_clusters:
        questions.append("¿Los antecedentes familiares cambian alguna recomendación preventiva para mí?")

    return {
        "patient": state.profile.display_name,
        "appointment": appointment.model_dump(mode="json") if appointment else None,
        "confirmed_conditions": state.profile.confirmed_conditions,
        "allergies": state.profile.allergies,
        "active_medications": [item.model_dump(mode="json") for item in state.medication_plans if item.active],
        "latest_vital": latest_vital.model_dump(mode="json") if latest_vital else None,
        "latest_weight": latest_weight.model_dump(mode="json") if latest_weight else None,
        "recent_results": [item.model_dump(mode="json") for item in recent_results],
        "active_missions": [item.model_dump(mode="json") for item in active_missions[-5:]],
        "family_context": family_clusters,
        "questions": list(dict.fromkeys(questions)),
        "required_documents": appointment.required_documents if appointment else [],
        "truth_boundary": "Resumen preparado con datos autorizados; debe ser revisado por el paciente y el profesional.",
    }


def evaluate_continuity(state: PatientState, now: datetime | None = None) -> list[ProactiveFinding]:
    """Generate findings only when explicitly requested or a safety channel allows it.

    The default product does not push these into chat: `PatientConsent.proactive_enabled`
    is false and the runtime polling loop is disabled. The function remains useful
    for an explicit patient request such as "revisa lo pendiente".
    """
    now = now or datetime.now(timezone.utc)
    findings: list[ProactiveFinding] = []
    if "appointments" in state.profile.consented_signal_types:
        upcoming = [
            item
            for item in state.appointments
            if item.status == "scheduled" and now <= item.scheduled_at <= now + timedelta(hours=72)
        ]
        for appointment in upcoming:
            findings.append(
                ProactiveFinding(
                    key=f"appointment_prep:{appointment.id}",
                    title="Tu consulta está cerca",
                    risk_level=RiskLevel.INFO,
                    summary=f"{appointment.title} está programada para {appointment.scheduled_at.isoformat()}.",
                    why_it_matters="Preparar cambios, resultados, tratamiento y preguntas ayuda a aprovechar la consulta.",
                    next_action="Revisa el resumen de consulta y confirma si falta algún documento o pregunta.",
                    evidence_ids=[appointment.id],
                    agent_plan=[
                        AgentStep(agent="ADVOCATE", action="Preparar resumen del paciente", reason="Consulta próxima"),
                        AgentStep(agent="ARCHIVUM", action="Verificar documentos", reason="Evitar información faltante"),
                    ],
                )
            )
    if "medications" in state.profile.consented_signal_types:
        skipped = [item for item in state.medication_checkins[-7:] if item.status == "skipped"]
        if skipped:
            findings.append(
                ProactiveFinding(
                    key=f"medication_skipped:{skipped[-1].id}",
                    title="Toma omitida registrada",
                    risk_level=RiskLevel.WATCH,
                    summary="El registro reciente incluye una toma marcada como omitida.",
                    why_it_matters="La omisión puede necesitar contexto, pero HealthIA no indica duplicar dosis ni cambiar el esquema.",
                    next_action="Indica qué ocurrió y consulta las instrucciones de tu profesional o farmacéutico antes de compensar una dosis.",
                    evidence_ids=[item.id for item in skipped],
                    agent_plan=[
                        AgentStep(agent="MEDSAFE", action="Revisar la omisión reportada", reason="Seguridad del tratamiento"),
                        AgentStep(agent="SENTINEL", action="Mantener el límite de no ajustar dosis", reason="Requiere criterio profesional"),
                    ],
                )
            )
    return findings
