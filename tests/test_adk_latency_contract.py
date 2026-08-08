from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_clinical_adk_runtime_is_bounded_and_structured() -> None:
    runtime = (ROOT / "healthia_one/adk_runtime.py").read_text(encoding="utf-8")

    assert 'tools=[inspect_clinical_baseline]' in runtime
    assert 'maximum_adk_function_calls": 1' in runtime
    assert "types.GenerateContentConfig(" in runtime
    assert 'types.ThinkingConfig(thinking_level="minimal")' in runtime
    assert "max_output_tokens = min(self.settings.ai_max_output_tokens, 1100)" in runtime
    assert 'response_mime_type="application/json"' in runtime
    assert "response_json_schema=CLINICAL_PLAN_JSON_SCHEMA" in runtime
    assert '"structured_output_required": True' in runtime
    assert '"structured_output": True' in runtime
    assert '"thinking_level": "minimal"' in runtime
    assert '"function_call_count": baseline_calls' in runtime


def test_clinical_schema_requires_five_patient_questions() -> None:
    runtime = (ROOT / "healthia_one/adk_runtime.py").read_text(encoding="utf-8")

    assert '"questions": {' in runtime
    assert '"minItems": 5' in runtime
    assert '"maxItems": 5' in runtime
    assert '"required": ["id", "prompt", "options", "multiple", "detail_placeholder"]' in runtime
