from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from healthia_one.models import HealthResult, PatientState
from healthia_one.result_intelligence import analyze_uploaded_result


class FakeCostGuard:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.max_output_tokens = 900

    def authorize(self, reason: str) -> int:
        self.calls.append(reason)
        return len(self.calls)


class FakeModels:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(self.payload, ensure_ascii=False))


class FakeClient:
    def __init__(self, payload: dict) -> None:
        self.models = FakeModels(payload)


class FakeResponder:
    def __init__(self, payload: dict) -> None:
        self.settings = SimpleNamespace(
            llm_backend="gemini_api",
            adk_ready=True,
            model="gemini-3.6-flash",
            llm_timeout_seconds=18,
        )
        self.cost_guard = FakeCostGuard()
        self.client = FakeClient(payload)
        self.last_status = ""
        self.last_error = ""

    def _get_client(self):
        return self.client

    @staticmethod
    def _json_object(text: str) -> dict:
        return json.loads(text)


@pytest.mark.asyncio
async def test_guarded_multimodal_ingestion_uses_one_model_call_and_keeps_ai_unverified() -> None:
    payload = {
        "artifact_type": "ct_image",
        "panel": "Tomografía de tórax",
        "modality": "CT",
        "anatomical_region": "Right lower lung",
        "exam_date": "2026-08-01",
        "summary": "Imagen torácica aportada por el paciente.",
        "reported_impression": "",
        "ai_observations": ["Opacidad basal derecha visible; observación de IA no verificada."],
        "measurements": [],
        "safety_flags": [],
        "quality_limitations": ["Captura aislada; no sustituye la serie diagnóstica ni el informe radiológico."],
        "confidence": "medium",
        "verification_status": "ai_observed_unverified",
    }
    responder = FakeResponder(payload)
    state = PatientState()
    result = HealthResult(filename="ct-chest.png", status="pending_multimodal")

    analyzed = await analyze_uploaded_result(
        responder,
        state,
        result,
        content=b"synthetic-image-bytes",
        mime_type="image/png",
    )

    assert responder.cost_guard.calls == ["multimodal_result_ingestion"]
    assert len(responder.client.models.calls) == 1
    call = responder.client.models.calls[0]
    assert call["model"] == "gemini-3.6-flash"
    assert call["config"].response_mime_type == "application/json"
    assert analyzed.status == "parsed"
    assert analyzed.artifact_type == "ct_image"
    assert analyzed.modality == "CT"
    assert analyzed.anatomical_region == "Right lower lung"
    assert analyzed.ai_observations
    assert analyzed.reported_impression == ""
    assert analyzed.verification_status == "ai_observed_unverified"
    assert analyzed.source.source_type == "AI_extraction"
    assert analyzed.source.verified is False
    assert responder.last_status == "result_multimodal_completed"
