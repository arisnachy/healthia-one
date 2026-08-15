from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from healthia_one.autopilot_event_intents import stage_event_intent
from healthia_one.control import audit
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.medication_followup_guardian import MISSION_TYPE
from healthia_one.mission_evidence_api import linked_to_mission
from healthia_one.models import (
    ChatMessage,
    DocumentCategory,
    HealthMission,
    MissionStatus,
    PatientState,
    RiskLevel,
)


REVIEW_DOCUMENT_CATEGORIES = {
    DocumentCategory.CONSULTATION,
    DocumentCategory.DISCHARGE,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _medication_id(mission: HealthMission) -> str | None:
    prefix = f"{MISSION_TYPE}:"
    if not mission.mission_type.startswith(prefix):
        return None
    medication_id = mission.mission_type[len(prefix):].strip()
    return medication_id or None


def _handoff_at(state: PatientState, mission: HealthMission) -> datetime | None:
    events = [
        event
        for event in state.audit_events
        if event.action == "handoff_medication_followup_to_human"
        and event.resource_id == mission.id
        and event.outcome == "success"
    ]
    return min((event.created_at for event in events), default=None)


def _linked_review_documents(state: PatientState, mission: HealthMission) -> list:
    handoff_at = _handoff_at(state, mission)
    if handoff_at is None:
        return []
    return [
        document
        for document in state.documents
        if document.patient_id == state.profile.id
        and linked_to_mission(document, mission.id)
        and document.category in REVIEW_DOCUMENT_CATEGORIES
        and document.status != "invalid"
        and document.uploaded_at >= handoff_at
    ]


def _stage(
    state: PatientState,
    mission: HealthMission,
    *,
    medication_id: str,
    document_ids: list[str],
    receipt_id: str,
) -> str:
    observation_id = document_ids[-1]
    assessment = GuardianAssessment(
        observation_id=observation_id,
        metric="medication_followup",
        classification="medication_followup_human_review_documented",
        risk_level=RiskLevel.INFO,
        summary="Explicitly linked post-handoff review evidence was captured for a medication follow-up mission.",
        observed={
            "medication_id": medication_id,
            "document_ids": document_ids,
        },
        context={
            "mission_id": mission.id,
            "release_basis": "explicit_post_handoff_document_link",
        },
        inference="The workflow now has durable evidence that the patient explicitly linked a later consultation/discharge document to the human-gated mission.",
        hypothesis="No conclusion is made about medication safety, dose correctness, treatment effectiveness, or professional authorship.",
        confidence="high",
        notify_patient=True,
        requires_human_review=False,
        can_suppress_safety=False,
        provenance=[*document_ids, receipt_id],
    )
    signature = hashlib.sha256(
        f"{mission.id}|{'|'.join(document_ids)}|human_review_documented".encode("utf-8")
    ).hexdigest()[:16]
    event = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key=f"medication_review_release|{signature}",
        payload={
            "source": "guardian_context",
            "guardian_domain": "medication_followup",
            "mission_id": mission.id,
            "medication_id": medication_id,
            "guardian_assessment": assessment.model_dump(mode="json"),
            "notification_requested": True,
            "medication_followup_event": "human_review_documented",
            "explicit_patient_link_required": True,
            "professional_authorship_verified": False,
            "clinical_content_validated": False,
            "dose_instruction_given": False,
            "medication_plan_changed": False,
            "treatment_changed": False,
            "clinical_resolution_claimed": False,
            "human_boundary": True,
        },
    )
    return event.id


def _close(
    state: PatientState,
    mission: HealthMission,
    *,
    medication_id: str,
    documents: list,
    now: datetime,
) -> dict[str, Any]:
    document_ids = [document.id for document in documents]
    for document_id in document_ids:
        if document_id not in mission.evidence_ids:
            mission.evidence_ids.append(document_id)
    mission.status = MissionStatus.COMPLETED
    mission.risk_level = RiskLevel.INFO
    mission.updated_at = now
    mission.next_action = (
        "Workflow closed because post-handoff consultation/discharge evidence was explicitly linked to this medication mission. "
        "HealthIA did not interpret that evidence as a dose instruction and did not alter the medication plan."
    )
    receipt = audit(
        state,
        actor="healthia_medication_review_release",
        action="resolve_medication_followup_after_documented_review",
        resource_type="health_mission",
        resource_id=mission.id,
        details={
            "medication_id": medication_id,
            "document_ids": document_ids,
            "resolution": "documented_human_review_evidence_linked",
            "explicit_patient_link_required": True,
            "professional_authorship_verified": False,
            "clinical_content_validated": False,
            "dose_instruction_given": False,
            "medication_plan_changed": False,
            "clinical_resolution_claimed": False,
            "treatment_changed": False,
        },
    )
    mission.closure_evidence = list(
        dict.fromkeys(
            [
                *mission.closure_evidence,
                "documented_human_review_evidence_linked",
                receipt.id,
            ]
        )
    )
    state.messages.append(
        ChatMessage(
            patient_id=state.profile.id,
            role="assistant",
            author="HealthIA Guardian",
            content=(
                "You explicitly linked post-handoff consultation/discharge evidence to this medication follow-up mission, so I closed the workflow. "
                "That records documented review evidence only. HealthIA did not verify professional authorship, did not interpret the document as a new dose or medication order, "
                "did not declare the medication issue clinically resolved, and did not change treatment."
            ),
            risk_level=RiskLevel.INFO,
            mission_id=mission.id,
            metadata={
                "autonomous_medication_followup": True,
                "medication_followup_human_review_documented": True,
                "medication_id": medication_id,
                "document_ids": document_ids,
                "resolution_receipt_id": receipt.id,
                "professional_authorship_verified": False,
                "clinical_content_validated": False,
                "dose_instruction_given": False,
                "medication_plan_changed": False,
                "clinical_resolution_claimed": False,
                "treatment_changed": False,
            },
        )
    )
    event_id = _stage(
        state,
        mission,
        medication_id=medication_id,
        document_ids=document_ids,
        receipt_id=receipt.id,
    )
    return {
        "status": "completed",
        "mission_id": mission.id,
        "medication_id": medication_id,
        "document_ids": document_ids,
        "receipt_id": receipt.id,
        "event_id": event_id,
        "clinical_resolution_claimed": False,
        "medication_plan_changed": False,
    }


def reconcile_medication_review_release(
    state: PatientState,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Close only the workflow when explicit post-handoff human-review evidence exists."""
    current = now or utc_now()
    report: dict[str, Any] = {"completed": [], "waiting": []}

    for mission in state.missions:
        medication_id = _medication_id(mission)
        if medication_id is None or mission.status != MissionStatus.WAITING_PROFESSIONAL:
            continue
        documents = _linked_review_documents(state, mission)
        if not documents:
            report["waiting"].append(
                {
                    "status": "waiting",
                    "mission_id": mission.id,
                    "medication_id": medication_id,
                }
            )
            continue
        report["completed"].append(
            _close(
                state,
                mission,
                medication_id=medication_id,
                documents=documents,
                now=current,
            )
        )

    return report
