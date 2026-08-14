import json
from types import SimpleNamespace

import pytest

from healthia_one.education_video import (
    EducationPlanValidationError,
    PatientEducationVideoRouter,
    _education_system_instruction,
    _normalize_plan_payload,
)
from healthia_one.education_video_models import EducationFact
from healthia_one.models import PatientState


class FakeCostGuard:
    max_output_tokens = 1400

    def __init__(self):
        self.actions = []

    def authorize(self, action):
        self.actions.append(action)


class FakeInteractions:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(self.payload))


class FakeClient:
    def __init__(self, payload):
        self.interactions = FakeInteractions(payload)


def live_settings():
    return SimpleNamespace(llm_backend="gemini_api", adk_ready=True, model="gemini-3.5-flash")


def valid_payload():
    return {
        "title": " Understanding glucose ",
        "summary": " A short explanation ",
        "patient_fact_keys": ["result_glucose"],
        "scenes": [
            {"heading": " What glucose is ", "body": " General education. ", "narration": " Glucose is a source of energy. ", "visual_kind": "CARD"},
            {"heading": " Your result ", "body": " Your recorded value stays on a controlled card. ", "narration": " HealthIA separates your value from general education. ", "visual_kind": "card"},
            {"heading": " Follow up ", "body": " Keep the result for your next conversation. ", "narration": " Use the result to prepare questions. ", "visual_kind": "VEO", "veo_prompt": "Generic medical education animation of glucose moving through the bloodstream, no people, no text"},
        ],
    }


def test_system_prompt_explicitly_locks_scene_count_and_kind():
    prompt = _education_system_instruction("en")
    assert "between THREE and SIX education scenes" in prompt
    assert 'exactly lowercase "card" or "veo"' in prompt


def test_plan_normalizer_only_repairs_harmless_shape_variance():
    payload = valid_payload()
    normalized = _normalize_plan_payload(payload)
    assert normalized["title"] == "Understanding glucose"
    assert normalized["scenes"][0]["visual_kind"] == "card"
    assert normalized["scenes"][0]["veo_prompt"] == ""
    assert normalized["scenes"][2]["visual_kind"] == "veo"


@pytest.mark.asyncio
async def test_gemini_plan_uses_pydantic_json_schema_and_accepts_safe_normalization():
    client = FakeClient(valid_payload())
    guard = FakeCostGuard()
    router = PatientEducationVideoRouter(live_settings(), client_provider=lambda: client, cost_guard=guard)
    state = PatientState()
    facts = [EducationFact(key="result_glucose", label="Glucose", value="103 mg/dL", source_id="result_glucose", source_type="health_result")]
    plan = await router._gemini_plan(state, "glucose", "en", 60, facts)
    call = client.interactions.calls[0]
    schema = call["generation_config"]["response_json_schema"]
    assert schema["properties"]["scenes"]["minItems"] == 3
    assert schema["properties"]["scenes"]["maxItems"] == 8
    assert guard.actions == ["patient_education_video_plan"]
    assert len(plan.scenes) == 3
    assert plan.scenes[2].visual_kind == "veo"


@pytest.mark.asyncio
async def test_invalid_short_storyboard_fails_with_sanitized_validation_metadata():
    payload = valid_payload()
    payload["scenes"] = payload["scenes"][:1]
    client = FakeClient(payload)
    router = PatientEducationVideoRouter(live_settings(), client_provider=lambda: client, cost_guard=FakeCostGuard())
    with pytest.raises(EducationPlanValidationError) as raised:
        await router._gemini_plan(PatientState(), "glucose", "en", 60, [])
    assert raised.value.validation_errors
    assert any("scenes" in item["loc"] for item in raised.value.validation_errors)
    assert all("103" not in item["msg"] for item in raised.value.validation_errors)
