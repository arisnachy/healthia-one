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
    events: list[dict[str, Any]] = []

    def add(event_id: str, event_type: str, occurred_at: datetime, title: str, detail: str, source: str) -> None:
        events.append(
            {
                "id": event_id,
                "type": event_type,
                "occurred_at": occurred_at.isoformat(),
                "title": title,
                "detail": detail,
                "source": source,
            }
        )

    for item in state.vitals:
        bp = f"{item.systolic or '—'}/{item.diastolic or '—'}"
        add(item.id, "vital", item.measured_at, f"Presión {bp}", f"Pulso {item.pulse or '—'}", item.source.source_type)
    for item in state.weights:
        add(item.id, "weight", item.measured_at, f"Peso {item.weight_kg:.1f} kg", item.note or "Registro del paciente", item.source.source_type)
    for item in state.activity:
        add(item.id, "activity", item.measured_at, f"Actividad: {item.steps} pasos", f"{item.active_minutes} minutos activos", "patient_entry")
    for item in state.results:
        add(item.id, "result", item.uploaded_at, item.panel, f"{item.filename} · {item.status}", item.source.source_type)
    for item in state.documents:
        add(item.id, "document", item.uploaded_at, item.title, f"{item.category} · {item.status}", item.source.source_type)
    for item in state.medication_checkins:
        plan = next((plan for plan in state.medication_plans if plan.id == item.medication_id), None)
        add(item.id, "medication", item.recorded_at, f"Tratamiento: {plan.name if plan else 'medicamento'}", item.status, item.source.source_type)
    for item in state.appointments:
        add(item.id, "appointment", item.scheduled_at, item.title, f"{item.specialty} · {item.status}", item.source.source_type)
    for item in state.missions:
        add(item.id, "mission", item.updated_at, item.title, f"{item.status} · {item.next_action}", "healthia_mission")
    return sorted(events, key=lambda item: item["occurred_at"], reverse=True)


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
    family_clusters = []
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
                        AgentStep(agent="HISTORIA", action="Resumir cambios recientes", reason="Continuidad longitudinal"),
                        AgentStep(agent="KIRA", action="Solicitar confirmación", reason="Control del paciente"),
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
                        AgentStep(agent="MEDSAFE", action="Detectar omisión reportada", reason="Seguridad del tratamiento"),
                        AgentStep(agent="SENTINEL", action="Bloquear ajuste de dosis", reason="Requiere criterio profesional"),
                        AgentStep(agent="KIRA", action="Recoger contexto", reason="Próximo paso seguro"),
                    ],
                )
            )
    return findings
