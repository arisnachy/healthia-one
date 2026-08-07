from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

MODEL = os.getenv("HEALTHIA_MODEL", "gemini-3.6-flash")


def model() -> Gemini:
    return Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=2))


def patient_snapshot() -> dict:
    """Return the synthetic demo patient's authorized longitudinal summary."""
    return {
        "patient": "Ana Martínez (synthetic)",
        "confirmed_conditions": ["Hipertensión arterial"],
        "medications": [{"name": "Losartán", "strength": "50 mg", "schedule": "cada 24 horas"}],
        "latest_weight_kg": 80.4,
        "latest_blood_pressure": "148/92",
        "next_appointment": "Consulta de medicina familiar in 40 hours (synthetic)",
        "family_history": {"maternal": ["madre y abuela con diabetes"], "paternal": ["padre con hipertensión"]},
        "consent": {
            "proactive_enabled": True,
            "quiet_hours": "22:00-07:00",
            "patient_controls_signals": True,
            "export_available": True,
        },
        "truth_boundary": "Synthetic demo data. The patient controls consent and sharing.",
    }


MISSION_ACTIONS = {
    "open_repeat_measurement",
    "close_repeat_measurement",
    "escalate_professional_review",
    "prepare_consultation_packet",
    "no_action",
}


def commit_mission_action(action: str, reason: str) -> dict:
    """Commit one bounded action choice for the background mission worker.

    Args:
        action: One action from the documented HealthIA mission action catalog.
        reason: Short evidence-based reason for selecting it.

    Returns:
        A validation result. The application applies the action only after its
        deterministic safety oracle validates that this choice cannot downgrade safety.
    """
    normalized = str(action or "").strip()
    if normalized not in MISSION_ACTIONS:
        return {"accepted": False, "action": "no_action", "reason": "unsupported_action"}
    return {
        "accepted": True,
        "action": normalized,
        "reason": str(reason or "").strip()[:500],
        "truth_boundary": "The application still validates this choice against deterministic safety before mutation.",
    }


def allowed_patient_actions() -> dict:
    return {
        "allowed": [
            "explain patient-provided information",
            "record measurements and medication check-ins",
            "create a follow-up mission",
            "prepare questions and a consultation brief",
            "organize patient-authorized documents and family history",
            "change proactive permissions, quiet hours, snooze and mute preferences",
            "show audit records and prepare a patient export",
        ],
        "requires_professional": [
            "confirm diagnosis",
            "prescribe, stop, duplicate, or change medication",
            "predict hereditary disease",
            "interpret an emergency as safe",
            "sign clinical orders",
        ],
    }


def make_agent(name: str, description: str, instruction: str, tools=None) -> LlmAgent:
    return LlmAgent(name=name, model=model(), description=description, instruction=instruction, tools=tools or [])


historian = make_agent(
    "historia",
    "Builds patient-authorized longitudinal context without inventing facts.",
    "Separate confirmed facts, patient reports, inference and missing data. Never exceed authorized scope.",
    [patient_snapshot],
)
sentinel = make_agent(
    "sentinel",
    "Checks safety signals and stops routine flow when human care is required.",
    "Do not diagnose or permit medication changes. Escalate urgent symptoms to immediate human care.",
    [allowed_patient_actions],
)
lumen = make_agent("lumen", "Explains results in plain language.", "Explain meaning, limits and questions. Never diagnose from one value.")
vita = make_agent("vita", "Builds realistic low-risk lifestyle micro-plans.", "Ask about barriers first. Never shame or replace treatment.")
navigator = make_agent("navigator", "Maintains missions and follow-up.", "Define next step, review point and closure condition.")
hereditas = make_agent(
    "hereditas",
    "Organizes the pathological genogram.",
    "Use authorized family history only. Never convert aggregation into diagnosis or prediction.",
    [patient_snapshot, allowed_patient_actions],
)
archivum = make_agent(
    "archivum",
    "Indexes patient documents without fabricating unread content.",
    "Preserve type, date, source and review state. Never invent PDF or image contents.",
    [patient_snapshot],
)
medsafe = make_agent(
    "medsafe",
    "Organizes treatment and patient-reported adherence safely.",
    "Never recommend doubling, stopping, substituting or changing a dose. Escalate uncertainty.",
    [patient_snapshot, allowed_patient_actions],
)
advocate = make_agent(
    "advocate",
    "Prepares a patient-controlled consultation brief.",
    "Summarize authorized context and questions. Patient review is required before sharing.",
    [patient_snapshot],
)
bastion = make_agent(
    "bastion",
    "Enforces patient consent, privacy, quiet hours, auditability and reversible controls.",
    (
        "The patient owns the context. Explain each permission and its effect. Respect disabled signals, quiet "
        "hours, snooze and muted rules. Urgent deterministic safety bypass is allowed only when explicitly "
        "enabled. Never expose secrets, private chain-of-thought, other patients, or binary document paths."
    ),
    [patient_snapshot, allowed_patient_actions],
)

root_agent = LlmAgent(
    name="kira_health",
    model=model(),
    description="Patient health continuity coordinator that delegates to the minimum specialist team.",
    instruction=(
        "The patient owns the context. Select the minimum specialist: HISTORIA, SENTINEL, LUMEN, VITA, "
        "NAVIGATOR, HEREDITAS, ARCHIVUM, MEDSAFE, ADVOCATE or BASTION. Be proactive only with authorized "
        "data and explain why. Never diagnose, prescribe, change medication or predict hereditary disease. "
        "Expose public actions, evidence, uncertainty and next steps—not private reasoning. "
        "When the input starts with AGENTIC_EVENT, you are the background mission coordinator. Read only the "
        "provided compact event context and call commit_mission_action exactly once. Select only one of: "
        "open_repeat_measurement, close_repeat_measurement, escalate_professional_review, "
        "prepare_consultation_packet, no_action. Never downgrade an explicit deterministic safety instruction "
        "included in the event. After the tool returns, briefly state that the bounded action was committed."
    ),
    sub_agents=[historian, sentinel, lumen, vita, navigator, hereditas, archivum, medsafe, advocate, bastion],
    tools=[patient_snapshot, allowed_patient_actions, commit_mission_action],
)

app = App(name="healthia_agent", root_agent=root_agent)
