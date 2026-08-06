from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean

from healthia_one.family import evaluate_family_history
from healthia_one.models import AgentStep, PatientState, ProactiveFinding, RiskLevel
from healthia_one.safety import assess_vital


def _days_since(value: datetime, now: datetime) -> float:
    return max((now - value).total_seconds() / 86400, 0)


def evaluate_state(state: PatientState, now: datetime | None = None) -> list[ProactiveFinding]:
    now = now or datetime.now(timezone.utc)
    findings: list[ProactiveFinding] = []
    plan = state.profile.care_plan

    if "weight" in state.profile.consented_signal_types:
        if not state.weights or _days_since(state.weights[-1].measured_at, now) >= plan.weight_due_days:
            findings.append(
                ProactiveFinding(
                    key=f"missing_weight:{now.date().isoformat()}",
                    title="Registro de peso pendiente",
                    risk_level=RiskLevel.WATCH,
                    summary="No veo un peso reciente dentro del intervalo acordado.",
                    why_it_matters=(
                        "El peso ayuda a interpretar tendencias de presión, actividad y objetivos "
                        "del plan; una medición aislada no diagnostica nada."
                    ),
                    next_action="Registra tu peso cuando puedas y dime si hubo cambios en alimentación, hinchazón o actividad.",
                    evidence_ids=[state.weights[-1].id] if state.weights else [],
                    agent_plan=[
                        AgentStep(agent="SENTINEL", action="Detectar brecha de medición", reason="Plan de peso activo"),
                        AgentStep(agent="VITA", action="Preguntar barreras y contexto", reason="Evitar un recordatorio mecánico"),
                        AgentStep(agent="KIRA", action="Mantener la misión abierta", reason="Esperar dato del paciente"),
                    ],
                )
            )

        if len(state.weights) >= 2:
            ordered = sorted(state.weights, key=lambda item: item.measured_at)
            latest = ordered[-1]
            comparison = next(
                (item for item in reversed(ordered[:-1]) if latest.measured_at - item.measured_at >= timedelta(days=2)),
                ordered[0],
            )
            delta = latest.weight_kg - comparison.weight_kg
            if delta >= plan.weight_change_watch_kg:
                findings.append(
                    ProactiveFinding(
                        key=f"weight_gain:{latest.id}:{comparison.id}",
                        title="Cambio de peso que merece contexto",
                        risk_level=RiskLevel.WATCH,
                        summary=f"El peso aumentó {delta:.1f} kg entre dos registros.",
                        why_it_matters=(
                            "El cambio puede tener explicaciones cotidianas, de medición o de salud. "
                            "HealthIA necesita contexto antes de orientar."
                        ),
                        next_action=(
                            "¿Cambió tu alimentación, actividad o horario de medición? ¿Notas hinchazón, "
                            "falta de aire o algún síntoma nuevo?"
                        ),
                        evidence_ids=[comparison.id, latest.id],
                        agent_plan=[
                            AgentStep(agent="HISTORIA", action="Comparar registros", reason="Tendencia longitudinal"),
                            AgentStep(agent="SENTINEL", action="Buscar síntomas de prioridad", reason="Cambio material"),
                            AgentStep(agent="VITA", action="Explorar hábitos y barreras", reason="Contexto modificable"),
                        ],
                    )
                )

    if "vitals" in state.profile.consented_signal_types:
        if not state.vitals or _days_since(state.vitals[-1].measured_at, now) >= plan.blood_pressure_due_days:
            findings.append(
                ProactiveFinding(
                    key=f"missing_bp:{now.date().isoformat()}",
                    title="Presión arterial pendiente",
                    risk_level=RiskLevel.WATCH,
                    summary="No veo una presión reciente dentro del seguimiento acordado.",
                    why_it_matters="Una serie consistente es más útil que una medición aislada.",
                    next_action="Cuando estés en reposo, registra dos mediciones separadas por un minuto.",
                    evidence_ids=[],
                    agent_plan=[
                        AgentStep(agent="SENTINEL", action="Detectar brecha", reason="Hipertensión confirmada"),
                        AgentStep(agent="NAVIGATOR", action="Preparar registro guiado", reason="Mejorar técnica"),
                    ],
                )
            )
        elif state.vitals:
            latest = state.vitals[-1]
            decision = assess_vital(latest)
            if decision.level in {RiskLevel.PRIORITY, RiskLevel.URGENT}:
                findings.append(
                    ProactiveFinding(
                        key=f"vital_alert:{latest.id}",
                        title="Medición que necesita atención",
                        risk_level=decision.level,
                        summary=decision.message,
                        why_it_matters="La alerta proviene de un umbral determinista, no de un diagnóstico del modelo.",
                        next_action="Sigue la recomendación de seguridad mostrada y comparte el registro con un profesional.",
                        evidence_ids=[latest.id],
                        agent_plan=[
                            AgentStep(agent="SENTINEL", action="Aplicar umbral clínico", reason="Seguridad inmediata"),
                            AgentStep(agent="BASTION", action="Bloquear orientación rutinaria", reason="Prioridad clínica"),
                            AgentStep(agent="KIRA", action="Escalar al humano", reason="No retrasar atención"),
                        ],
                    )
                )

    if "activity" in state.profile.consented_signal_types and len(state.activity) >= 3:
        recent = sorted(state.activity, key=lambda item: item.measured_at)[-3:]
        average_steps = mean(item.steps for item in recent)
        if average_steps < plan.activity_goal_steps * 0.5:
            findings.append(
                ProactiveFinding(
                    key=f"low_activity:{recent[-1].measured_at.date().isoformat()}",
                    title="Actividad menor de la habitual",
                    risk_level=RiskLevel.INFO,
                    summary=f"El promedio de los últimos registros es {average_steps:.0f} pasos.",
                    why_it_matters="El objetivo sirve para conversar sobre barreras, no para juzgarte.",
                    next_action="¿Hubo dolor, cansancio, clima, trabajo u otra barrera? Podemos ajustar una meta pequeña y realista.",
                    evidence_ids=[item.id for item in recent],
                    agent_plan=[
                        AgentStep(agent="VITA", action="Explorar barreras", reason="Plan sostenible"),
                        AgentStep(agent="KIRA", action="Proponer microobjetivo", reason="Evitar recomendaciones genéricas"),
                    ],
                )
            )

    if "results" in state.profile.consented_signal_types:
        pending = [result for result in state.results if not result.explained]
        if pending:
            latest = pending[-1]
            findings.append(
                ProactiveFinding(
                    key=f"unreviewed_result:{latest.id}",
                    title="Tienes un resultado pendiente de explicación",
                    risk_level=RiskLevel.WATCH,
                    summary=f"El archivo {latest.filename} todavía no ha sido explicado.",
                    why_it_matters="Los resultados deben interpretarse con unidades, referencias, historia y síntomas.",
                    next_action="Abre el resultado para recibir una explicación y preparar preguntas para tu consulta.",
                    evidence_ids=[latest.id],
                    agent_plan=[
                        AgentStep(agent="LUMEN", action="Explicar el resultado", reason="Lenguaje humano"),
                        AgentStep(agent="HISTORIA", action="Comparar con contexto", reason="Evitar lectura aislada"),
                        AgentStep(agent="KIRA", action="Crear misión de revisión", reason="Cerrar la brecha"),
                    ],
                )
            )

    findings.extend(evaluate_family_history(state))
    return findings
