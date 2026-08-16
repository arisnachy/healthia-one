from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

from healthia_one.guardian_context import GuardianAssessment
from healthia_one.models import PatientState


GUARDIAN_EMAIL_CONSENT = "guardian_email"
GUARDIAN_EMAIL_AUTO_SEND_CONSENT = "guardian_email_auto_send"


class GuardianEmailDraft(BaseModel):
    id: str
    patient_id: str
    mission_id: str
    recipient: str
    subject: str
    body: str
    delivery_mode: Literal["draft_only", "eligible_auto_send", "in_app_only"]
    consent_basis: list[str] = Field(default_factory=list)
    contains_precise_location: bool = False
    changes_treatment: bool = False
    diagnostic_claim: bool = False


class GuardianNotificationPlan(BaseModel):
    patient_id: str
    mission_id: str
    in_app: bool = True
    push_requested: bool = False
    email: GuardianEmailDraft | None = None
    urgent_email_only_forbidden: bool = True
    reason: str = ""


def _stable_draft_id(patient_id: str, mission_id: str, assessment: GuardianAssessment) -> str:
    raw = f"{patient_id}|{mission_id}|{assessment.observation_id}|{assessment.classification}"
    return "gemail_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _first_name(state: PatientState) -> str:
    value = str(state.profile.display_name or "").strip()
    return value.split()[0] if value else "there"


def _bp_copy(state: PatientState, assessment: GuardianAssessment) -> tuple[str, str] | None:
    first = _first_name(state)
    if assessment.classification == "bp_followup_due":
        return (
            "HealthIA is waiting for your next blood-pressure reading",
            f"Hi {first},\n\nThe blood-pressure follow-up interval you authorized has elapsed since the last reading in HealthIA. I opened a measurement mission that will remain active until a new reading actually reaches your record.\n\nThis is a follow-up reminder based on your stored continuity settings, not a diagnosis. No medication or treatment was changed.\n\n— HealthIA",
        )
    if assessment.classification == "bp_followup_measurement_resolved":
        return (
            "HealthIA received your follow-up blood-pressure reading",
            f"Hi {first},\n\nA new blood-pressure measurement reached your HealthIA record, so I closed the measurement-capture mission automatically.\n\nThis confirms only that the requested data arrived. It does not mean HealthIA declared your blood pressure controlled, and no treatment was changed.\n\n— HealthIA",
        )
    if assessment.classification == "bp_followup_safety_handoff":
        return (
            "HealthIA received your reading and kept the mission open for safety review",
            f"Hi {first},\n\nA new blood-pressure reading reached HealthIA, but the deterministic safety layer flagged the measurement for prompt human review. The mission therefore remains open rather than being marked clinically resolved.\n\nOpen HealthIA to see the safety guidance. No medication or treatment was changed automatically.\n\n— HealthIA",
        )
    if assessment.classification == "bp_followup_human_review_documented":
        return (
            "HealthIA recorded your documented follow-up review",
            f"Hi {first},\n\nYou explicitly linked post-handoff consultation or discharge evidence to the blood-pressure follow-up mission. HealthIA closed the workflow as documented-review evidence captured.\n\nHealthIA did not independently verify professional authorship or claim that the clinical situation is resolved. No treatment was changed.\n\n— HealthIA",
        )
    return None


def plan_guardian_notification(
    state: PatientState,
    assessment: GuardianAssessment,
    *,
    mission_id: str,
) -> GuardianNotificationPlan:
    """Plan notifications for the promoted BP circuit only.

    Broad Guardian notification types remain quarantined. Email is never sent
    unless the patient explicitly enabled Guardian email and standing auto-send.
    """
    if assessment.classification not in {
        "bp_followup_due",
        "bp_followup_measurement_resolved",
        "bp_followup_safety_handoff",
        "bp_followup_human_review_documented",
    }:
        return GuardianNotificationPlan(
            patient_id=state.profile.id,
            mission_id=mission_id,
            reason="classification_not_promoted_to_mainline",
        )

    copy = _bp_copy(state, assessment)
    if copy is None or not state.profile.email:
        return GuardianNotificationPlan(
            patient_id=state.profile.id,
            mission_id=mission_id,
            reason="patient_email_unavailable",
        )

    signals = set(state.consent.signal_types)
    email_enabled = GUARDIAN_EMAIL_CONSENT in signals
    auto_send = email_enabled and GUARDIAN_EMAIL_AUTO_SEND_CONSENT in signals
    subject, body = copy
    delivery_mode: Literal["draft_only", "eligible_auto_send", "in_app_only"] = (
        "eligible_auto_send" if auto_send else "draft_only" if email_enabled else "in_app_only"
    )
    basis = [item for item in (GUARDIAN_EMAIL_CONSENT, GUARDIAN_EMAIL_AUTO_SEND_CONSENT) if item in signals]

    return GuardianNotificationPlan(
        patient_id=state.profile.id,
        mission_id=mission_id,
        email=GuardianEmailDraft(
            id=_stable_draft_id(state.profile.id, mission_id, assessment),
            patient_id=state.profile.id,
            mission_id=mission_id,
            recipient=state.profile.email,
            subject=subject,
            body=body,
            delivery_mode=delivery_mode,
            consent_basis=basis,
        ),
        reason="bp_followup_mainline",
    )
