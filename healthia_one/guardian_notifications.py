from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

from healthia_one.guardian_context import GuardianAssessment
from healthia_one.models import PatientState


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


def _email_body(state: PatientState, assessment: GuardianAssessment) -> tuple[str, str]:
    first = _first_name(state)
    if assessment.classification == "appointment_preparation_gap":
        return (
            "HealthIA is preparing your upcoming appointment",
            (
                f"Hi {first},\n\n"
                "HealthIA checked the preparation items listed for your upcoming appointment against the health record you authorized. "
                "Some items are not yet verifiable, so I opened a preparation mission and will keep it active until the missing evidence is present.\n\n"
                "I did not book, cancel, or change your appointment, and this message contains no diagnosis or treatment change. "
                "Open HealthIA when convenient to review exactly what is still missing.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "appointment_preparation_resolved":
        return (
            "HealthIA completed your appointment preparation mission",
            (
                f"Hi {first},\n\n"
                "HealthIA matched the evidence in your record to every preparation item listed for your upcoming appointment. "
                "The preparation mission is now closed automatically because those items are verifiable in HealthIA.\n\n"
                "This does not guarantee that a provider will accept a document or mean the clinical visit is complete. "
                "No appointment, diagnosis, medication, or treatment was changed.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "result_monitoring_context_gap":
        return (
            "HealthIA found a follow-up item in your record",
            (
                f"Hi {first},\n\n"
                "HealthIA stored a new laboratory result and compared the evidence visible in your record with the treatment context you authorized. "
                "I found a monitoring-context gap and opened a HealthIA mission so it does not get lost.\n\n"
                "This is a record-completeness follow-up, not a diagnosis. It does not mean your treatment is unsafe, and no medication or treatment was changed. "
                "If you already have the missing laboratory evidence, open HealthIA and upload or confirm it so I can resolve the mission.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "result_monitoring_context_resolved":
        return (
            "HealthIA closed a follow-up mission with new evidence",
            (
                f"Hi {first},\n\n"
                "HealthIA matched newly available laboratory evidence to a follow-up mission that was waiting for it. "
                "The requested monitoring context is now present in your HealthIA record, so I closed that mission automatically.\n\n"
                "This is a continuity update, not a diagnosis. No medication or treatment was changed. "
                "You can open HealthIA to review the evidence and the mission receipt.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "recurring_context_pattern":
        return (
            "HealthIA noticed a pattern worth reviewing",
            (
                f"Hi {first},\n\n"
                "HealthIA continued monitoring the health signals you authorized while you were away. "
                "I noticed a recurring physiological pattern around a similar part of your day and prepared a short context review.\n\n"
                "This is an association, not a diagnosis, and I have not identified the cause. No medication or treatment was changed. "
                "When convenient, open HealthIA so I can ask for the missing context and continue the same mission with you.\n\n"
                "— HealthIA Guardian"
            ),
        )
    return (
        "HealthIA has a signal ready for your review",
        (
            f"Hi {first},\n\n"
            "HealthIA continued monitoring the health signals you authorized while you were away. "
            "I found a change that is not fully explained by the context currently available and prepared it for your review.\n\n"
            "This message is not a diagnosis and no medication or treatment was changed. Open HealthIA when convenient so I can confirm the missing context with you.\n\n"
            "— HealthIA Guardian"
        ),
    )


def plan_guardian_notification(
    state: PatientState,
    assessment: GuardianAssessment,
    *,
    mission_id: str,
) -> GuardianNotificationPlan:
    """Create a bounded patient-contact plan from one Guardian assessment.

    Email composition is allowed without external mutation. Sending requires two
    explicit standing signal flags in PatientConsent.signal_types:

    - guardian_email: patient wants Guardian email updates;
    - guardian_email_auto_send: patient allows low-risk Guardian update emails to
      be sent without approving each message individually.

    This planner does not itself send email. The outbound worker must still pass
    the Google/external action guard and persist a provider receipt.
    """
    if not assessment.notify_patient:
        return GuardianNotificationPlan(
            patient_id=state.profile.id,
            mission_id=mission_id,
            in_app=False,
            push_requested=False,
            reason="Assessment does not request patient interruption.",
        )

    signals = set(state.consent.signal_types)
    email_address = str(state.profile.email or "").strip()
    email_opt_in = "guardian_email" in signals
    auto_send_opt_in = "guardian_email_auto_send" in signals
    push_opt_in = "guardian_push" in signals

    email_draft = None
    if email_address:
        subject, body = _email_body(state, assessment)
        mode: Literal["draft_only", "eligible_auto_send", "in_app_only"] = "draft_only"
        consent_basis: list[str] = []
        if email_opt_in:
            consent_basis.append("guardian_email")
        if email_opt_in and auto_send_opt_in:
            mode = "eligible_auto_send"
            consent_basis.append("guardian_email_auto_send")
        email_draft = GuardianEmailDraft(
            id=_stable_draft_id(state.profile.id, mission_id, assessment),
            patient_id=state.profile.id,
            mission_id=mission_id,
            recipient=email_address,
            subject=subject,
            body=body,
            delivery_mode=mode,
            consent_basis=consent_basis,
            contains_precise_location=False,
            changes_treatment=False,
            diagnostic_claim=False,
        )

    return GuardianNotificationPlan(
        patient_id=state.profile.id,
        mission_id=mission_id,
        in_app=True,
        push_requested=push_opt_in,
        email=email_draft,
        urgent_email_only_forbidden=True,
        reason=(
            "A Guardian assessment needs patient context. External delivery remains consent- and receipt-gated."
        ),
    )
