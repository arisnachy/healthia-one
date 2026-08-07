from __future__ import annotations

from types import SimpleNamespace

import pytest

from healthia_one.context_compiler import relevant_results
from healthia_one.models import HealthResult, PatientState
from healthia_one.result_intelligence import (
    analyze_uploaded_result,
    normalized_mime_type,
    result_storage_path,
    supports_inline_multimodal,
)


def test_result_storage_path_is_scoped_and_sanitized() -> None:
    path = result_storage_path("uid/../../other", "result_123", "CT CHEST.PDF")
    assert path.parts[:2] == ("uploads", "results")
    assert ".." not in path.parts
    assert path.name == "result_123.pdf"
    assert "uid_.._.._other" in str(path)


def test_multimodal_mime_detection_is_explicit() -> None:
    assert normalized_mime_type("scan.pdf", "application/octet-stream") == "application/pdf"
    assert normalized_mime_type("image.JPG", None) == "image/jpeg"
    assert supports_inline_multimodal("image/png") is True
    assert supports_inline_multimodal("text/plain") is False


@pytest.mark.asyncio
async def test_multimodal_result_stays_pending_without_ai_and_spends_zero_calls() -> None:
    state = PatientState()
    result = HealthResult(filename="ct.png", status="pending_multimodal")
    responder = SimpleNamespace(settings=SimpleNamespace(llm_backend="mock", adk_ready=False))
    analyzed = await analyze_uploaded_result(
        responder,
        state,
        result,
        content=b"not-a-real-image",
        mime_type="image/png",
    )
    assert analyzed.status == "pending_multimodal"
    assert analyzed.explained is False
    assert "no se consume una llamada" in analyzed.explanation


def test_result_context_retrieves_matching_old_study_but_not_unrelated_chat() -> None:
    state = PatientState()
    state.results = [
        HealthResult(filename="cbc.json", panel="Hemograma", explanation="Hemoglobina 13.8"),
        HealthResult(filename="torax-2026.png", panel="Tomografía de tórax", explanation="AI no verificada: opacidad basal derecha"),
        HealthResult(filename="lipids.json", panel="Perfil lipídico", explanation="LDL 121 mg/dL"),
    ]
    matched = relevant_results(state, "¿Qué decía la tomografía de tórax que subí?")
    assert matched[0].panel == "Tomografía de tórax"
    assert relevant_results(state, "¿Cómo puedo organizar mejor mi sueño?") == []
