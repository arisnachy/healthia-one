from pathlib import Path


ACCOUNT = Path("web/account.js").read_text(encoding="utf-8")


def test_account_ui_exposes_google_connection_without_embedding_credentials():
    assert "/api/google-constellation/oauth/readiness" in ACCOUNT
    assert "/api/google-constellation/capabilities" in ACCOUNT
    assert "/api/google-constellation/oauth/connect" in ACCOUNT
    assert "/api/google-constellation/oauth/disconnect" in ACCOUNT
    assert "Google connected" in ACCOUNT
    assert "Google not connected" in ACCOUNT
    assert "Google connection unavailable" in ACCOUNT
    lowered = ACCOUNT.lower()
    assert "refresh_token" not in lowered
    assert "client_secret" not in lowered
    assert "access_token" not in lowered


def test_connect_requires_backend_readiness_and_disconnect_tells_truth_about_provider_revocation():
    assert "readiness?.ready === true" in ACCOUNT
    assert "google_grant_revoked === false" in ACCOUNT
    assert "Provider-side Google access can be revoked separately" in ACCOUNT
    assert "No secret material is exposed" in ACCOUNT


def test_oauth_callback_return_opens_account_status_and_removes_query_marker():
    assert 'params.get("google") !== "connected"' in ACCOUNT
    assert "history.replaceState" in ACCOUNT
    assert "Google connected to HealthIA for authorized missions." in ACCOUNT
