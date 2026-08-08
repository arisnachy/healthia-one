from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_clinical_adk_runtime_is_bounded_and_structured() -> None:
    runtime = (ROOT / "healthia_one/adk_runtime.py").read_text(encoding="utf-8")

    assert 'tools=[inspect_clinical_baseline]' in runtime
    assert 'maximum_adk_function_calls": 1' in runtime
    assert "types.GenerateContentConfig(" in runtime
    assert 'types.ThinkingConfig(thinking_level="minimal")' in runtime
    assert "max_output_tokens = self.settings.ai_max_output_tokens" in runtime
    assert 'response_mime_type="application/json"' in runtime
    assert "response_json_schema=CLINICAL_PLAN_JSON_SCHEMA" in runtime
    assert '"structured_output_required": True' in runtime
    assert '"structured_output": True' in runtime
    assert '"thinking_level": "minimal"' in runtime
    assert '"function_call_count": baseline_calls' in runtime
    assert "is_final_response" in runtime


def test_clinical_schema_requires_five_compact_patient_questions() -> None:
    runtime = (ROOT / "healthia_one/adk_runtime.py").read_text(encoding="utf-8")

    assert '"questions": {' in runtime
    assert '"minItems": 5' in runtime
    assert '"maxItems": 5' in runtime
    assert '"maxItems": 2' in runtime
    assert '"maxItems": 3' in runtime
    assert '"maxItems": 5' in runtime
    assert '"required": ["id", "prompt", "options", "multiple", "detail_placeholder"]' in runtime
    assert '"selected_specialists"' not in runtime.split("CLINICAL_PLAN_JSON_SCHEMA", 1)[1].split("ADK_CLINICAL_INSTRUCTION", 1)[0]


def test_json_parser_reports_truncated_or_invalid_structured_output() -> None:
    runtime = (ROOT / "healthia_one/adk_runtime.py").read_text(encoding="utf-8")

    # Internal diagnostics are developer-facing and must describe the failure
    # precisely; they are not patient-visible UI and therefore should not be
    # locked to either English or Spanish wording.
    assert "incomplete or invalid structured JSON" in runtime
    assert "did not return a structured JSON object" in runtime
    assert 'f"(chars={len(value)}, pos={nested.pos}, error={nested.msg})"' in runtime