from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from healthia_one.continuity import consultation_brief
from healthia_one.models import (
    AgentStep,
    AgenticEvent,
    HealthMission,
    MissionArtifact,
    MissionStatus,
    PatientState,
    RiskLevel,
    VitalRecord,
)
from healthia_one.safety import assess_vital


ALLOWED_ACTIONS = {
    "open_repeat_measurement",
    "close_repeat_measurement",
    "escalate_professional_review",
    "prepare_consultation_packet",
    "no_action",
}


@dataclass(frozen=True)
class MissionDecision:
    action: str
    reason: str
    evidence_ids: tuple[str, ...] = ()
    risk_level: RiskLevel = RiskLevel.INFO

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "evidence_ids": list(self.evidence_ids),
            "risk_level": self.risk_level.value,
        }


@dataclass(frozen=True)
class MissionOutcome:
    action: str
    mission_id: str | None
    artifact_ids: tuple[str, ...]
    status: str
    public_summary: str
    evidence_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "mission_id": self.mission_id,
            "artifact_ids": list(self.artifact_ids),
            "status": self.status,
            "public_summary": self.public_summary,
            "evidence_ids": list(self.evidence_ids),
        }


def _active_bp_mission(state: PatientState) -> HealthMission | None:
    return next(
        (
            mission
            for mission in reversed(state.missions)
            if mission.mission_type == "blood_pressure_followup"
            and mission.status not in {MissionStatus.COMPLETED, MissionStatus.CANCELLED}
        ),
        None,
    )


def _vital_for_event(state: PatientState, event: AgenticEvent) -> VitalRecord | None:
    if event.source_id:
        match = next((item for item in state.vitals if item.id == event.source_id), None)
        if match is not None:
            return match
    return state.vitals[-1] if state.vitals else None


def _appointment_packet_needed(state: PatientState, now: datetime) -> bool:
    upcoming = [
        item
        for item in state.appointments
        if item.status == "scheduled" and now <= item.scheduled_at <= now + timedelta(hours=72)
    ]
    if not upcoming:
        return False
    appointment_ids = {item.id for item in upcoming}
    for artifact in state.mission_artifacts:
        if artifact.artifact_type != "consultation_packet":
            continue
        if artifact.payload.get("appointment_id") in appointment_ids:
            return False
    return True


def deterministic_decision(state: PatientState, event: AgenticEvent) -> MissionDecision:
    """Choose the safe action for an event without a model.

    The deterministic path is the safety fallback and the CI oracle. A live ADK
    decision is accepted only when it selects one of these bounded actions.
    """

    if event.event_type in {"vital_recorded", "device_sync"}:
        vital = _vital_for_event(state, event)
        if vital is None:
            return MissionDecision("no_action", "No hay una medición utilizable para este evento.")
        decision = assess_vital(vital)
        active = _active_bp_mission(state)
        evidence = (vital.id,)
        if decision.must_stop_normal_flow:
            return MissionDecision(
                "escalate_professional_review",
                "La barrera determinista de seguridad exige detener el seguimiento rutinario.",
                evidence,
                decision.level,
            )
        if decision.level == RiskLevel.PRIORITY:
            if active is not None:
                return MissionDecision(
                    "escalate_professional_review",
                    "Una misión de repetición ya estaba abierta y la nueva medición continúa en prioridad.",
                    tuple(dict.fromkeys([*active.evidence_ids, vital.id])),
                    decision.level,
                )
            return MissionDecision(
                "open_repeat_measurement",
                "La medición activa un seguimiento acotado para obtener una segunda evidencia comparable.",
                evidence,
                decision.level,
            )
        if active is not None:
            return MissionDecision(
                "close_repeat_measurement",
                "Llegó la evidencia de repetición y ya no activa el umbral determinista de prioridad.",
                tuple(dict.fromkeys([*active.evidence_ids, vital.id])),
                decision.level,
            )
        return MissionDecision("no_action", "La medición no requiere una misión adicional.", evidence, decision.level)

    if event.event_type in {"scheduled_tick", "manual_demo"}:
        now = event.created_at.astimezone(timezone.utc)
        if _appointment_packet_needed(state, now):
            appointment = min(
                (
                    item
                    for item in state.appointments
                    if item.status == "scheduled" and now <= item.scheduled_at <= now + timedelta(hours=72)
                ),
                key=lambda item: item.scheduled_at,
            )
            return MissionDecision(
                "prepare_consultation_packet",
                "Hay una consulta próxima y todavía no existe un paquete de continuidad para ella.",
                (appointment.id,),
            )
        return MissionDecision("no_action", "No existe trabajo autónomo pendiente para este ciclo.")

    return MissionDecision("no_action", f"Evento no accionable: {event.event_type}.")


def validate_adk_decision(
    state: PatientState,
    event: AgenticEvent,
    candidate: dict[str, Any] | None,
) -> MissionDecision:
    """Constrain an ADK-selected action to the deterministic safety envelope."""

    oracle = deterministic_decision(state, event)
    if not candidate:
        return oracle
    action = str(candidate.get("action", "")).strip()
    if action not in ALLOWED_ACTIONS:
        return oracle
    # ADK may choose a less aggressive no-op, but it may never downgrade the
    # deterministic safety action or close a mission without closure evidence.
    if oracle.action in {"escalate_professional_review", "open_repeat_measurement"} and action != oracle.action:
        return oracle
    if oracle.action == "close_repeat_measurement" and action not in {"close_repeat_measurement", "escalate_professional_review"}:
        return oracle
    if oracle.action == "prepare_consultation_packet" and action not in {"prepare_consultation_packet", "no_action"}:
        return oracle
    reason = str(candidate.get("reason") or oracle.reason).strip()[:500]
    return MissionDecision(action, reason or oracle.reason, oracle.evidence_ids, oracle.risk_level)


def _reading_payload(state: PatientState, evidence_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    evidence = set(evidence_ids)
    return [
        {
            "id": item.id,
            "measured_at": item.measured_at.isoformat(),
            "systolic": item.systolic,
            "diastolic": item.diastolic,
            "pulse": item.pulse,
            "source": item.source.source_type,
        }
        for item in state.vitals
        if item.id in evidence
    ]


def apply_mission_action(
    state: PatientState,
    event: AgenticEvent,
    decision: MissionDecision,
) -> MissionOutcome:
    """Apply one bounded action and return evidence for a judge-visible trace."""

    now = datetime.now(timezone.utc)
    action = decision.action
    if action == "no_action":
        return MissionOutcome(action, None, (), "completed", decision.reason, decision.evidence_ids)

    if action == "open_repeat_measurement":
        existing = _active_bp_mission(state)
        if existing is None:
            mission = HealthMission(
                title="Confirmar una medición de presión",
                mission_type="blood_pressure_followup",
                status=MissionStatus.WAITING_PATIENT,
                risk_level=decision.risk_level,
                next_action="Registrar una nueva medición con técnica comparable y conservar cualquier síntoma reportado.",
                evidence_ids=list(decision.evidence_ids),
                agent_plan=[
                    AgentStep(agent="SENTINEL", action="Aplicar barrera determinista de seguridad", reason="No delegar seguridad al modelo", status="completed"),
                    AgentStep(agent="NAVIGATOR", action="Abrir seguimiento con condición de cierre", reason="Obtener nueva evidencia", status="completed"),
                ],
            )
            state.missions.append(mission)
        else:
            mission = existing
            mission.evidence_ids = list(dict.fromkeys([*mission.evidence_ids, *decision.evidence_ids]))
            mission.updated_at = now
        return MissionOutcome(
            action,
            mission.id,
            (),
            mission.status.value,
            "HealthIA abrió una misión de seguimiento y quedó esperando una nueva medición, sin cambiar tratamiento.",
            tuple(mission.evidence_ids),
        )

    if action == "close_repeat_measurement":
        mission = _active_bp_mission(state)
        if mission is None:
            return MissionOutcome("no_action", None, (), "completed", "No había una misión abierta que cerrar.")
        mission.evidence_ids = list(dict.fromkeys([*mission.evidence_ids, *decision.evidence_ids]))
        artifact = MissionArtifact(
            mission_id=mission.id,
            artifact_type="measurement_followup_summary",
            title="Resumen verificable del seguimiento de presión",
            source_evidence_ids=list(mission.evidence_ids),
            payload={
                "readings": _reading_payload(state, tuple(mission.evidence_ids)),
                "outcome": "repeat_measurement_received_without_priority_threshold",
                "safety": "No confirma diagnóstico ni modifica tratamiento.",
            },
        )
        state.mission_artifacts.append(artifact)
        mission.status = MissionStatus.COMPLETED
        mission.updated_at = now
        mission.next_action = "Misión cerrada: la repetición fue recibida y quedó documentada para continuidad."
        mission.closure_evidence = list(dict.fromkeys([*mission.closure_evidence, artifact.id, *mission.evidence_ids]))
        return MissionOutcome(
            action,
            mission.id,
            (artifact.id,),
            mission.status.value,
            "HealthIA recibió la segunda medición, creó un resumen verificable y cerró la misión automáticamente.",
            tuple(mission.evidence_ids),
        )

    if action == "escalate_professional_review":
        mission = _active_bp_mission(state)
        if mission is None:
            mission = HealthMission(
                title="Revisión profesional de una medición prioritaria",
                mission_type="blood_pressure_followup",
                status=MissionStatus.WAITING_PROFESSIONAL,
                risk_level=decision.risk_level,
                next_action="Seguir la recomendación de seguridad y compartir las mediciones con un profesional.",
                evidence_ids=list(decision.evidence_ids),
            )
            state.missions.append(mission)
        else:
            mission.status = MissionStatus.WAITING_PROFESSIONAL
            mission.risk_level = decision.risk_level
            mission.updated_at = now
            mission.next_action = "La repetición continúa requiriendo revisión profesional; no ajustar medicación desde HealthIA."
            mission.evidence_ids = list(dict.fromkeys([*mission.evidence_ids, *decision.evidence_ids]))
        artifact = MissionArtifact(
            mission_id=mission.id,
            artifact_type="professional_review_packet",
            title="Paquete para revisión profesional",
            source_evidence_ids=list(mission.evidence_ids),
            payload={
                "readings": _reading_payload(state, tuple(mission.evidence_ids)),
                "risk_level": mission.risk_level.value,
                "safety": "Escalamiento generado por reglas deterministas; HealthIA no prescribe ni cambia dosis.",
            },
        )
        state.mission_artifacts.append(artifact)
        return MissionOutcome(
            action,
            mission.id,
            (artifact.id,),
            mission.status.value,
            "HealthIA detuvo el flujo rutinario, preparó evidencia y dejó la misión en revisión profesional.",
            tuple(mission.evidence_ids),
        )

    if action == "prepare_consultation_packet":
        now = event.created_at.astimezone(timezone.utc)
        upcoming = [
            item
            for item in state.appointments
            if item.status == "scheduled" and now <= item.scheduled_at <= now + timedelta(hours=72)
        ]
        if not upcoming:
            return MissionOutcome("no_action", None, (), "completed", "No hay una consulta próxima que preparar.")
        appointment = min(upcoming, key=lambda item: item.scheduled_at)
        existing = next(
            (
                artifact
                for artifact in state.mission_artifacts
                if artifact.artifact_type == "consultation_packet"
                and artifact.payload.get("appointment_id") == appointment.id
            ),
            None,
        )
        if existing is not None:
            return MissionOutcome(
                action,
                existing.mission_id,
                (existing.id,),
                "completed",
                "El paquete de consulta ya existía; el ciclo fue idempotente.",
                (appointment.id,),
            )
        mission = HealthMission(
            title="Preparar paquete para la próxima consulta",
            mission_type="appointment_preparation",
            status=MissionStatus.COMPLETED,
            risk_level=RiskLevel.INFO,
            next_action="Paquete preparado; el paciente puede revisarlo antes de compartirlo.",
            evidence_ids=[appointment.id],
            agent_plan=[
                AgentStep(agent="HISTORIA", action="Reunir cambios longitudinales autorizados", reason="Continuidad", status="completed"),
                AgentStep(agent="ARCHIVUM", action="Organizar resultados y documentos disponibles", reason="Evitar omisiones", status="completed"),
                AgentStep(agent="ADVOCATE", action="Construir preguntas y resumen para la consulta", reason="Reducir fricción", status="completed"),
            ],
        )
        packet = consultation_brief(state, appointment.id)
        artifact = MissionArtifact(
            mission_id=mission.id,
            artifact_type="consultation_packet",
            title=f"Paquete de continuidad · {appointment.title}",
            source_evidence_ids=[appointment.id],
            payload={"appointment_id": appointment.id, "brief": packet, "requires_patient_review": True},
        )
        mission.closure_evidence = [artifact.id, appointment.id]
        state.missions.append(mission)
        state.mission_artifacts.append(artifact)
        return MissionOutcome(
            action,
            mission.id,
            (artifact.id,),
            mission.status.value,
            "HealthIA reunió el contexto autorizado, creó el paquete de consulta y cerró esa tarea sin intervención manual.",
            (appointment.id,),
        )

    raise ValueError(f"Unsupported mission action: {action}")
