from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from healthia_one.autopilot_event_intents import stage_event_intent
from healthia_one.control import audit
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.models import (
    AgentStep,
    Appointment,
    ChatMessage,
    DocumentCategory,
    HealthMission,
    MissionStatus,
    PatientState,
    RiskLevel,
)


MISSION_TYPE = "appointment_guardian_preparation"
RULE_KEY = "appointment_guardian:preparation"
PREP_WINDOW = timedelta(hours=72)
RECENT_RESULT_WINDOW = timedelta(days=180)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _tokens(value: Any) -> set[str]:
    return {token for token in _normalize(value).split() if len(token) >= 3}


def _appointment_mission(state: PatientState, appointment_id: str) -> HealthMission | None:
    return next(
        (
            mission
            for mission in state.missions
            if mission.mission_type == MISSION_TYPE and appointment_id in mission.evidence_ids
        ),
        None,
    )


def _open_appointment_mission(state: PatientState, appointment_id: str) -> HealthMission | None:
    mission = _appointment_mission(state, appointment_id)
    if mission is None:
        return None
    if mission.status in {
        MissionStatus.ACTIVE,
        MissionStatus.WAITING_PATIENT,
        MissionStatus.WAITING_PROFESSIONAL,
    }:
        return mission
    return None


def _document_material(document) -> str:
    return " ".join(
        [
            document.title,
            document.filename,
            document.category.value,
            *document.tags,
        ]
    )


def _category_document_ids(state: PatientState, category: DocumentCategory) -> list[str]:
    return [document.id for document in state.documents if document.category == category and document.status != "invalid"]


def _recent_result_evidence(state: PatientState, now: datetime) -> list[str]:
    threshold = now - RECENT_RESULT_WINDOW
    result_ids = [
        result.id
        for result in state.results
        if result.status == "parsed" and threshold <= result.uploaded_at <= now + timedelta(minutes=10)
    ]
    if not result_ids:
        return []
    document_ids = [
        document.id
        for document in state.documents
        if document.related_result_id in set(result_ids) and document.status != "invalid"
    ]
    return list(dict.fromkeys([*result_ids, *document_ids]))


def _active_medication_evidence(state: PatientState) -> list[str]:
    plan_ids = [plan.id for plan in state.medication_plans if plan.active]
    if plan_ids:
        return plan_ids
    # Profile medication strings are useful context but do not have stable object
    # IDs. A synthetic evidence marker is deliberately not created. Without a
    # persisted MedicationPlan, the requirement remains unverified.
    return []


def _generic_document_match(state: PatientState, requirement: str) -> list[str]:
    wanted = _tokens(requirement)
    if not wanted:
        return []
    matches: list[str] = []
    for document in state.documents:
        if document.status == "invalid":
            continue
        available = _tokens(_document_material(document))
        # Conservative matching: all meaningful requirement tokens must be
        # represented in one persisted document. This prevents a loose keyword
        # from being mistaken for proof that the requested document exists.
        if wanted.issubset(available):
            matches.append(document.id)
    return matches


def evaluate_requirement(state: PatientState, requirement: str, *, now: datetime) -> dict[str, Any]:
    normalized = _normalize(requirement)
    result_tokens = {"resultado", "resultados", "result", "results", "laboratorio", "laboratory", "analitica", "analisis", "lab"}
    medication_tokens = {"medicamento", "medicamentos", "medication", "medications", "tratamiento", "treatment"}
    insurance_tokens = {"seguro", "insurance", "aseguradora"}
    identity_tokens = {"identidad", "identity", "cedula", "passport", "pasaporte"}
    words = set(normalized.split())

    if words & result_tokens:
        evidence = _recent_result_evidence(state, now)
        return {
            "requirement": requirement,
            "kind": "recent_results",
            "satisfied": bool(evidence),
            "evidence_ids": evidence,
            "verification": "parsed_result_within_180_days",
        }

    if words & medication_tokens or ("lista" in words and "medicamentos" in words):
        evidence = _active_medication_evidence(state)
        return {
            "requirement": requirement,
            "kind": "active_medication_list",
            "satisfied": bool(evidence),
            "evidence_ids": evidence,
            "verification": "active_persisted_medication_plan",
        }

    if words & insurance_tokens:
        evidence = _category_document_ids(state, DocumentCategory.INSURANCE)
        return {
            "requirement": requirement,
            "kind": "insurance_document",
            "satisfied": bool(evidence),
            "evidence_ids": evidence,
            "verification": "persisted_insurance_document",
        }

    if words & identity_tokens:
        evidence = _category_document_ids(state, DocumentCategory.IDENTITY)
        return {
            "requirement": requirement,
            "kind": "identity_document",
            "satisfied": bool(evidence),
            "evidence_ids": evidence,
            "verification": "persisted_identity_document",
        }

    evidence = _generic_document_match(state, requirement)
    return {
        "requirement": requirement,
        "kind": "generic_document",
        "satisfied": bool(evidence),
        "evidence_ids": evidence,
        "verification": "exact_token_document_match" if evidence else "unverified_requirement",
    }


def appointment_preparation_snapshot(
    state: PatientState,
    appointment: Appointment,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or utc_now()
    checks = [evaluate_requirement(state, item, now=current) for item in appointment.required_documents]
    missing = [item for item in checks if not item["satisfied"]]
    verified = [item for item in checks if item["satisfied"]]
    evidence_ids = list(
        dict.fromkeys(
            evidence_id
            for check in verified
            for evidence_id in check["evidence_ids"]
        )
    )
    return {
        "appointment_id": appointment.id,
        "scheduled_at": appointment.scheduled_at.isoformat(),
        "required_count": len(checks),
        "verified_count": len(verified),
        "missing_count": len(missing),
        "checks": checks,
        "missing_requirements": [item["requirement"] for item in missing],
        "evidence_ids": evidence_ids,
        "ready": bool(checks) and not missing,
        "truth_boundary": (
            "Preparation readiness means HealthIA can verify the appointment's listed requirements in the patient record. "
            "It does not prove the provider will accept them or that the clinical visit is complete."
        ),
    }


def _assessment(
    appointment: Appointment,
    *,
    classification: str,
    summary: str,
    missing_requirements: list[str],
    provenance: list[str],
) -> GuardianAssessment:
    return GuardianAssessment(
        observation_id=appointment.id,
        metric="appointment_preparation",
        classification=classification,
        risk_level=RiskLevel.INFO,
        summary=summary,
        observed={
            "appointment_id": appointment.id,
            "scheduled_at": appointment.scheduled_at.isoformat(),
        },
        context={
            "rule_key": RULE_KEY,
            "missing_requirement_count": len(missing_requirements),
        },
        inference=(
            "HealthIA found appointment preparation items that are not yet verifiable in the authorized record."
            if classification == "appointment_preparation_gap"
            else "Every listed appointment preparation requirement is now verifiable in the authorized HealthIA record."
        ),
        hypothesis=(
            "The patient may already possess an unuploaded document; HealthIA will keep the mission open until evidence is present."
            if classification == "appointment_preparation_gap"
            else "No additional inference is required to close the record-preparation mission."
        ),
        confidence="high",
        notify_patient=True,
        requires_human_review=False,
        can_suppress_safety=False,
        provenance=list(dict.fromkeys(provenance)),
    )


def _stage_notification(
    state: PatientState,
    *,
    appointment: Appointment,
    mission: HealthMission,
    assessment: GuardianAssessment,
    event_kind: str,
    signature: str,
) -> str:
    event = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key=f"appointment_guardian|{appointment.id}|{event_kind}|{signature}",
        payload={
            "source": "guardian_context",
            "guardian_domain": "appointment_preparation",
            "mission_id": mission.id,
            "appointment_id": appointment.id,
            "guardian_assessment": assessment.model_dump(mode="json"),
            "notification_requested": True,
            "appointment_guardian_event": event_kind,
            "diagnosis_claimed": False,
            "treatment_changed": False,
            "appointment_booked_or_changed": False,
            "human_boundary": True,
        },
    )
    return event.id


def _signature(values: list[str]) -> str:
    normalized = "|".join(sorted(_normalize(item) for item in values))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _cancel_stale_mission(state: PatientState, appointment: Appointment, mission: HealthMission) -> dict[str, Any]:
    mission.status = MissionStatus.CANCELLED
    mission.updated_at = utc_now()
    reason = "appointment_cancelled" if appointment.status == "cancelled" else "appointment_no_longer_scheduled"
    mission.next_action = "Preparation mission closed because the appointment is no longer scheduled."
    receipt = audit(
        state,
        actor="healthia_appointment_guardian",
        action="cancel_appointment_preparation_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={"appointment_id": appointment.id, "reason": reason},
    )
    mission.closure_evidence = list(dict.fromkeys([*mission.closure_evidence, reason, receipt.id]))
    return {"status": "cancelled", "mission_id": mission.id, "appointment_id": appointment.id, "receipt_id": receipt.id}


def _reconcile_one(state: PatientState, appointment: Appointment, *, now: datetime) -> dict[str, Any] | None:
    mission = _appointment_mission(state, appointment.id)

    if appointment.status != "scheduled":
        if mission and mission.status not in {MissionStatus.COMPLETED, MissionStatus.CANCELLED}:
            return _cancel_stale_mission(state, appointment, mission)
        return None

    if appointment.scheduled_at < now:
        if mission and mission.status not in {MissionStatus.COMPLETED, MissionStatus.CANCELLED}:
            return _cancel_stale_mission(state, appointment, mission)
        return None

    if appointment.scheduled_at > now + PREP_WINDOW:
        return None

    if not appointment.required_documents:
        return None

    snapshot = appointment_preparation_snapshot(state, appointment, now=now)
    missing = list(snapshot["missing_requirements"])

    if not missing:
        open_mission = _open_appointment_mission(state, appointment.id)
        if open_mission is None:
            return {"status": "already_ready", "appointment_id": appointment.id}
        for evidence_id in [appointment.id, *snapshot["evidence_ids"]]:
            if evidence_id not in open_mission.evidence_ids:
                open_mission.evidence_ids.append(evidence_id)
        open_mission.status = MissionStatus.COMPLETED
        open_mission.updated_at = now
        open_mission.next_action = (
            "Preparation mission closed automatically: every listed appointment requirement is verifiable in the HealthIA record."
        )
        receipt = audit(
            state,
            actor="healthia_appointment_guardian",
            action="resolve_appointment_preparation_mission",
            resource_type="health_mission",
            resource_id=open_mission.id,
            details={
                "appointment_id": appointment.id,
                "verified_count": snapshot["verified_count"],
                "required_count": snapshot["required_count"],
                "evidence_ids": snapshot["evidence_ids"],
                "appointment_booked_or_changed": False,
                "treatment_changed": False,
                "resolution": "listed_requirements_verified",
            },
        )
        open_mission.closure_evidence = list(
            dict.fromkeys([
                *open_mission.closure_evidence,
                "listed_appointment_requirements_verified",
                receipt.id,
            ])
        )
        state.messages.append(
            ChatMessage(
                patient_id=state.profile.id,
                role="assistant",
                author="HealthIA Guardian",
                content=(
                    "I matched the evidence in your HealthIA record to the preparation items for your upcoming appointment. "
                    "Every listed requirement is now verifiable, so I closed the preparation mission automatically. "
                    "This does not confirm provider acceptance or complete the clinical visit."
                ),
                risk_level=RiskLevel.INFO,
                mission_id=open_mission.id,
                metadata={
                    "autonomous_appointment_guardian": True,
                    "appointment_preparation_resolved": True,
                    "appointment_id": appointment.id,
                    "resolution_receipt_id": receipt.id,
                },
            )
        )
        assessment = _assessment(
            appointment,
            classification="appointment_preparation_resolved",
            summary="HealthIA verified every listed preparation requirement and closed the appointment preparation mission.",
            missing_requirements=[],
            provenance=[appointment.id, *snapshot["evidence_ids"], receipt.id],
        )
        event_id = _stage_notification(
            state,
            appointment=appointment,
            mission=open_mission,
            assessment=assessment,
            event_kind="resolved",
            signature=_signature(snapshot["evidence_ids"]),
        )
        return {
            "status": "completed",
            "appointment_id": appointment.id,
            "mission_id": open_mission.id,
            "receipt_id": receipt.id,
            "event_id": event_id,
        }

    created = mission is None
    if mission is None:
        mission = HealthMission(
            patient_id=state.profile.id,
            title="Prepare for upcoming appointment",
            mission_type=MISSION_TYPE,
            status=MissionStatus.WAITING_PATIENT,
            risk_level=RiskLevel.INFO,
            next_action="",
            evidence_ids=[appointment.id],
            agent_plan=[
                AgentStep(
                    agent="APPOINTMENT GUARDIAN",
                    action="Verify the appointment's listed preparation requirements against the longitudinal record",
                    reason="Turn a near-term appointment into a resolvable preparation mission",
                    status="completed",
                ),
                AgentStep(
                    agent="ARCHIVUM",
                    action="Match required documents to persisted evidence without inventing availability",
                    reason="Provider preparation should be evidence-backed",
                    status="running",
                ),
                AgentStep(
                    agent="KIRA",
                    action="Keep the mission alive until every listed requirement is verifiable",
                    reason="Close by evidence, not by reminder delivery",
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
                    "Your appointment is approaching. I checked the preparation items against your HealthIA record and found items I cannot verify yet. "
                    "I opened a preparation mission and will keep it active until the missing evidence is present."
                ),
                risk_level=RiskLevel.INFO,
                mission_id=mission.id,
                metadata={
                    "autonomous_appointment_guardian": True,
                    "appointment_preparation_gap": True,
                    "appointment_id": appointment.id,
                    "missing_requirements": missing,
                },
            )
        )

    mission.updated_at = now
    for evidence_id in [appointment.id, *snapshot["evidence_ids"]]:
        if evidence_id not in mission.evidence_ids:
            mission.evidence_ids.append(evidence_id)
    mission.next_action = "Still missing: " + "; ".join(missing) + "."

    signature = _signature(missing)
    assessment = _assessment(
        appointment,
        classification="appointment_preparation_gap",
        summary=f"HealthIA cannot yet verify {len(missing)} listed appointment preparation item(s).",
        missing_requirements=missing,
        provenance=[appointment.id, *snapshot["evidence_ids"]],
    )
    event_id = _stage_notification(
        state,
        appointment=appointment,
        mission=mission,
        assessment=assessment,
        event_kind="created" if created else "updated",
        signature=signature,
    )
    audit(
        state,
        actor="healthia_appointment_guardian",
        action="open_appointment_preparation_mission" if created else "update_appointment_preparation_mission",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "appointment_id": appointment.id,
            "missing_requirements": missing,
            "verified_count": snapshot["verified_count"],
            "required_count": snapshot["required_count"],
            "event_id": event_id,
            "appointment_booked_or_changed": False,
            "diagnosis_claimed": False,
            "treatment_changed": False,
        },
    )
    return {
        "status": "created" if created else "waiting",
        "appointment_id": appointment.id,
        "mission_id": mission.id,
        "event_id": event_id,
        "missing_requirements": missing,
    }


def reconcile_appointment_guardian(state: PatientState, *, now: datetime | None = None) -> dict[str, Any]:
    """Turn upcoming appointments into evidence-closed preparation missions.

    This function mutates PatientState only. It does not book, cancel, reschedule,
    contact a provider, change treatment, or perform a network call. Notifications
    are staged as durable intents and become externally visible only after the
    canonical state commit.
    """
    current = now or utc_now()
    report: dict[str, Any] = {"created": [], "waiting": [], "completed": [], "cancelled": []}

    if not state.consent.proactive_enabled or "appointments" not in set(state.consent.signal_types):
        return report
    if any(RULE_KEY.startswith(prefix) for prefix in state.consent.muted_rule_prefixes):
        return report

    for appointment in sorted(state.appointments, key=lambda item: item.scheduled_at):
        outcome = _reconcile_one(state, appointment, now=current)
        if not outcome:
            continue
        status = outcome["status"]
        if status == "created":
            report["created"].append(outcome)
        elif status in {"waiting", "already_ready"}:
            report["waiting"].append(outcome)
        elif status == "completed":
            report["completed"].append(outcome)
        elif status == "cancelled":
            report["cancelled"].append(outcome)
    return report


def appointment_guardian_due(state: PatientState, *, now: datetime | None = None) -> bool:
    current = now or utc_now()
    if not state.consent.proactive_enabled or "appointments" not in set(state.consent.signal_types):
        return False
    if any(RULE_KEY.startswith(prefix) for prefix in state.consent.muted_rule_prefixes):
        return False
    return any(
        appointment.status == "scheduled"
        and current <= appointment.scheduled_at <= current + PREP_WINDOW
        and bool(appointment.required_documents)
        for appointment in state.appointments
    )
