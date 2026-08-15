from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_private_worker_exposes_zero_model_intent_recovery_endpoint() -> None:
    worker = (ROOT / "healthia_one/autopilot_worker.py").read_text(encoding="utf-8")

    assert "recover_firestore_event_intents" in worker
    assert '@app.post("/scheduled/recover-intents")' in worker
    assert "require_private_cloud_runtime()" in worker
    assert '"intent_recovery_schedule": "every_15_minutes"' in worker
    assert "failure_count" in worker
    assert "status_code=503" in worker


def test_scheduler_deployment_adds_15_minute_recovery_without_enabling_apis_silently() -> None:
    script = (ROOT / "deployment/deploy-autopilot-schedules.ps1").read_text(encoding="utf-8")

    assert 'RecoveryJobName = "healthia-autopilot-intent-recovery"' in script
    assert 'RecoverySchedule = "*/15 * * * *"' in script
    assert 'Path = "/scheduled/recover-intents"' in script
    assert "zero model calls" in script
    assert "-Confirmed" in script
    assert "This script will not enable APIs silently" in script
    assert "--oidc-service-account-email" in script
