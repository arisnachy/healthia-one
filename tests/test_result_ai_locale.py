from healthia_one.language import bind_requested_locale, reset_requested_locale
from healthia_one.models import HealthResult
from healthia_one.result_ai import apply_multimodal_analysis


def test_multimodal_result_explanation_respects_english_request_locale() -> None:
    token = bind_requested_locale("en-US")
    try:
        result = HealthResult(filename="synthetic-lab.pdf", status="pending_multimodal")
        parsed = apply_multimodal_analysis(
            result,
            {
                "status": "parsed",
                "response_locale": "en",
                "panel": "Synthetic lab",
                "observations": [
                    {"name": "Glucose", "value": 103, "unit": "mg/dL", "reference": "70-99"},
                ],
                "findings": ["Glucose is visible in the uploaded report."],
                "limitations": ["Synthetic demonstration document."],
                "patient_explanation": "The report contains a readable glucose value.",
                "requires_professional_review": True,
            },
        )
    finally:
        reset_requested_locale(token)

    assert parsed.status == "parsed"
    assert parsed.explained is True
    assert "Limitations:" in parsed.explanation
    assert "This analysis organizes the uploaded evidence" in parsed.explanation
    assert "Este análisis" not in parsed.explanation
    assert any(item.name == "Finding" for item in parsed.items)


def test_multimodal_pending_boundary_respects_english_request_locale() -> None:
    token = bind_requested_locale("en")
    try:
        result = HealthResult(filename="scan.pdf", status="pending_multimodal")
        pending = apply_multimodal_analysis(
            result,
            {
                "status": "pending",
                "response_locale": "en",
                "detail": "The model did not finish reading this file.",
            },
        )
    finally:
        reset_requested_locale(token)

    assert "The original file is saved" in pending.explanation
    assert "HealthIA will not invent findings" in pending.explanation
    assert "El archivo original" not in pending.explanation
