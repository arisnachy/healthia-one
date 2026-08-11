from __future__ import annotations

from pathlib import Path

from healthia_one.google_mission_chat import should_consider_google_mission
from healthia_one.models import ChatMessage, PatientState

ROOT = Path(__file__).resolve().parents[1]


def _state_with_google_mission() -> PatientState:
    state = PatientState()
    state.messages.extend(
        [
            ChatMessage(role="patient", author="Patient", content="Busca una clínica cerca de Santiago."),
            ChatMessage(
                role="assistant",
                author="HealthIA",
                content="Encontré tres opciones verificables. ¿Cuál prefieres?",
                metadata={
                    "google_mission_id": "gmission_demo",
                    "google_mission_state": "awaiting_selection",
                    "google_mission_next_action": "patient_or_context_selects_candidate",
                },
            ),
        ]
    )
    return state


def test_active_google_mission_understands_ordinal_correction() -> None:
    state = _state_with_google_mission()
    assert should_consider_google_mission(state, "No, la segunda") is True
    assert should_consider_google_mission(state, "the second one") is True


def test_active_google_mission_understands_natural_continuation() -> None:
    state = _state_with_google_mission()
    assert should_consider_google_mission(state, "Ese me sirve") is True
    assert should_consider_google_mission(state, "continúa con eso") is True
    assert should_consider_google_mission(state, "go ahead with that") is True


def test_explicit_clinical_topic_switch_outranks_old_google_mission() -> None:
    state = _state_with_google_mission()
    assert should_consider_google_mission(state, "No, hablaba de mi presión") is False
    assert should_consider_google_mission(state, "abre el resultado de laboratorio") is False


def test_no_google_mission_means_generic_pronoun_is_not_hijacked() -> None:
    state = PatientState()
    assert should_consider_google_mission(state, "la segunda") is False
    assert should_consider_google_mission(state, "continúa con eso") is False


def test_adk_autonomy_and_execution_receipt_are_locked_to_real_events() -> None:
    adk = (ROOT / "healthia_one/google_mission_adk.py").read_text(encoding="utf-8")
    chat = (ROOT / "healthia_one/google_mission_chat.py").read_text(encoding="utf-8")

    assert "continue through every verifiable read-only or non-mutating step" in adk
    assert "Stop immediately at the first real human/external boundary" in adk
    assert 'executed_tools: list[str] = []' in adk
    assert 'getattr(part, "function_call", None)' in adk
    assert 'payload["_execution"]' in adk
    assert '"public_action_receipt": receipt' in chat
    assert '"requires_human_authorization": requires_auth' in chat
    assert 'action="advance_google_health_mission"' in chat
    assert '### Comprobante de misión' in chat
    assert 'content = f"{content}\\n\\n{_receipt_markdown(receipt)}"' in chat
    assert "HealthIA no ejecutó ese paso por su cuenta" in chat
