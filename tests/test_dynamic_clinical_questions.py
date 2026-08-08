import asyncio
import json
from types import SimpleNamespace

from healthia_one.config import Settings
from healthia_one.gemini import GeminiResponder
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


DYNAMIC_URINARY_PLAN = {
    "intent": "clinical_consultation",
    "clinical_focus": "Distinguir irritación urinaria baja de un cuadro con posible compromiso alto o causa genital",
    "why_these_questions": [
        "La localización y el patrón del dolor cambian el nivel de atención",
        "Fiebre alta, vómitos o empeoramiento rápido requieren otra dirección",
    ],
    "missing_information": ["características de la orina", "posibilidad de embarazo", "síntomas genitales"],
    "selected_specialists": [
        {"role": "interview", "reason": "aclarar síntomas discriminativos"},
        {"role": "safety", "reason": "descartar señales de alarma"},
        {"role": "medication", "reason": "revisar alergias y lo ya utilizado"},
    ],
    "questions": [
        {
            "id": "dolor_localizacion",
            "prompt": "¿Dónde sientes la molestia con mayor claridad?",
            "options": ["Solo al orinar", "Parte baja del abdomen", "Espalda o costado", "Zona genital"],
            "multiple": True,
            "detail_placeholder": "Indica el lado y si el dolor se desplaza",
        },
        {
            "id": "orina_cambios",
            "prompt": "¿Has notado cambios visibles u olor diferente en la orina?",
            "options": ["Sin cambios", "Orina turbia", "Sangre visible", "Olor más fuerte"],
            "multiple": True,
            "detail_placeholder": "Describe cuándo comenzó el cambio",
        },
        {
            "id": "alarma_urinaria",
            "prompt": "¿Ha ocurrido alguna señal de alarma desde que empezó?",
            "options": ["Ninguna", "Fiebre alta o escalofríos", "Vómitos repetidos", "Empeoramiento rápido"],
            "multiple": True,
            "detail_placeholder": "Describe la señal y cuándo ocurrió",
        },
        {
            "id": "contexto_genital",
            "prompt": "¿Hay flujo, irritación genital o una posibilidad de embarazo?",
            "options": ["No", "Flujo o irritación", "Embarazo posible", "No estoy segura"],
            "multiple": True,
            "detail_placeholder": "Agrega un detalle si aplica",
        },
        {
            "id": "episodios_previos",
            "prompt": "¿Tuviste antes un episodio parecido y cómo se confirmó?",
            "options": ["Nunca", "Sí, sin estudios", "Sí, con análisis de orina", "No lo recuerdo"],
            "multiple": False,
            "detail_placeholder": "Indica cuándo ocurrió y qué te dijeron",
        },
    ],
}


class FakeInteractions:
    def __init__(self, payload) -> None:
        self.calls = []
        self.payload = payload

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output = self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)
        return SimpleNamespace(outputs=[SimpleNamespace(text=output)])


class FakeClient:
    def __init__(self, payload) -> None:
        self.interactions = FakeInteractions(payload)


def guarded_settings(**overrides) -> Settings:
    values = {
        "llm_backend": "gemini_api",
        "model": "gemini-3.6-flash",
        "cost_mode": "guarded",
        "ai_request_limit": 4,
        "cost_guard_start_enabled": True,
        "ai_max_output_tokens": 1400,
    }
    values.update(overrides)
    return Settings(**values)


def test_gemini_fills_empty_ai_scaffold_with_case_specific_questions(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = FakeClient(DYNAMIC_URINARY_PLAN)
    responder = GeminiResponder(guarded_settings(), client_factory=lambda: client)
    state = seed_state()
    complaint = "Desde ayer me arde al orinar y tengo que ir al baño a cada rato"
    draft = respond(state, complaint)

    original_prompts = [item["prompt"] for item in draft.message.metadata["clinical_interview"]["question_block"]["questions"]]
    assert original_prompts == []
    result = asyncio.run(responder.enhance(state, complaint, draft))
    interview = result.message.metadata["clinical_interview"]
    prompts = [item["prompt"] for item in interview["question_block"]["questions"]]

    assert prompts == [item["prompt"] for item in DYNAMIC_URINARY_PLAN["questions"]]
    assert interview["question_source"] == "gemini_dynamic"
    assert result.message.metadata["llm_status"] == "dynamic_clinical_questions"
    assert result.message.metadata["judge_review"]["approved"] is True
    assert result.message.metadata["judge_review"]["score"] >= 80
    assert result.message.metadata["agent_execution"] == "on_demand"
    assert 2 <= len(result.message.agent_plan) <= 4
    assert {step.agent for step in result.message.agent_plan} == {"INTERVIEWER", "SENTINEL", "MEDSAFE"}
    assert len(client.interactions.calls) == 1
    assert client.interactions.calls[0]["store"] is False
    assert client.interactions.calls[0]["generation_config"]["thinking_level"] == "minimal"
    assert result.message.metadata["cost_guard"]["requests_used"] == 1


def test_ai_off_never_invents_or_reveals_prefabricated_questions(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = FakeClient(DYNAMIC_URINARY_PLAN)
    responder = GeminiResponder(
        guarded_settings(cost_guard_start_enabled=False),
        client_factory=lambda: client,
    )
    state = seed_state()
    complaint = "Desde ayer me arde al orinar y tengo frecuencia urinaria"
    draft = respond(state, complaint)
    result = asyncio.run(responder.enhance(state, complaint, draft))
    interview = result.message.metadata["clinical_interview"]

    assert client.interactions.calls == []
    assert interview["question_block"]["questions"] == []
    assert interview["question_block"]["generation_required"] is True
    assert result.message.metadata["llm_status"] == "cost_guard_blocked"
    assert result.message.metadata["agent_execution"] == "on_demand"
    assert 2 <= len(result.message.agent_plan) <= 4
    assert result.message.metadata["judge_review"]["verdict"] == "SAFE_FALLBACK_NOT_HACKATHON_EVIDENCE"


def test_judge_rejects_bad_dynamic_block_without_substituting_static_form(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    bad = dict(DYNAMIC_URINARY_PLAN)
    bad["questions"] = [dict(DYNAMIC_URINARY_PLAN["questions"][0]) for _ in range(5)]
    client = FakeClient(bad)
    responder = GeminiResponder(guarded_settings(), client_factory=lambda: client)
    state = seed_state()
    complaint = "Desde ayer me arde al orinar y tengo frecuencia urinaria"
    draft = respond(state, complaint)
    original = draft.message.metadata["clinical_interview"]["question_block"]
    assert original["questions"] == []
    result = asyncio.run(responder.enhance(state, complaint, draft))

    assert len(client.interactions.calls) == 1
    assert result.message.metadata["llm_status"] == "clinical_safe_fallback"
    assert result.message.metadata["clinical_interview"]["question_block"]["questions"] == []
    assert result.message.metadata["clinical_interview"]["question_block"]["generation_required"] is True
    assert result.message.metadata["judge_review"]["verdict"] == "SAFE_FALLBACK_NOT_HACKATHON_EVIDENCE"
    assert result.message.metadata["cost_guard"]["requests_used"] == 1


def test_compact_prompt_does_not_send_full_chat_or_every_specialist(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = FakeClient(DYNAMIC_URINARY_PLAN)
    responder = GeminiResponder(guarded_settings(), client_factory=lambda: client)
    state = seed_state()
    complaint = "Desde ayer me arde al orinar y tengo frecuencia urinaria"
    draft = respond(state, complaint)
    asyncio.run(responder.enhance(state, complaint, draft))

    payload = json.loads(client.interactions.calls[0]["input"])
    assert payload["task"] == "generate_next_adaptive_clinical_question_block"
    assert "messages" not in payload
    assert "family_members" not in payload["authorized_clinical_context"]
    assert payload["constraints"]["single_model_call"] is True
    assert payload["constraints"]["maximum_selected_specialists"] == 4
