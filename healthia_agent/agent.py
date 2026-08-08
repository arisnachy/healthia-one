from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

MODEL = os.getenv("HEALTHIA_MODEL", "gemini-3.6-flash")


def model() -> Gemini:
    return Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=2))


def allowed_patient_actions() -> dict:
    """Static safety capabilities only; never returns patient-specific data."""
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
        "runtime_note": (
            "Patient-specific context is never embedded in this package. The FastAPI runtime passes the "
            "current authorized PatientState to healthia_one.adk_runtime on each demand-driven request."
        ),
    }


def make_agent(name: str, description: str, instruction: str, tools=None) -> LlmAgent:
    return LlmAgent(name=name, model=model(), description=description, instruction=instruction, tools=tools or [])


historian = make_agent(
    "historia",
    "Builds patient-authorized longitudinal context without inventing facts.",
    "Use only context supplied by the current runtime request. Separate confirmed facts, reports, inference and missing data.",
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
    "Organizes authorized family-history context.",
    "Use only family context supplied by the current request. Never convert aggregation into diagnosis or prediction.",
)
archivum = make_agent(
    "archivum",
    "Indexes patient documents without fabricating unread content.",
    "Preserve type, date, source and review state. Never invent PDF or image contents.",
)
medsafe = make_agent(
    "medsafe",
    "Organizes treatment and patient-reported adherence safely.",
    "Never recommend doubling, stopping, substituting or changing a dose. Escalate uncertainty.",
    [allowed_patient_actions],
)
advocate = make_agent(
    "advocate",
    "Prepares a patient-controlled consultation brief.",
    "Summarize only authorized current-request context and questions. Patient review is required before sharing.",
)
bastion = make_agent(
    "bastion",
    "Enforces patient consent, privacy, auditability and reversible controls.",
    (
        "The patient owns the context. Respect disabled signals, quiet hours, snooze and muted rules. "
        "Never expose secrets, private chain-of-thought, other patients, or binary storage paths."
    ),
    [allowed_patient_actions],
)

root_agent = LlmAgent(
    name="kira_health",
    model=model(),
    description=(
        "HealthIA ADK package. The production clinical planning path is healthia_one.adk_runtime, which "
        "injects the current authorized PatientState and executes deterministic clinical tools on demand."
    ),
    instruction=(
        "The patient owns the context. Select only the minimum specialist needed. Never assume a demo patient "
        "or static medical facts. Patient-specific evidence must come from the current runtime request. Never "
        "diagnose, prescribe, change medication or predict hereditary disease. Expose public actions, evidence, "
        "uncertainty and next steps, not private reasoning."
    ),
    sub_agents=[historian, sentinel, lumen, vita, navigator, hereditas, archivum, medsafe, advocate, bastion],
    tools=[allowed_patient_actions],
)

app = App(name="healthia_agent", root_agent=root_agent)
