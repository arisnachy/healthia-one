from __future__ import annotations

from healthia_one.clinical_intake import detect_clinical_consultation
from healthia_one.models import ChatMessage, PatientState
from healthia_one.orchestrator import respond

COMPLAINT = (
    "Since yesterday I have burning pain when I urinate and I need to go very often. "
    "Help me understand what information is still missing."
)

def _persist_exchange(state: PatientState, patient_text: str, response) -> None:
    state.messages.append(ChatMessage(role="patient", author="Patient", content=patient_text))
    state.messages.append(response.message)

def test_natural_english_urinary_complaint_is_detected_without_translation_hint() -> None:
    is_clinical, domain = detect_clinical_consultation(COMPLAINT)
    assert is_clinical is True
    assert domain == "urinary"

def test_clarification_turn_cannot_demote_next_explicit_english_symptom_turn() -> None:
    state = PatientState()
    first = respond(state, "What about that?")
    assert first.message.metadata["reference_clarification_required"] is True
    _persist_exchange(state, "What about that?", first)
    second = respond(state, COMPLAINT)
    assert second.message.metadata["intent"] == "clinical_consultation"
    interview = second.message.metadata["clinical_interview"]
    assert interview["status"] == "awaiting_answers"
    assert interview["domain"] == "urinary"
    assert interview["question_block"]["generation_required"] is True
    assert second.message.metadata.get("reference_clarification_required") is not True
