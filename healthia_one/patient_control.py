from __future__ import annotations

from healthia_one.models import AgentStep, ChatMessage, ChatResponse, HealthMission, PatientState, RiskLevel


CONTROL_TERMS = (
    "privacidad",
    "permiso",
    "permisos",
    "consentimiento",
    "vigilar",
    "monitorear",
    "alertas",
    "silencio",
    "silenciar",
    "pausar",
    "auditoría",
    "auditoria",
    "exportar",
    "descargar mis datos",
    "mis datos",
)


def maybe_control_response(state: PatientState, patient_text: str) -> ChatResponse | None:
    lower = patient_text.lower()
    if not any(term in lower for term in CONTROL_TERMS):
        return None
    consent = state.consent
    plan = [
        AgentStep(agent="BASTION", action="Revisar permisos y límites", reason="Control del paciente", status="completed"),
        AgentStep(agent="ECHO", action="Resumir el registro auditable", reason="Transparencia", status="completed"),
        AgentStep(agent="KIRA", action="Presentar acciones reversibles", reason="Autonomía del paciente", status="completed"),
    ]
    signals = ", ".join(consent.signal_types) if consent.signal_types else "ninguna"
    snooze = consent.snoozed_until.isoformat() if consent.snoozed_until else "no activa"
    content = (
        "### Tú controlas HealthIA\n\n"
        f"**Seguimiento proactivo:** {'activo' if consent.proactive_enabled else 'pausado'}.\n\n"
        f"**Señales autorizadas:** {signals}.\n\n"
        f"**Horario de silencio:** {consent.quiet_hours_start}–{consent.quiet_hours_end}.\n\n"
        f"**Pausa temporal:** {snooze}.\n\n"
        f"**Registro auditable:** {len(state.audit_events)} eventos.\n\n"
        "Desde Permisos y privacidad puedes cambiar señales, pausar intervenciones, revisar la auditoría "
        "y exportar tus datos estructurados. Las alertas urgentes deterministas solo atraviesan el silencio "
        "cuando tú mantienes autorizado ese límite de seguridad."
    )
    mission = HealthMission(
        title="Revisar control y privacidad",
        mission_type="patient_control",
        next_action="Confirmar permisos, horario de silencio o exportación",
        evidence_ids=[item.id for item in state.audit_events[-5:]],
        agent_plan=plan,
    )
    state.missions.append(mission)
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="KIRA Health",
            content=content,
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            agent_plan=plan,
            metadata={"action_target": "control", "mission_type": mission.mission_type},
        ),
        mission=mission,
    )
