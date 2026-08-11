from pathlib import Path


WORKFLOW = Path(".github/workflows/google-wave2-live-providers.yml")


def test_live_provider_harness_requires_exact_manual_authorization():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "I_AUTHORIZE_STT_DOCUMENTAI_HEALTHCARE_LIVE" in text
    assert "veo_authorized':False" in text


def test_stt_contract_matches_verified_live_proof():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ffmpeg -v error -y -i /tmp/healthia-wave2-raw.wav -ar 16000 -ac 1" in text
    assert "controls=[{'one','1'},{'two','2'},{'three','3'}]" in text
    assert "expected_control_concept_hits" in text
    assert "raw_transcript_exposed" in text


def test_documentai_contract_uses_canonical_private_gcs_proof():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "google-wave2-documentai-gcs-proof.yml" in text
    assert "private_gcs:true" in text


def test_healthcare_contract_waits_for_dataset_lifecycle_and_proves_both_modalities():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "gcloud healthcare datasets create" in text
    assert "gcloud healthcare fhir-stores create" in text
    assert "gcloud healthcare dicom-stores create" in text
    assert "fhir_create_reread" in text
    assert "dicom_stow_metadata_reread" in text
    assert "dataset_absent_after_cleanup" in text


def test_temporary_roles_are_cleaned_and_no_broad_owner_editor_role_is_used():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "roles/owner" not in text
    assert "roles/editor" not in text
    assert "remove-iam-policy-binding" in text
    assert "temporary_roles_remaining_count" in text
