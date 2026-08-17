from __future__ import annotations

from pathlib import Path

import pytest

from healthia_one.adk_gemini import AdkGeminiResponder
from healthia_one.config import Settings
from healthia_one.deterministic_router import _mentions_result
from healthia_one.documents import build_document, category_from_filename
from healthia_one.evidence_store import EvidenceStoreError, load_evidence, persist_evidence
from healthia_one.models import ClinicalDocument, DocumentCategory, HealthResult
from healthia_one.service import HealthIAService


@pytest.mark.asyncio
async def test_local_evidence_roundtrip_is_patient_scoped(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HEALTHIA_GCS_BUCKET", raising=False)
    content = b"synthetic clinical evidence"
    document = build_document(
        filename="TAC_torax.png",
        content_type="image/png",
        size_bytes=len(content),
        patient_id="patient-alpha",
    )
    stored = await persist_evidence(document, content, tmp_path)
    assert stored.storage_path.startswith("uploads/patient-alpha/")
    assert await load_evidence(stored, tmp_path) == content
    assert (tmp_path / stored.storage_path).is_file()


@pytest.mark.asyncio
async def test_local_evidence_rejects_path_escape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HEALTHIA_GCS_BUCKET", raising=False)
    document = ClinicalDocument(
        title="Escape",
        filename="escape.txt",
        storage_path="../../escape.txt",
    )
    with pytest.raises(EvidenceStoreError):
        await load_evidence(document, tmp_path)


def test_document_modality_classifier_avoids_short_substring_false_positive() -> None:
    assert category_from_filename("CT_torax.png") == DocumentCategory.IMAGING
    assert category_from_filename("informe_TAC_torax.pdf") == DocumentCategory.IMAGING
    assert category_from_filename("factura_contacto.txt") == DocumentCategory.OTHER
    assert category_from_filename("hemograma_control.pdf") == DocumentCategory.LABORATORY


def test_result_router_uses_token_aware_short_modalities() -> None:
    assert _mentions_result("Háblame de mi CT de tórax") is True
    assert _mentions_result("Revisa el informe de mi TAC") is True
    assert _mentions_result("Necesito contactar al centro") is False
    assert _mentions_result("Quiero rectificar mi teléfono") is False


@pytest.mark.asyncio
async def test_result_and_original_are_committed_together() -> None:
    service = HealthIAService(Settings(store_backend="memory", llm_backend="mock"))
    result = HealthResult(filename="lab.json", panel="Laboratorio", status="parsed", explained=True)
    document = ClinicalDocument(
        title="Laboratorio original",
        filename="lab.json",
        storage_path="uploads/patient_demo/lab.json",
        status="parsed",
        related_result_id=result.id,
    )
    await service.add_result_evidence(result, document)
    state = await service.snapshot()
    assert any(item.id == result.id for item in state.results)
    assert any(item.id == document.id and item.related_result_id == result.id for item in state.documents)
    assert any(
        event.action == "upload_result_evidence"
        and event.resource_id == result.id
        and event.details.get("document_id") == document.id
        for event in state.audit_events
    )


def test_real_service_uses_adk_clinical_boundary_even_when_ai_is_mocked() -> None:
    service = HealthIAService(Settings(store_backend="memory", llm_backend="mock"))
    assert isinstance(service.gemini, AdkGeminiResponder)
    source = Path("healthia_agent/agent.py").read_text(encoding="utf-8")
    assert "patient_snapshot" not in source
    assert "healthia_one.adk_runtime" in source


def test_permanent_background_loop_is_absent() -> None:
    assert not hasattr(HealthIAService, "background_loop")
    app_source = Path("app/main.py").read_text(encoding="utf-8")
    device_source = Path("web/profile-devices.js").read_text(encoding="utf-8")
    assert "background_loop(" not in app_source
    assert "setInterval(" not in device_source


def test_cloud_deploy_requires_authenticated_durable_evidence_and_strict_proof() -> None:
    deploy = Path("deployment/deploy-cloud-demo.ps1").read_text(encoding="utf-8")
    verifier = Path("deployment/verify_cloud_demo.py").read_text(encoding="utf-8")
    assert "HEALTHIA_STORE_BACKEND=firestore" in deploy
    assert "HEALTHIA_AUTH_REQUIRED=true" in deploy
    assert "HEALTHIA_GCS_BUCKET=$BucketName" in deploy
    assert "HEALTHIA_PROACTIVE_ENABLED=false" in deploy
    assert "HEALTHIA_DEVICE_TOKEN_SECRET=${DeviceSecretName}:latest" in deploy
    assert "HEALTHIA_SESSION_SECRET=${SessionSecretName}:latest" in deploy
    assert "verify_cloud_demo.py" in deploy
    assert '"live_gemini_interactions_call"' in verifier
    assert '"google_adk_runner_tool_trajectory"' in verifier
    assert '"two_memory_preserving_dynamic_question_blocks"' in verifier
    assert '"gemini_followup_or_orientation_decision"' in verifier
    assert '"restart_safe_browser_session_identity"' in verifier
    assert '"restart_safe_device_identity"' in verifier
    assert '"two_patient_state_isolation"' in verifier
    assert '"cross_patient_document_denied"' in verifier
    assert '"gcs_patient_scoped_original_evidence"' in verifier
    assert '"clinical_twin_provenance"' in verifier
    assert '"original_evidence_roundtrip"' in verifier


def test_cloud_identity_token_is_not_passed_in_process_arguments() -> None:
    deploy = Path("deployment/deploy-cloud-demo.ps1").read_text(encoding="utf-8")
    provider = Path("deployment/verify_cloud_provider_binding.py").read_text(encoding="utf-8")
    assert '$env:HEALTHIA_CLOUD_ID_TOKEN = $providerIdentityToken' in deploy
    assert '$env:HEALTHIA_CLOUD_ID_TOKEN = $identityToken' in deploy
    assert 'Remove-Item Env:HEALTHIA_CLOUD_ID_TOKEN' in deploy
    assert '$providerProofArgs += @("--identity-token"' not in deploy
    assert '$proofArgs += @("--identity-token"' not in deploy
    assert 'default=os.getenv("HEALTHIA_CLOUD_ID_TOKEN", "")' in provider
