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
        "medications": [
            {
                "name": "Losartán",
                "strength": "50 mg",
                "schedule": "cada 24 horas",
                "purpose": "Control de presión arterial",
            }
        ],
        "latest_weight_kg": 80.4,
        "previous_weight_kg": 78.0,
        "latest_blood_pressure": "148/92",
        "activity_last_3_days_steps": [2400, 1800, 2100],
        "next_appointment": "Consulta de medicina familiar in 40 hours (synthetic)",
        "family_history": {
            "maternal": ["madre con diabetes", "abuela con diabetes"],
            "paternal": ["padre con hipertensión"],
            "siblings": ["hermano con hipertensión"],
        },
        "truth_boundary": (
            "Synthetic demo data. The system may organize and explain but cannot diagnose, change "
            "medication, or predict hereditary disease."
        ),
    }


def allowed_patient_actions() -> dict:
    return {
        "allowed": [
            "explain patient-provided information",
            "record measurements and medication check-ins",
            "create a follow-up mission",
            "prepare questions and a consultation brief",
            "organize patient-authorized documents",
            "summarize authorized family history",
            "recommend a level of human care using deterministic safety rules",
        ],
        "requires_professional": [
            "confirm diagnosis",
            "prescribe, stop, duplicate, or change medication",
            "predict that a hereditary disease will occur",
            "interpret an emergency as safe",
            "sign clinical orders",
        ],
    }


historian = LlmAgent(
    name="historia",
    model=model(),
    description="Builds patient-authorized longitudinal context without inventing facts.",
    instruction=(
        "Use patient_snapshot. Separate confirmed facts, patient reports, inference, and missing data. "
        "Never expose information outside the authorized synthetic snapshot."
    ),
    tools=[patient_snapshot],
)

sentinel = LlmAgent(
    name="sentinel",
    model=model(),
    description="Checks safety signals and stops routine flow when human care is required.",
    instruction=(
        "Apply safety conservatively. Do not diagnose. Do not permit medication changes. For urgent "
        "symptoms, direct the patient to immediate human care and stop routine coaching."
    ),
    tools=[allowed_patient_actions],
)

lumen = LlmAgent(
    name="lumen",
    model=model(),
    description="Explains results and health information in plain language.",
    instruction="Explain meaning, limits, missing context, and questions. Never diagnose from one value.",
)

vita = LlmAgent(
    name="vita",
    model=model(),
    description="Builds realistic low-risk lifestyle micro-plans around patient barriers.",
    instruction="Ask about barriers before suggesting a small goal. Never shame or replace treatment.",
)

navigator = LlmAgent(
    name="navigator",
    model=model(),
    description="Keeps missions, measurements, results, appointments, and follow-up from being lost.",
    instruction="Define a next step, follow-up point, and closure condition for every active mission.",
)

hereditas = LlmAgent(
    name="hereditas",
    model=model(),
    description="Organizes the pathological genogram and family-history questions.",
    instruction=(
        "Use only authorized family history. Organize lineage, relationship, conditions, age at diagnosis, "
        "and confidence. Never present family aggregation as diagnosis or disease prediction."
    ),
    tools=[patient_snapshot, allowed_patient_actions],
)

archivum = LlmAgent(
    name="archivum",
    model=model(),
    description="Indexes and relates patient documents without fabricating unread content.",
    instruction=(
        "Organize documents by type, date, source, provenance and review state. Never invent text from "
        "an unread PDF or image and never expose documents outside patient scope."
    ),
    tools=[patient_snapshot],
)

medsafe = LlmAgent(
    name="medsafe",
    model=model(),
    description="Organizes treatment and patient-reported adherence within strict medication safety limits.",
    instruction=(
        "Use the exact registered plan. You may record taken, late, skipped, or unknown status, explain the "
        "documented purpose, and prepare questions. Never tell the patient to double, stop, substitute, or "
        "change a dose. Escalate uncertainty to a pharmacist or prescribing professional."
    ),
    tools=[patient_snapshot, allowed_patient_actions],
)

advocate = LlmAgent(
    name="advocate",
    model=model(),
    description="Prepares a concise patient-controlled consultation brief and prioritized questions.",
    instruction=(
        "Summarize changes, measurements, results, treatment, family context, documents, patient goals, "
        "and questions. Mark source and uncertainty. The patient must review before sharing."
    ),
    tools=[patient_snapshot],
)

root_agent = LlmAgent(
    name="kira_health",
    model=model(),
    description="Patient health continuity coordinator that delegates to the minimum specialist team.",
    instruction=(
        "You are KIRA Health. The patient owns the context. Select the minimum specialist: HISTORIA for "
        "longitudinal context, SENTINEL for safety, LUMEN for results, VITA for barriers, NAVIGATOR for "
        "continuity, HEREDITAS for family history, ARCHIVUM for documents, MEDSAFE for treatment safety, "
        "and ADVOCATE for consultation preparation. Be proactive only with authorized data and explain why. "
        "Do not diagnose, prescribe, change medication, or predict hereditary disease. Expose public actions, "
        "evidence, uncertainty, and next steps—not private reasoning."
    ),
    sub_agents=[historian, sentinel, lumen, vita, navigator, hereditas, archivum, medsafe, advocate],
    tools=[patient_snapshot, allowed_patient_actions],
)

app = App(name="healthia_agent", root_agent=root_agent)
