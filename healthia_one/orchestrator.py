from __future__ import annotations

from healthia_one.clinical_intake import respond_to_clinical_intake
from healthia_one.deterministic_router import respond as deterministic_respond
from healthia_one.models import ChatResponse, PatientState


def _explicit_clinical_request(text: str) -> bool:
    normalized = text.lower().strip()
    if any(exclusion in normalized for exclusion in ("preparar mi consulta", "prepara mi consulta", "próxima consulta", "proxima consulta", "agendar", "cita")):
        return False
    return any(
        phrase in normalized
        for phrase in (
            "quiero hacer una consulta",
            "quiero iniciar una consulta",
            "necesito una consulta médica",
            "necesito una consulta medica",
            "quiero consultar por mi salud",
            "quiero que me evalúes",
            "quiero que me evalues",
        )
    )


def respond(state: PatientState, patient_text: str) -> ChatResponse:
    """Route the visible patient workflow through safety-bound clinical intake first.

    Symptom consultations and explicit requests to start a clinical consultation
    receive a structured two-block interview and internal clinical council. All
    other intents retain the verified deterministic domain router.
    """

    clinical_response = respond_to_clinical_intake(state, patient_text)
    if clinical_response is not None:
        return clinical_response

    if _explicit_clinical_request(patient_text):
        clinical_response = respond_to_clinical_intake(
            state,
            f"Paciente presenta una molestia no especificada y solicita consulta: {patient_text}",
        )
        if clinical_response is not None:
            interview = clinical_response.message.metadata.get("clinical_interview", {})
            interview["chief_complaint"] = patient_text
            return clinical_response

    return deterministic_respond(state, patient_text)
