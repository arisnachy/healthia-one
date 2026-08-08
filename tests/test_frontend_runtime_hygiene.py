from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_identity_cleanup_does_not_use_recursive_dom_observer() -> None:
    profile_devices = (WEB / "profile-devices.js").read_text(encoding="utf-8")
    assert "hideInternalNames" not in profile_devices
    assert "MutationObserver(hideInternalNames)" not in profile_devices


def test_core_runtime_serializes_refresh_and_owns_one_event_stream() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "let refreshPromise = null" in app
    assert "let eventStream = null" in app
    assert "if (eventStream) return" in app
    assert 'new EventSource("/api/events/stream")' in app


def test_only_semantic_frontend_modules_are_loaded() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    expected = (
        "i18n.js",
        "app.js",
        "clinical-council.js",
        "patient-record.js",
        "family-documents.js",
        "continuity.js",
        "privacy-controls.js",
        "profile-devices.js",
        "account.js",
        "runtime-integrations.js",
        "provider-integrations.js",
        "cost-control.js",
        "icons.js",
    )
    assert html.count("<script ") == len(expected)
    for script in expected:
        assert html.count(f'/assets/{script}') == 1
    icons = (WEB / "icons.js").read_text(encoding="utf-8")
    assert "loadScript(" not in icons
    assert "document.createElement('script')" not in icons


def test_i18n_runtime_is_os_aware_and_has_input_language_override() -> None:
    i18n = (WEB / "i18n.js").read_text(encoding="utf-8")
    index = (WEB / "index.html").read_text(encoding="utf-8")
    login = (WEB / "login.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "navigator.languages" in i18n
    assert "navigator.language" in i18n
    assert "detectInputLocale" in i18n
    assert 'const responseLocale = inputLocale(clean)' in app
    assert '"Accept-Language":responseLocale' in app
    assert '<html lang="en">' in index
    assert '<html lang="en">' in login
    assert '/assets/i18n.js' in index
    assert '/assets/i18n.js' in login
    assert 'data-i18n="chat.hero"' in index
    assert 'data-i18n="auth.hero"' in login


def test_browser_runtime_has_no_permanent_interval_polling() -> None:
    offenders = [path.name for path in WEB.glob("*.js") if "setInterval(" in path.read_text(encoding="utf-8")]
    assert offenders == [], f"Permanent browser polling found in: {offenders}"


def test_repository_contains_no_transfer_or_temporary_workflow_artifacts() -> None:
    assert not (ROOT / ".cleanup-bundle").exists()
    assert not list(ROOT.glob(".audit-tree-probe*"))
    assert not list((ROOT / ".github" / "workflows").glob("apply-*.yml"))
    manifest = ROOT / "RELEASE-MANIFEST.json"
    if manifest.exists():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert payload.get("project") == "HealthIA ONE"
        assert payload.get("synthetic_demo_only") is True
        assert payload.get("source_ref")


def test_main_runtime_has_no_stale_patient_name_dom_reference() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '$("#patientName")' not in app_js
    assert 'refs.patientName' not in app_js
    assert 'id="heroPatientName"' in index_html


def test_cloud_ai_status_is_driven_by_runtime_readiness_not_key_presence() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert "readiness.ai_ready" in app_js
    assert "readiness.api_key_configured" not in app_js
    assert "readiness.llm_backend" in app_js


def test_cost_control_runtime_is_vertex_aware_and_has_no_permanent_polling() -> None:
    cost_js = (WEB / "cost-control.js").read_text(encoding="utf-8")
    assert "google_ai_configured" in cost_js
    assert "ai_transport" in cost_js
    assert "Vertex AI activo" in cost_js
    assert "api_key_configured" not in cost_js
    assert "setInterval(" not in cost_js
    assert "visibilitychange" in cost_js
    assert "window.addEventListener" in cost_js
    assert "'focus'" in cost_js
    assert "loadStatus" in cost_js


def test_icon_decoration_preserves_composer_file_input() -> None:
    icons = (WEB / "icons.js").read_text(encoding="utf-8")
    index_html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="resultFile"' in index_html
    assert "attach.innerHTML" not in icons
    assert "insertAdjacentHTML('afterbegin', icon('plus'))" in icons
    assert "!$('.v6-icon', attach)" in icons


def test_real_cloud_browser_proof_checks_account_dom_and_vertex_truth() -> None:
    proof = (ROOT / "scripts" / "cloud_browser_judge_proof.py").read_text(encoding="utf-8")
    assert 'account_identity = page.locator("#accountIdentity").inner_text()' in proof
    assert 'require(email in account_identity' in proof
    assert 'get_by_text(email, exact=True)' not in proof
    assert 'runtime label contradicts live AI readiness' in proof
    assert 'browser_runtime_label_matches_live_vertex_readiness' in proof


def test_real_cloud_browser_navigation_is_unambiguous() -> None:
    proof = (ROOT / "scripts" / "cloud_browser_judge_proof.py").read_text(encoding="utf-8")
    assert "page.locator('.main-nav [data-open=\"chat\"]').click()" in proof
    assert "page.locator('[data-open=\"chat\"]').click()" not in proof
