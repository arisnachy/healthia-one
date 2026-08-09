import asyncio
import json
import os

from fastapi.testclient import TestClient

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"

from healthia_one.clinical_planner import (
    extract_known_clinical_facts,
    judge_dynamic_plan,
    normalize_dynamic_question_block,
    repeats_explicit_location_fact,
)
from healthia_one.clinical_intake import ANSWER_PREFIX
from healthia_one.config import Settings
from healthia_one.gemini import GeminiResponder
from healthia_one.models import MissionStatus
from healthia_one.orchestrator import respond
from healthia_one.service import HealthIAService
from app.main import app


def _neck_block(first_prompt: str) -> dict:
    return {
        "clinical_focus": "Aclarar dolor cervical",
        "why_these_questions": ["Distinguir un dato relevante"],
        "questions": [
            {"id": "location", "prompt": first_prompt, "options": ["Cuello", "Hombro", "Espalda"], "multiple": False},
            {"id": "radiation", "prompt": "¿El dolor se irradia hacia un brazo o la cabeza?", "options": ["No", "Hacia un brazo", "Hacia la cabeza"], "multiple": False},
            {"id": "trigger", "prompt": "¿Qué movimiento o postura lo empeora más?", "options": ["Girar", "Mirar hacia abajo", "No identifico uno"], "multiple": False},
            {"id": "alarm", "prompt": "¿Ha aparecido debilidad, entumecimiento o empeoramiento rápido?", "options": ["No", "Debilidad", "Entumecimiento"], "multiple": True},
            {"id": "impact", "prompt": "¿Cómo limita tus actividades habituales?", "options": ["No las limita", "Las limita un poco", "Las limita mucho"], "multiple": False},
        ],
    }


def test_explicit_neck_location_blocks_generic_location_repeat() -> None:
    known_facts = extract_known_clinical_facts("Tengo dolor de cuello desde ayer")
    assert known_facts["explicit_body_locations"] == ["cuello"]
    assert repeats_explicit_location_fact({"prompt": "¿Dónde te duele?"}, known_facts) is True
    assert repeats_explicit_location_fact(
        {"prompt": "¿Además del cuello, el dolor se extiende a otro lugar?"}, known_facts
    ) is False


def test_judge_rejects_generic_location_repeat_and_questions_keep_free_text() -> None:
    payload = _neck_block("¿Dónde te duele?")
    block = normalize_dynamic_question_block(payload, 1)
    review = judge_dynamic_plan(
        block,
        chief_complaint="Tengo dolor de cuello desde ayer",
        previous_answers=[],
        agent_plan=[],
        model_payload=payload,
    )
    assert review["approved"] is False
    assert any("localización" in item for item in review["blockers"])
    assert all(question["allow_detail"] is True for question in block["questions"])


def test_new_consultation_preserves_record_and_closes_only_unfinished_interview() -> None:
    service = HealthIAService(Settings(llm_backend="mock", store_backend="memory", proactive_enabled=False))
    state = asyncio.run(service.snapshot())
    original_vitals = len(state.vitals)
    original_documents = len(state.documents)
    original_messages = len(state.messages)
    draft = respond(state, "Tengo dolor de cuello desde ayer")
    state.messages.append(draft.message)
    asyncio.run(service.store.save(state))

    message = asyncio.run(service.start_new_consultation())
    saved = asyncio.run(service.snapshot())
    interview = next(item for item in saved.missions if item.id == draft.mission.id)

    assert message.metadata["preserves_longitudinal_record"] is True
    assert message.metadata["conversation_id"].startswith("consultation_")
    assert len(saved.vitals) == original_vitals
    assert len(saved.documents) == original_documents
    assert len(saved.messages) == original_messages + 2
    assert interview.status == MissionStatus.CANCELLED
    assert "superseded_by_new_consultation" in interview.closure_evidence
    previous_interview = saved.messages[-2].metadata["clinical_interview"]
    assert previous_interview["status"] == "cancelled"


def test_new_consultation_api_preserves_bootstrap_record() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        before = client.get("/api/bootstrap").json()
        response = client.post("/api/consultations/new")
        after = client.get("/api/bootstrap").json()

    assert response.status_code == 200
    payload = response.json()
    assert payload["preserves_longitudinal_record"] is True
    assert payload["conversation_id"] == payload["message"]["metadata"]["conversation_id"]
    assert len(after["vitals"]) == len(before["vitals"])
    assert len(after["documents"]) == len(before["documents"])
    assert len(after["messages"]) == len(before["messages"]) + 1


def test_social_turns_are_human_deterministic_and_never_start_an_interview() -> None:
    service = HealthIAService(Settings(llm_backend="mock", store_backend="memory"))
    state = asyncio.run(service.snapshot())
    for text in ("Hola, ¿cómo vas?", "¿Cómo estás hoy?", "Gracias por tu ayuda", "Hasta luego", "Hello, how are you?", "Thank you", "See you"):
        response = respond(state, text)
        assert response.message.metadata["intent"] == "social_small_talk"
        assert response.message.metadata["skip_llm"] == "deterministic_social"
        assert "clinical_interview" not in response.message.metadata
        assert response.mission is None


def test_social_turn_skips_gemini_even_when_a_client_is_configured() -> None:
    service = HealthIAService(Settings(llm_backend="mock", store_backend="memory"))
    state = asyncio.run(service.snapshot())
    draft = respond(state, "Hello, how are you today?")
    responder = GeminiResponder(
        Settings(llm_backend="gemini_api", store_backend="memory", cost_mode="guarded", ai_request_limit=1, cost_guard_start_enabled=True),
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("Gemini must not be called for social talk")),
    )

    result = asyncio.run(responder.enhance(state, "Hello, how are you today?", draft))

    assert result.message.metadata["llm_status"] == "deterministic_social"
    assert result.message.metadata["llm_skipped"] is True
    assert result.message.metadata["cost_guard"]["requests_used"] == 0


def test_social_api_skips_llm_and_clinical_intake_for_spanish_and_english() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        for text in ("Hola, ¿cómo vas?", "Gracias", "How are you today?", "Goodbye"):
            response = client.post("/api/chat", json={"message": text})
            assert response.status_code == 200
            metadata = response.json()["message"]["metadata"]
            assert metadata["intent"] == "social_small_talk"
            assert metadata["llm_status"] == "deterministic_social"
            assert metadata["llm_skipped"] is True
            assert "clinical_interview" not in metadata

    service = HealthIAService(Settings(llm_backend="mock", store_backend="memory"))
    state = asyncio.run(service.snapshot())
    symptom = respond(state, "Hola, tengo dolor de cuello")
    assert symptom.message.metadata["intent"] == "clinical_consultation"


def test_social_turn_does_not_resume_a_persisted_interview_but_structured_answer_does() -> None:
    service = HealthIAService(Settings(llm_backend="mock", store_backend="memory"))
    state = asyncio.run(service.snapshot())
    initial = respond(state, "Tengo dolor de cuello desde ayer")
    state.messages.append(initial.message)
    interview = initial.message.metadata["clinical_interview"]

    greeting = respond(state, "Hola, ¿cómo vas?")

    assert greeting.message.metadata["intent"] == "social_small_talk"
    assert "clinical_interview" not in greeting.message.metadata
    assert interview["status"] == "awaiting_answers"
    assert len(state.missions) == 1

    answer = ANSWER_PREFIX + json.dumps(
        {
            "interview_id": interview["id"],
            "stage": 1,
            "answers": [{"question_id": "trigger", "selected": ["Girar el cuello"], "detail": ""}],
        }
    )
    resumed = respond(state, answer)
    assert resumed.message.metadata["clinical_interview"]["id"] == interview["id"]
    assert resumed.message.metadata["clinical_interview"]["stage"] == 2


def test_social_api_does_not_resume_persisted_interview() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        initial = client.post("/api/chat", json={"message": "Tengo dolor de cuello desde ayer"}).json()
        assert initial["message"]["metadata"]["intent"] == "clinical_consultation"
        greeting = client.post("/api/chat", json={"message": "Hola, ¿cómo vas?"})

    assert greeting.status_code == 200
    metadata = greeting.json()["message"]["metadata"]
    assert metadata["intent"] == "social_small_talk"
    assert metadata["llm_status"] == "deterministic_social"
    assert "clinical_interview" not in metadata
