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
    """Return the synthetic demo patient's authorized longitudinal summary.

    This tool intentionally exposes only synthetic hackathon data. It must be replaced by an
    authenticated, patient-scoped store before any real deployment.
    """

    return {
        "patient": "Ana Martínez (synthetic)",
        "confirmed_conditions": ["Hipertensión arterial"],
        "medications": ["Losartán 50 mg cada 24 horas"],
        "latest_weight_kg": 80.4,
        "previous_weight_kg": 78.0,
        "latest_blood_pressure": "148/92",
        "activity_last_3_days_steps": [2400, 1800, 2100],
        "truth_boundary": "Synthetic demo data; not a diagnosis or treatment order.",
    }


def allowed_patient_actions() -> dict:
    """Return the action classes that HealthIA ONE may perform without clinical overreach."""

    return {
        "allowed": [
            "explain patient-provided information",
            "record measurements",
            "create a follow-up mission",
            "prepare questions for a professional",
            "recommend an appropriate level of care using deterministic safety rules",
        ],
        "requires_professional": [
            "confirm diagnosis",
            "prescribe or change medication",
            "interpret an emergency as safe",
            "sign clinical orders",
        ],
    }


historian = LlmAgent(
    name="historia",
    model=model(),
    description="Builds the patient-authorized longitudinal context without inventing facts.",
    instruction=(
        "You are HISTORIA. Use patient_snapshot when longitudinal context is needed. Separate "
        "confirmed facts, patient-reported facts, model inference, and missing information. "
        "Never expose or infer data outside the synthetic authorized snapshot."
    ),
    tools=[patient_snapshot],
)

sentinel = LlmAgent(
    name="sentinel",
    model=model(),
    description="Checks safety signals and decides whether routine conversation must stop.",
    instruction=(
        "You are SENTINEL. Identify red flags and abnormal measurements conservatively. Use "
        "allowed_patient_actions. Do not diagnose. If urgent symptoms are present, direct the "
        "patient to immediate human care and stop routine coaching."
    ),
    tools=[allowed_patient_actions],
)

lumen = LlmAgent(
    name="lumen",
    model=model(),
    description="Explains results and health information in plain language.",
    instruction=(
        "You are LUMEN. Explain what a result measures, what it may and may not mean, what context "
        "is missing, and what questions to ask. Never claim a diagnosis from one value."
    ),
)

vita = LlmAgent(
    name="vita",
    model=model(),
    description="Builds low-risk, realistic lifestyle micro-plans around patient barriers.",
    instruction=(
        "You are VITA. Ask about barriers before suggesting a small behavior goal. Never shame the "
        "patient and never replace a professional treatment plan."
    ),
)

navigator = LlmAgent(
    name="navigator",
    model=model(),
    description="Keeps health missions, measurements, results, and follow-up from being lost.",
    instruction=(
        "You are NAVIGATOR. Convert the situation into a clear next step, follow-up point, and "
        "closure condition. Distinguish what the patient can do from what needs a professional."
    ),
)

root_agent = LlmAgent(
    name="kira_health",
    model=model(),
    description="Patient health continuity coordinator that delegates to the minimum specialist team.",
    instruction=(
        "You are KIRA Health, coordinator of HealthIA ONE. The patient owns the context. Select the "
        "minimum specialist needed: HISTORIA for longitudinal context, SENTINEL for safety, LUMEN "
        "for explanation, VITA for lifestyle barriers, and NAVIGATOR for continuity. Be proactive "
        "only with authorized data. Explain why you intervened. You are not a doctor or emergency "
        "service; do not confirm diagnoses, prescribe, or change treatment. Keep private model "
        "reasoning hidden and expose only public actions, evidence, uncertainty, and next steps."
    ),
    sub_agents=[historian, sentinel, lumen, vita, navigator],
    tools=[patient_snapshot, allowed_patient_actions],
)

app = App(name="healthia_agent", root_agent=root_agent)
