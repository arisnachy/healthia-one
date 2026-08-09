from pathlib import Path


SCRIPT = Path("deployment/configure-google-oauth.ps1").read_text(encoding="utf-8")


def test_oauth_provisioning_requires_explicit_confirmation_and_never_enables_apis():
    lowered = SCRIPT.lower()
    assert "[switch] $Confirmed" in SCRIPT
    assert "HEALTHIA_GOOGLE_OAUTH_NOT_CONFIRMED" in SCRIPT
    assert "gcloud services enable" not in lowered
    assert "will not enable APIs silently" in SCRIPT


def test_oauth_provisioning_never_creates_google_oauth_clients_or_prints_secret_payloads():
    assert "does not create a Google OAuth Client ID" in SCRIPT
    assert "OAuth client payload: not displayed" in SCRIPT
    assert "OAuth state payload: not displayed" in SCRIPT
    assert "access secret version" not in SCRIPT.lower()


def test_cloud_run_receives_resource_reference_redirect_and_state_secret_mapping():
    assert "HEALTHIA_GOOGLE_OAUTH_CLIENT_SECRET_RESOURCE=$OAuthClientSecretResource" in SCRIPT
    assert "HEALTHIA_GOOGLE_OAUTH_REDIRECT_URI=$RedirectUri" in SCRIPT
    assert "HEALTHIA_GOOGLE_OAUTH_STATE_SECRET=$($stateSecret.Secret):$($stateSecret.Version)" in SCRIPT
    assert '"run", "services", "update"' in SCRIPT
    assert "/api/google-constellation/oauth/callback" in SCRIPT
    assert 'if ($redirect.Scheme -ne "https")' in SCRIPT


def test_secret_access_is_secret_scoped_and_never_project_wide_admin():
    lowered = SCRIPT.lower()
    assert '"secrets", "add-iam-policy-binding"' in SCRIPT
    assert "roles/secretmanager.secretAccessor" in SCRIPT
    assert "roles/secretmanager.secretVersionAdder" in SCRIPT
    assert "roles/secretmanager.viewer" in SCRIPT
    assert "roles/secretmanager.admin" not in SCRIPT
    assert '"projects", "add-iam-policy-binding"' not in lowered
    assert "project-wide Secret Manager access" in SCRIPT


def test_patient_token_secret_name_is_hashed_and_empty_until_consent():
    assert "SHA256" in SCRIPT
    assert 'return "healthia-google-oauth-$($hex.Substring(0, 24))"' in SCRIPT
    assert "contains no token until patient consent callback succeeds" in SCRIPT
    assert "PatientId must be a HealthIA patient_ identifier" in SCRIPT
