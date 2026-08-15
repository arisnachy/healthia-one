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
    if assessment.classification == "bp_followup_due":
        return (
            "HealthIA is waiting for your next blood-pressure reading",
            (
                f"Hi {first},\n\n"
                "The blood-pressure follow-up interval you authorized has elapsed since the last reading in HealthIA. "
                "I opened a measurement mission that will remain active until a new reading actually reaches your record.\n\n"
                "This is a follow-up reminder based on your stored care plan, not a diagnosis. No medication or treatment was changed.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "bp_followup_measurement_resolved":
        return (
            "HealthIA received your follow-up blood-pressure reading",
            (
                f"Hi {first},\n\n"
                "A new blood-pressure measurement reached your HealthIA record, so I closed the measurement-capture mission automatically.\n\n"
                "This confirms that the requested data arrived; it does not mean HealthIA declared your blood pressure controlled, and no treatment was changed.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "bp_followup_safety_handoff":
        return (
            "HealthIA received your reading and kept the mission open for safety review",
            (
                f"Hi {first},\n\n"
                "A new blood-pressure reading reached HealthIA, but the deterministic safety layer flagged the measurement for prompt human review. "
                "The follow-up mission therefore remains open instead of being marked clinically resolved.\n\n"
                "Open HealthIA to see the safety guidance. No medication or treatment was changed automatically.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "bp_followup_human_review_documented":
        return (
            "HealthIA recorded your documented follow-up review",
            (
                f"Hi {first},\n\n"
                "You explicitly linked post-handoff consultation or discharge evidence to the blood-pressure follow-up mission. "
                "HealthIA therefore closed the workflow as documented-review evidence captured.\n\n"
                "HealthIA did not independently verify professional authorship or the clinical content of that document, "
                "does not claim that your blood pressure or the clinical situation is resolved, and did not change treatment.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "medication_followup_due":
        return (
            "HealthIA is waiting for your next medication check-in",
            (
                f"Hi {first},\n\n"
                "The HealthIA continuity interval for a medication check-in stream you explicitly authorized has elapsed. "
                "I opened a check-in mission that will remain active until a new patient-reported check-in reaches your record.\n\n"
                "This does not mean HealthIA believes you missed a dose, and it is not an instruction to take, repeat, double, skip, stop, or change medication. "
                "No treatment was changed.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "medication_followup_checkin_resolved":
        return (
            "HealthIA received your medication check-in",
            (
                f"Hi {first},\n\n"
                "A new explicit medication check-in reached your HealthIA record, so I closed the check-in capture mission.\n\n"
                "This confirms only what you reported. It does not establish adherence, medication effectiveness, or treatment safety, and HealthIA did not provide compensation or dose-change advice. "
                "No treatment was changed.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification in {
        "medication_followup_safety_handoff",
        "medication_followup_review_handoff",
    }:
        return (
            "HealthIA recorded your check-in and kept the medication mission open for human review",
            (
                f"Hi {first},\n\n"
                "Your medication check-in reached HealthIA, but the information in that check-in requires human clinical or pharmacy review before the workflow can close automatically.\n\n"
                "HealthIA recorded the evidence but did not recommend an extra, replacement, reduced, skipped, stopped, or changed dose and did not change treatment. "
                "Open HealthIA to review the safety or follow-up guidance.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "medication_followup_human_review_documented":
        return (
            "HealthIA recorded documented review evidence for your medication follow-up",
            (
                f"Hi {first},\n\n"
                "You explicitly linked a post-handoff consultation or discharge document to the medication follow-up mission, so HealthIA closed the workflow as documented-review evidence captured.\n\n"
                "HealthIA did not independently verify professional authorship or clinical content, did not interpret the document as a new dose or medication order, "
                "does not claim that the medication issue is clinically resolved, and did not change treatment.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "postvisit_summary_gap":
        return (
            "HealthIA is preserving continuity after your visit",
            (
                f"Hi {first},\n\n"
                "HealthIA sees a completed appointment but cannot yet verify a consultation note or discharge summary in your longitudinal record. "
                "I opened a post-visit continuity mission so the outcome of the visit does not get lost.\n\n"
                "I am not guessing what happened during the appointment, and I did not change any diagnosis, medication, treatment, or appointment. "
                "If you have the visit summary, open HealthIA and add the document when convenient.\n\n"
                "— HealthIA Guardian"
            ),
        )
    if assessment.classification == "postvisit_summary_resolved":
        return (
            "HealthIA captured the evidence from your completed visit",
            (
                f"Hi {first},\n\n"
                "HealthIA matched a persisted consultation or discharge document to your completed visit and closed the post-visit continuity mission.\n\n"
                "This confirms document capture only. It does not mean HealthIA inferred a diagnosis or independently validated the clinical content, "
                "and no medication, treatment, or appointment was changed.\n\n"
                "— HealthIA Guardian"
            ),
        )
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
        reason="A Guardian assessment needs patient context. External delivery remains consent- and receipt-gated.",
    )
