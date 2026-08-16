from pathlib import Path


WORKFLOW = Path(".github/workflows/google-live-finalization.yml").read_text(encoding="utf-8")


def test_live_finalization_never_enables_apis_or_mutates_iam():
    lowered = WORKFLOW.lower()
    assert "gcloud services enable" not in lowered
    assert "add-iam-policy-binding" not in lowered
    assert "set-iam-policy" not in lowered
    assert "no api enablement; no iam mutation" in lowered


def test_tts_probe_is_synthetic_and_does_not_upload_audio_bytes():
    assert "https://texttospeech.googleapis.com/v1/text:synthesize" in WORKFLOW
    assert "HealthIA synthetic accessibility proof." in WORKFLOW
    assert "rm -f /tmp/healthia-proof.mp3" in WORKFLOW
    assert "Synthetic audio SHA-256" in WORKFLOW
    assert "audioContent" in WORKFLOW


def test_fcm_probe_cannot_notify_a_real_device_and_classifies_iam_blocker():
    assert "healthia-proof-intentionally-invalid-registration-token" in WORKFLOW
    assert "INVALID_ARGUMENT" in WORKFLOW
    assert "PERMISSION_DENIED" in WORKFLOW
    assert "BLOCKED_IAM: FCM API is enabled" in WORKFLOW
    assert "Delivery: none" in WORKFLOW
    assert "fcm.googleapis.com/v1/projects/${PROJECT_ID}/messages:send" in WORKFLOW


def test_disabled_clinical_apis_fail_closed_instead_of_being_enabled():
    assert "speech.googleapis.com" in WORKFLOW
    assert "documentai.googleapis.com" in WORKFLOW
    assert "healthcare.googleapis.com" in WORKFLOW
    assert "BLOCKED_DISABLED_API" in WORKFLOW
    assert "will not enable it silently" in WORKFLOW


def test_veo_generation_remains_cost_gated():
    assert "Veo: Vertex AI API enabled; generation remains COST_GATED" in WORKFLOW
    assert "Veo real generation: requires explicit cost/authorization gate" in WORKFLOW


def test_scheduler_probe_is_read_only_and_records_permission_boundary():
    assert "gcloud scheduler jobs list" in WORKFLOW
    assert "cloudscheduler.jobs.list" in WORKFLOW
    assert "BLOCKED_IAM" in WORKFLOW
    assert "scheduler jobs create" not in WORKFLOW.lower()
