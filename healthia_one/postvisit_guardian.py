from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from healthia_one.autopilot_event_intents import stage_event_intent
from healthia_one.control import audit
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.models import (
    AgentStep,
    Appointment,
    ChatMessage,
    ClinicalDocument,
    DocumentCategory,
    HealthMission,
    MissionStatus,
    PatientState,
    RiskLevel,
)


MISSION_TYPE = "postvisit_guardian_summary_capture"
RULE_KEY = "postvisit_guardian:summary_capture"
CAPTURE_WINDOW = timedelta(days=14)
POSTVISIT_CATEGORIES = {DocumentCategory.CONSULTATION, DocumentCategory.DISCHARGE}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mission_for(state: PatientState, appointment_id: str) -> HealthMission | None:
    return next(
        (
            mission
            for mission in state.missions
            if mission.mission_type == MISSION_TYPE and appointment_id in mission.evidence_ids
        ),
        None,
    )


def _open_mission_for(state: PatientState, appointment_id: str) -> HealthMission | None:
    mission = _mission_for(state, appointment_id)
    if mission is None:
        return None
    return mission if mission.status in {
        MissionStatus.ACTIVE,
        MissionStatus.WAITING_PATIENT,
        MissionStatus.WAITING_PROFESSIONAL,
    } else None


def _completed_recent(appointment: Appointment, now: datetime) -> bool:
    return (
        appointment.status == "completed"
        and appointment.scheduled_at <= now
        and appointment.scheduled_at >= now - CAPTURE_WINDOW
    )


def _candidate_appointments_for_document(
    state: PatientState,
    document: ClinicalDocument,
    *,
    now: datetime,
) -> list[Appointment]:
    if document.category not in POSTVISIT_CATEGORIES or document.status == "invalid":
        return []
    return [
        appointment
        for appointment in state.appointments
        if _completed_recent(appointment, now)
        and appointment.scheduled_at <= document.uploaded_at <= appointment.scheduled_at + CAPTURE_WINDOW
    ]


def _unambiguous_documents(
    state: PatientState,
    appointment: Appointment,
    *,
    now: datetime,
) -> list[ClinicalDocument]:
    matched: list[ClinicalDocument] = []
    for document in state.documents:
        candidates = _candidate_appointments_for_document(state, document, now=now)
        if len(candidates) == 1 and candidates[0].id == appointment.id:
            matched.append(document)
    return matched


def _assessment(
    appointment: Appointment,
    *,
    classification: str,
    provenance: list[str],
) -> GuardianAssessment:
    return GuardianAssessment(
        observation_id=appointment.id,
        metric="postvisit_continuity",
        classification=classification,
        risk_level=RiskLevel.INFO,
        summary=(
            "A completed appointment does not yet have an unambiguous consultation/discharge document in HealthIA."
            if classification == "postvisit_summary_gap"
            else "HealthIA matched durable post-visit evidence to the completed appointment and closed the continuity mission."
        ),
        observed={
            "appointment_id": appointment.id,
            "scheduled_at": appointment.scheduled_at.isoformat(),
            "appointment_status": appointment.status,
        },
        context={"rule_key": RULE_KEY},
        inference=(
            "The patient record is missing verifiable post-visit evidence for this completed appointment."
            if classification == "postvisit_summary_gap"
            else "A consultation/discharge document is uniquely attributable to this completed appointment by the bounded time window."
        ),
        hypothesis=(
            "The patient may already have the visit summary outside HealthIA and can upload it."
            if classification == "postvisit_summary_gap"
            else "No clinical inference is required to close a document-capture mission."
        ),
        confidence="high",
        notify_patient=True,
        requires_human_review=False,
        can_suppress_safety=False,
        provenance=list(dict.fromkeys(provenance)),
    )


def _stage(
    state: PatientState,
    appointment: Appointment,
    mission: HealthMission,
    assessment: GuardianAssessment,
    *,
    event_kind: str,
    evidence_signature: str,
) -> str:
    event = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key=f"postvisit_guardian|{appointment.id}|{event_kind}|{evidence_signature}",
        payload={
            "source": "guardian_context",
            "guardian_domain": "postvisit_continuity",
            "mission_id": mission.id,
            "appointment_id": appointment.id,
            "guardian_assessment": assessment.model_dump(mode="json"),
            "notification_requested": True,
            "postvisit_guardian_event": event_kind,
            "diagnosis_claimed": False,
            "treatment_changed": False,
            "appointment_booked_or_changed": False,
            "human_boundary": True,
        },
    )
    return event.id


def _signature(values: list[str]) -> str:
    raw = "|".join(sorted(values))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _open_gap(state: PatientState, appointment: Appointment, *, now: datetime) -> dict[str, Any]:
    existing = _open_mission_for(state, appointment.id)
    if existing is not None:
        return {"status": "waiting", "appointment_id": appointment.id, "mission_id": existing.id}

    mission = HealthMission(
        patient_id=state.profile.id,
        title="Capture post-visit summary",
        mission_type=MISSION_TYPE,
        status=MissionStatus.WAITING_PATIENT,
        risk_level=RiskLevel.INFO,
        next_action="Upload the consultation note or discharge summary from this completed visit when available.",
        evidence_ids=[appointment.id],
        agent_plan=[
            AgentStep(
                agent="POSTVISIT GUARDIAN",
                action="Detect completed appointment without attributable post-visit evidence",
                reason="Prevent the visit outcome from disappearing after the encounter",
                status="completed",
            ),
            AgentStep(
                agent="ARCHIVUM",
                action="Wait for a persisted consultation or discharge document",
                reason="Close only from durable evidence",
                status="running",
            ),
            AgentStep(
                agent="KIRA",
                action="Preserve the mission across sessions and close when evidence is unambiguous",
                reason="Maintain longitudinal continuity without inventing visit details",
                status="running",
            ),
        ],
    )
    state.missions.append(mission)
    state.messages.append(
        ChatMessage(
            patient_id=state.profile.id,
            role="assistant",
            author="HealthIA Guardian",
            content=(
                "I see that this appointment is marked completed, but I cannot yet verify a consultation note or discharge summary in your HealthIA record. "
                "I opened a post-visit continuity mission so the outcome does not get lost. I will not invent what happened during the visit."
            ),
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            metadata={
                "autonomous_postvisit_guardian": True,
                "postvisit_summary_gap": True,
                "appointment_id": appointment.id,
            },
        )
    )
    assessment = _assessment(
        appointment,
        classification="postvisit_summary_gap",
        provenance=[appointment.id],
    )
    event_id = _stage(
        state,
        appointment,
        mission,
        assessment,
        event_kind="created",
        evidence_signature="missing",
    )
    audit(
        state,
        actor="healthia_postvisit_guardian",
        action="open_postvisit_summary_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "appointment_id": appointment.id,
            "event_id": event_id,
            "diagnosis_claimed": False,
            "treatment_changed": False,
            "appointment_booked_or_changed": False,
        },
    )
    return {"status": "created", "appointment_id": appointment.id, "mission_id": mission.id, "event_id": event_id}


def _close_with_documents(
    state: PatientState,
    appointment: Appointment,
    mission: HealthMission,
    documents: list[ClinicalDocument],
    *,
    now: datetime,
) -> dict[str, Any]:
    document_ids = [document.id for document in documents]
    for evidence_id in [appointment.id, *document_ids]:
        if evidence_id not in mission.evidence_ids:
            mission.evidence_ids.append(evidence_id)
    mission.status = MissionStatus.COMPLETED
    mission.updated_at = now
    mission.next_action = (
        "Post-visit continuity mission closed automatically: a consultation/discharge document is now durably present and unambiguously attributable to this visit."
    )
    receipt = audit(
        state,
        actor="healthia_postvisit_guardian",
        action="resolve_postvisit_summary_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "appointment_id": appointment.id,
            "document_ids": document_ids,
            "resolution": "postvisit_document_present_unambiguous",
            "diagnosis_claimed": False,
            "treatment_changed": False,
            "appointment_booked_or_changed": False,
        },
    )
    mission.closure_evidence = list(dict.fromkeys([
        *mission.closure_evidence,
        "postvisit_document_present_unambiguous",
        receipt.id,
    ]))
    state.messages.append(
        ChatMessage(
            patient_id=state.profile.id,
            role="assistant",
            author="HealthIA Guardian",
            content=(
                "I matched a persisted consultation/discharge document to your completed visit and closed the post-visit continuity mission. "
                "This confirms document capture only; I did not infer a diagnosis or change treatment."
            ),
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            metadata={
                "autonomous_postvisit_guardian": True,
                "postvisit_summary_resolved": True,
                "appointment_id": appointment.id,
                "resolution_receipt_id": receipt.id,
            },
        )
    )
    assessment = _assessment(
        appointment,
        classification="postvisit_summary_resolved",
        provenance=[appointment.id, *document_ids, receipt.id],
    )
    event_id = _stage(
        state,
        appointment,
        mission,
        assessment,
        event_kind="resolved",
        evidence_signature=_signature(document_ids),
    )
    return {
        "status": "completed",
        "appointment_id": appointment.id,
        "mission_id": mission.id,
        "document_ids": document_ids,
        "receipt_id": receipt.id,
        "event_id": event_id,
    }


def reconcile_postvisit_guardian(state: PatientState, *, now: datetime | None = None) -> dict[str, Any]:
    """Close the gap between a completed appointment and its durable outcome evidence.

    No clinical content is inferred here. A consultation/discharge document can
    close a mission only when the bounded time relationship identifies exactly one
    completed appointment. Ambiguous evidence fails closed.
    """
    current = now or utc_now()
    report: dict[str, Any] = {"created": [], "waiting": [], "completed": []}

    if not state.consent.proactive_enabled or "appointments" not in set(state.consent.signal_types):
        return report
    if any(RULE_KEY.startswith(prefix) for prefix in state.consent.muted_rule_prefixes):
        return report

    for appointment in sorted(state.appointments, key=lambda item: item.scheduled_at):
        if not _completed_recent(appointment, current):
            continue
        documents = _unambiguous_documents(state, appointment, now=current)
        mission = _open_mission_for(state, appointment.id)
        if documents:
            if mission is None:
                report["waiting"].append({
                    "status": "evidence_already_present",
                    "appointment_id": appointment.id,
                    "document_ids": [item.id for item in documents],
                })
                continue
            report["completed"].append(
                _close_with_documents(state, appointment, mission, documents, now=current)
            )
            continue
        outcome = _open_gap(state, appointment, now=current)
        report["created" if outcome["status"] == "created" else "waiting"].append(outcome)

    return report
