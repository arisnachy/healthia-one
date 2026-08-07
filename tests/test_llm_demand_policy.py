from __future__ import annotations

from pathlib import Path

from healthia_one.deterministic_router import respond
from healthia_one.llm_policy import should_use_patient_chat_model
from healthia_one.models import ChatMessage, ChatResponse, RiskLevel
from healthia_one.service import seed_state


ROOT = Path(__file__).resolve().parents[1]


def test_resolved_domain_actions_do_not_need_a_second_model_call() -> None:
    state = seed_state()
    for message in (
        "Muéstrame mi tratamiento",
        "Organiza mis documentos",
        "Prepara mi próxima cita",
        "Enséñame mi línea de tiempo",
        "Muéstrame mi genograma familiar",
    ):
        draft = respond(state, message)
        assert draft.message.metadata.get("action_target")
        assert should_use_patient_chat_model(message, draft) is False


def test_short_social_messages_stay_local() -> None:
    draft = ChatResponse(message=ChatMessage(role="assistant", author="HealthIA", content="Hola"))
    assert should_use_patient_chat_model("Hola", draft) is False
    assert should_use_patient_chat_model("Muchas gracias!", draft) is False


def test_free_form_unresolved_chat_can_use_one_model_call() -> None:
    draft = ChatResponse(message=ChatMessage(role="assistant", author="HealthIA", content="Borrador"))
    assert should_use_patient_chat_model("No sé exactamente qué necesito, ayúdame a ordenar lo que cambió esta semana", draft) is True


def test_clinical_interview_remains_model_eligible_but_urgent_safety_never_is() -> None:
    clinical = ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="HealthIA",
            content="Preguntas",
            metadata={"clinical_interview": {"stage": 1}},
        )
    )
    assert should_use_patient_chat_model("me arde al orinar", clinical) is True

    urgent = ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="HealthIA",
            content="Urgente",
            risk_level=RiskLevel.URGENT,
            metadata={"clinical_interview": {"stage": 1}},
        )
    )
    assert should_use_patient_chat_model("dolor de pecho intenso", urgent) is False


def test_service_enforces_demand_policy_before_gemini_enhancement() -> None:
    source = (ROOT / "healthia_one" / "service.py").read_text(encoding="utf-8")
    assert "should_use_patient_chat_model(content, response)" in source
    assert '"llm_status": "not_needed"' in source
    assert '"model_call_saved": True' in source
