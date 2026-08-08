from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_login_supports_google_and_email_without_exposing_server_secrets() -> None:
    auth = (WEB / "auth.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "GoogleAuthProvider" in auth
    assert "signInWithPopup" in auth
    assert "createUserWithEmailAndPassword" in auth
    assert "signInWithEmailAndPassword" in auth
    assert "getIdToken" in auth
    assert "/api/auth/config" in auth
    assert "GEMINI_API_KEY" not in auth
    assert 'id="authGate"' in html
    assert 'id="googleSignIn"' in html


def test_frontend_sends_verified_identity_token_and_uses_authenticated_event_stream() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'headers.set("Authorization", `Bearer ${token}`)' in app
    assert 'healthiaFetch("/api/events/stream"' in app
    assert "new EventSource" not in app
    assert "Agentes a demanda" in app


def test_every_patient_module_uses_the_single_authenticated_transport() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "window.healthiaFetch = healthiaFetch" in app
    offenders: list[str] = []
    for path in WEB.glob("*.js"):
        if path.name in {"app.js", "auth.js"}:
            continue
        source = path.read_text(encoding="utf-8")
        if "fetch(" in source:
            offenders.append(path.name)
    assert offenders == [], f"raw unauthenticated fetch remains in: {offenders}"


def test_sidebar_has_one_patient_identity_not_account_plus_patient_duplicates() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert html.count('id="patientName"') == 1
    assert 'id="accountPill"' in html
    assert 'id="signOutButton"' in html
    assert "Arisnachy Gomez" not in html
    assert "Áreas disponibles · se activan a demanda" in html


def test_cloud_deploy_requires_budget_ack_and_can_enable_identity_platform() -> None:
    deploy = (ROOT / "deployment" / "deploy-cloud-demo.ps1").read_text(encoding="utf-8")
    assert "BudgetTargetUsd = 45" in deploy
    assert "AbsoluteBudgetUsd = 50" in deploy
    assert 'if ($budgetAck -ne "BUDGET")' in deploy
    assert "HEALTHIA_AUTH_MODE=$authMode" in deploy
    assert "HEALTHIA_FIREBASE_API_KEY" in deploy
    assert "HEALTHIA_FIREBASE_AUTH_DOMAIN" in deploy
    assert "HEALTHIA_FIREBASE_APP_ID" in deploy
    assert "identitytoolkit.googleapis.com" in deploy
    assert "Agentes: A DEMANDA" in deploy
