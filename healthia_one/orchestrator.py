from __future__ import annotations

from healthia_one.clinical_intake import respond_to_clinical_intake
from healthia_one.deterministic_router import respond as deterministic_respond
from healthia_one.models import ChatResponse, PatientState


def respond(state: PatientState, patient_text: str) -> ChatResponse:
    """Route the visible patient workflow through safety-bound clinical intake first.

    Symptom consultations receive a structured two-block interview and internal
    clinical council. All other intents retain the verified deterministic domain
    router. The public surface never exposes private reasoning or internal names.
    """

    clinical_response = respond_to_clinical_intake(state, patient_text)
    if clinical_response is not None:
        return clinical_response
    return deterministic_respond(state, patient_text)
