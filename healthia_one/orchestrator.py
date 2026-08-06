from __future__ import annotations

from healthia_one.models import (
    AgentStep,
    ChatMessage,
    ChatResponse,
    HealthMission,
    MissionStatus,
    PatientState,
    RiskLevel,
)
from healthia_one.safety import assess_text


def _plan(*steps: tuple[str, str, str]) -> list[AgentStep]:
    return [AgentStep(agent=agent, action=action, reason=reason, status="completed") for agent, action, reason in steps]


def respond(state: PatientState, patient_text: str) -> ChatResponse:
    safety = assess_text(patient_text)
    if safety.must_stop_normal_flow:
        plan = _plan(
            ("SENTINEL", "Detectar lenguaje urgente", "Seguridad inmediata"),
            ("BASTION", "Bloquear flujo rutinario", "No retrasar atención"),
            ("KIRA", "Escalar al humano", "La IA no gestiona emergencias"),
        )
        message = ChatMessage(
            role="assistant",
            author="KIRA Health",
            content=safety.message,
            risk_level=RiskLevel.URGENT,
            agent_plan=plan,
        )
        return ChatResponse(message=message)

    lower = patient_text.lower()
    profile = state.profile
    mission: HealthMission | None = None

    if any(word in lower for word in ("resultado", "laboratorio", "analítica", "análisis")):
        plan = _plan(
            ("LUMEN", "Localizar y explicar resultados", "Lenguaje comprensible"),
            ("HISTORIA", "Comparar con la línea de tiempo", "Evitar interpretación aislada"),
            ("KIRA", "Preparar preguntas y seguimiento", "Continuidad"),
        )
        latest = state.results[-1] if state.results else None
        if latest:
            content = latest.explanation or (
                f"Encontré **{latest.filename}**, pero todavía está pendiente de explicación. "
                "Ábrelo desde Resultados o vuelve a cargarlo en JSON/CSV/TXT para una lectura estructurada."
            )
            evidence = [latest.id]
        else:
            content = (
                "No veo resultados cargados todavía. Puedes adjuntar un JSON, CSV, TXT, PDF o imagen. "
                "Los formatos estructurados se explican localmente; PDF e imágenes esperan al agente multimodal."
            )
            evidence = []
        mission = HealthMission(
            title="Comprender resultado de salud",
            mission_type="result_explanation",
            next_action="Esperar archivo o confirmar comprensión",
            evidence_ids=evidence,
            agent_plan=plan,
        )
    elif any(word in lower for word in ("peso", "engord", "adelgaz")):
        plan = _plan(
            ("HISTORIA", "Revisar tendencia de peso", "Contexto longitudinal"),
            ("SENTINEL", "Comprobar síntomas de prioridad", "Seguridad"),
            ("VITA", "Explorar hábitos y barreras", "Plan realista"),
        )
        latest = state.weights[-1].weight_kg if state.weights else None
        content = (
            f"Tu último peso registrado es **{latest:.1f} kg**. " if latest is not None else "No veo un peso registrado todavía. "
        ) + (
            "Para entender un cambio necesito saber cuándo te pesaste, si usaste la misma balanza y "
            "si hubo cambios de alimentación, actividad, hinchazón o falta de aire."
        )
        mission = HealthMission(
            title="Entender cambio de peso",
            mission_type="weight_followup",
            status=MissionStatus.WAITING_PATIENT,
            next_action="Registrar peso y responder preguntas de contexto",
            agent_plan=plan,
        )
    elif any(word in lower for word in ("presión", "tension", "tensión")):
        plan = _plan(
            ("SENTINEL", "Revisar presión y síntomas", "Umbrales de seguridad"),
            ("NAVIGATOR", "Guiar técnica de medición", "Calidad del dato"),
            ("KIRA", "Mantener seguimiento", "Serie longitudinal"),
        )
        content = (
            "Registra la presión después de cinco minutos de reposo, espalda y brazo apoyados, "
            "y toma dos mediciones separadas por un minuto. Si aparece dolor de pecho, falta de aire, "
            "debilidad de un lado o dificultad para hablar, busca atención urgente."
        )
        mission = HealthMission(
            title="Seguimiento de presión arterial",
            mission_type="blood_pressure",
            status=MissionStatus.WAITING_PATIENT,
            next_action="Recibir dos mediciones y síntomas asociados",
            agent_plan=plan,
        )
    elif any(word in lower for word in ("actividad", "caminar", "ejercicio", "pasos")):
        plan = _plan(
            ("VITA", "Revisar actividad y barreras", "Plan sostenible"),
            ("HISTORIA", "Comparar con registros previos", "Tendencia"),
            ("KIRA", "Proponer microobjetivo", "Evitar recomendaciones genéricas"),
        )
        recent = state.activity[-3:]
        content = (
            "Veo pocos registros de actividad. " if len(recent) < 3 else
            f"Tus últimos registros promedian **{sum(item.steps for item in recent)/len(recent):.0f} pasos**. "
        ) + "¿Qué barrera pesa más ahora: dolor, cansancio, tiempo, clima o ánimo?"
        mission = HealthMission(
            title="Plan de actividad realista",
            mission_type="activity_plan",
            status=MissionStatus.WAITING_PATIENT,
            next_action="Identificar barrera y acordar una meta pequeña",
            agent_plan=plan,
        )
    else:
        plan = _plan(
            ("HISTORIA", "Recuperar contexto autorizado", "No empezar desde cero"),
            ("SENTINEL", "Comprobar señales de prioridad", "Seguridad"),
            ("KIRA", "Elegir el equipo mínimo", "Evitar agentes innecesarios"),
        )
        content = (
            f"Estoy contigo, {profile.display_name.split()[0]}. Puedo revisar tu historia autorizada, "
            "registrar mediciones, explicar resultados, preparar una consulta o mantener una misión "
            "de seguimiento. Cuéntame qué cambió, desde cuándo y qué te preocupa más."
        )

    if mission:
        state.missions.append(mission)
    message = ChatMessage(
        role="assistant",
        author="KIRA Health",
        content=content,
        risk_level=RiskLevel.INFO,
        mission_id=mission.id if mission else None,
        agent_plan=plan,
    )
    return ChatResponse(message=message, mission=mission)
