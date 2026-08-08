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
        "app.js",
        "clinical-council.js",
        "patient-record.js",
        "family-documents.js",
        "continuity.js",
        "privacy-controls.js",
        "profile-devices.js",
        "account.js",
        "icons.js",
    )
    assert html.count("<script ") == len(expected)
    for script in expected:
        assert html.count(f'/assets/{script}') == 1


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
    assert "window.addEventListener('focus', loadStatus)" in cost_js


def test_real_cloud_browser_proof_checks_account_dom_and_vertex_truth() -> None:
    proof = (ROOT / "scripts" / "cloud_browser_judge_proof.py").read_text(encoding="utf-8")
    assert 'account_identity = page.locator("#accountIdentity").inner_text()' in proof
    assert 'require(email in account_identity' in proof
    assert 'get_by_text(email, exact=True)' not in proof
    assert 'runtime label contradicts live AI readiness' in proof
    assert 'browser_runtime_label_matches_live_vertex_readiness' in proof
