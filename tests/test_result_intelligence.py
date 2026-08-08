from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from healthia_one.context_compiler import relevant_results
from healthia_one.models import HealthResult, PatientState
from healthia_one.result_intelligence import (
    analyze_uploaded_result,
    apply_analysis_payload,
    normalized_mime_type,
    result_storage_path,
    supports_inline_multimodal,
)
from healthia_one.twin_runtime import record_result_in_state


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


def test_analysis_payload_keeps_reported_text_separate_from_ai_observation() -> None:
    result = HealthResult(filename="ct-chest.png", status="pending_multimodal")
    payload = {
        "artifact_type": "ct_image",
        "panel": "Tomografía de tórax",
        "modality": "CT",
        "anatomical_region": "Right lower lung",
        "exam_date": "2026-08-01",
        "summary": "Imagen torácica aportada por el paciente.",
        "reported_impression": "",
        "ai_observations": ["Opacidad basal derecha visible; observación no verificada."],
        "measurements": [],
        "safety_flags": [],
        "quality_limitations": ["Imagen única; no sustituye la serie DICOM ni el informe radiológico."],
        "confidence": "medium",
        "verification_status": "ai_observed_unverified",
    }
    apply_analysis_payload(result, payload, request_number=1)
    assert result.artifact_type == "ct_image"
    assert result.modality == "CT"
    assert result.anatomical_region == "Right lower lung"
    assert result.exam_date == date(2026, 8, 1)
    assert result.reported_impression == ""
    assert result.ai_observations == ["Opacidad basal derecha visible; observación no verificada."]
    assert result.verification_status == "ai_observed_unverified"
    assert result.source.source_type == "AI_extraction"
    assert result.source.verified is False


def test_result_reducer_uses_exam_date_and_creates_anatomy_and_silent_open_loop() -> None:
    state = PatientState()
    state.profile.id = "uid_patient"
    result = HealthResult(
        patient_id="forged",
        filename="ct-chest.png",
        uploaded_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        panel="Tomografía de tórax",
        artifact_type="ct_image",
        modality="CT",
        anatomical_region="Right lower lung",
        exam_date=date(2026, 8, 1),
        ai_observations=["Opacidad basal derecha; no verificada."],
        verification_status="ai_observed_unverified",
        source={"source_type": "AI_extraction", "source_id": "gemini_multimodal:1", "verified": False},
    )
    event = record_result_in_state(state, result)
    assert result.patient_id == "uid_patient"
    assert event.event_at.date() == date(2026, 8, 1)
    assert event.recorded_at.date() == date(2026, 8, 7)
    assert event.certainty == "ai_extraction"
    assert event.verification_status == "unverified"
    assert len(state.anatomical_links) == 1
    assert state.anatomical_links[0].system == "Respiratory"
    assert state.anatomical_links[0].laterality == "right"
    assert state.anatomical_links[0].status == "suspected"
    assert len(state.open_clinical_loops) == 1
    assert state.open_clinical_loops[0].status == "open"
    assert not state.messages, "open loops must not create background chat spam"


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
