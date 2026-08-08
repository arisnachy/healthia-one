from healthia_one.result_ai import (
    MULTIMODAL_TIMEOUT_SECONDS,
    RESULT_ANALYSIS_JSON_SCHEMA,
    _media_input,
    _multimodal_timeout_seconds,
)


class _Settings:
    llm_timeout_seconds = 30


class _Responder:
    settings = _Settings()


def test_pdf_uses_low_resolution_to_reduce_gemini3_media_latency() -> None:
    payload = _media_input("laboratorio.pdf", "application/pdf", b"%PDF-test")

    assert payload["type"] == "document"
    assert payload["mime_type"] == "application/pdf"
    assert payload["resolution"] == "low"
    assert payload["data"]


def test_clinical_images_keep_high_resolution_fidelity() -> None:
    payload = _media_input("rx-torax.png", "image/png", b"png-test")

    assert payload["type"] == "image"
    assert payload["mime_type"] == "image/png"
    assert payload["resolution"] == "high"


def test_multimodal_timeout_is_separate_from_interactive_chat_timeout() -> None:
    assert MULTIMODAL_TIMEOUT_SECONDS == 45
    assert _multimodal_timeout_seconds(_Responder()) == 45


def test_multimodal_schema_is_compact_but_preserves_clinical_signal() -> None:
    properties = RESULT_ANALYSIS_JSON_SCHEMA["properties"]
    required = set(RESULT_ANALYSIS_JSON_SCHEMA["required"])

    assert {"document_type", "panel", "observations", "findings", "patient_explanation"} <= required
    assert properties["observations"]["maxItems"] == 20
    assert properties["findings"]["maxItems"] == 10
    assert properties["anatomical_regions"]["maxItems"] == 6
    assert properties["limitations"]["maxItems"] == 4
    assert properties["patient_explanation"]["maxLength"] == 700
    observation_required = set(properties["observations"]["items"]["required"])
    assert observation_required == {"name", "value"}
    assert "unit" not in observation_required
    assert "reference" not in observation_required
