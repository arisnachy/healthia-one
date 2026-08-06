from pathlib import Path

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
        "patient-record.js",
        "family-documents.js",
        "continuity.js",
        "privacy-controls.js",
        "profile-devices.js",
        "icons.js",
    )
    assert html.count("<script ") == len(expected)
    for script in expected:
        assert html.count(f'/assets/{script}') == 1
