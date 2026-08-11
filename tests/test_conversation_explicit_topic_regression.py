from __future__ import annotations

from healthia_one.conversation_brain import build_frame, explicit_topic
from healthia_one.models import PatientState
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


def test_consultation_is_explicit_topic_not_unanchored_short_followup() -> None:
    frame = build_frame(PatientState(), "Prepara mi próxima consulta médica")
    assert explicit_topic("Prepara mi próxima consulta médica") == "appointments"
    assert frame.current_topic == "appointments"
    assert frame.reference_status == "explicit_current_topic"
    assert frame.needs_clarification is False


def test_existing_consultation_preparation_route_survives_conversation_brain_hardening() -> None:
    response = respond(seed_state(), "Prepara mi próxima consulta médica")
    assert response.mission is not None
    assert response.mission.mission_type == "consultation_preparation"


def test_short_standalone_command_is_not_treated_as_ellipsis() -> None:
    frame = build_frame(PatientState(), "Abre mi perfil")
    assert frame.ambiguous_reference is False
    assert frame.needs_clarification is False


def test_reference_signal_it_does_not_match_inside_spanish_words() -> None:
    frame = build_frame(PatientState(), "Prepara mi cita")
    assert frame.current_topic == "appointments"
    assert frame.ambiguous_reference is False
    assert frame.needs_clarification is False


def test_real_short_ellipsis_remains_context_dependent() -> None:
    frame = build_frame(PatientState(), "¿Y mañana?")
    assert frame.ambiguous_reference is True
    assert frame.needs_clarification is True
