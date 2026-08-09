from pathlib import Path


SCRIPT = Path("deployment/deploy-gmail-push-worker.ps1").read_text(encoding="utf-8")
WORKER = Path("healthia_one/gmail_push_worker.py").read_text(encoding="utf-8")
LIVE_PROOF = Path(".github/workflows/google-cloud-live-proof.yml").read_text(encoding="utf-8")


def test_gmail_worker_deploy_is_private_and_never_enables_apis_silently():
    assert "--no-allow-unauthenticated" in SCRIPT
    assert "--allow-unauthenticated" not in SCRIPT
    assert "gcloud services enable" not in SCRIPT.lower()
    assert "HEALTHIA_GMAIL_WORKER_NOT_CONFIRMED" in SCRIPT
    assert "[switch] $Confirmed" in SCRIPT


def test_gmail_topic_and_push_identity_match_google_authenticated_push_contract():
    assert "gmail-api-push@system.gserviceaccount.com" in SCRIPT
    assert "roles/pubsub.publisher" in SCRIPT
    assert "--push-auth-service-account" in SCRIPT
    assert "--push-auth-token-audience" in SCRIPT
    assert "roles/run.invoker" in SCRIPT
    assert "/events/gmail-push" in SCRIPT


def test_cloud_project_is_injected_into_production_and_live_proof_worker_runtime():
    assert "GOOGLE_CLOUD_PROJECT=$ProjectId" in SCRIPT
    assert "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" in LIVE_PROOF
    assert "GOOGLE_CLOUD_PROJECT is required for Gmail push worker" in WORKER


def test_watch_renewal_uses_private_scheduler_oidc_not_mailbox_polling():
    assert "--oidc-service-account-email" in SCRIPT
    assert "--oidc-token-audience" in SCRIPT
    assert "/scheduled/renew-gmail-watches" in SCRIPT
    assert "renew expiring patient-authorized gmail api watches" in SCRIPT.lower()
    assert "event-driven via pub/sub" in SCRIPT.lower()


def test_deployment_does_not_grant_broad_secret_access():
    assert "roles/secretmanager.secretAccessor" not in SCRIPT
    assert "does not grant broad secret access" in SCRIPT


def test_worker_has_no_public_docs_and_lazy_cloud_initialization():
    assert "docs_url=None" in WORKER
    assert "openapi_url=None" in WORKER
    assert 'if "value" not in cached:' in WORKER
    assert "runtime_factory()" in WORKER
    assert "build_live_runtime()" not in WORKER.split("app = create_app()", 1)[0].split("def runtime()", 1)[0]
