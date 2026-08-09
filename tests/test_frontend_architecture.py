from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

SEMANTIC_SCRIPTS = (
    "app.js",
    "patient-record.js",
    "family-documents.js",
    "continuity.js",
    "privacy-controls.js",
    "profile-devices.js",
    "icons.js",
)


def test_frontend_has_no_version_layer_assets() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "ui-v2" not in html
    assert "ui-v3" not in html
    assert "ui-v4" not in html
    assert "ui-v5" not in html
    assert "ui-v6" not in html
    assert "ui-v7" not in html
    assert html.count('rel="stylesheet"') == 2
    assert '/assets/styles.css' in html
    assert '/assets/interactions.css' in html
    for script in SEMANTIC_SCRIPTS:
        assert f'/assets/{script}' in html
    assert not list(WEB.glob("ui-v*.js"))
    assert not list(WEB.glob("ui-v*.css"))


def test_frontend_semantic_modules_are_valid_javascript() -> None:
    for script in SEMANTIC_SCRIPTS:
        subprocess.run(["node", "--check", str(WEB / script)], check=True)


def test_runtime_guards_and_single_event_stream_are_present() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "__HEALTHIA_APP_BOOTED__" in app
    assert "let eventStream = null" in app
    assert "if (eventStream) return" in app
    assert "refreshPromise" in app
    assert 'setTimeout(() => refresh(), 120)' in app
    for script in SEMANTIC_SCRIPTS[1:]:
        content = (WEB / script).read_text(encoding="utf-8")
        assert "window.__HEALTHIA_" in content


def test_chat_shell_logo_scroll_avatar_and_new_consultation_contract() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    i18n = (WEB / "i18n.js").read_text(encoding="utf-8")
    for marker in ('id="newConsultation"', 'class="left-rail-scroll"', 'id="accountPill"', 'class="brand-mark"', '<svg viewBox="0 0 48 48"'):
        assert marker in html
    assert ".left-rail-scroll" in css and "overflow-y: auto" in css
    assert ".user-pill" in css
    assert 'api("/api/consultations/new", {method:"POST"})' in app
    assert "setSendState" in app
    assert "function publicName(value)" in app
    assert 'tr("app.module")' in app
    assert '"app.module": "Health module"' in i18n
    assert '"app.module": "Módulo de salud"' in i18n


def test_secondary_modules_are_locale_aware_and_keep_real_endpoints() -> None:
    scripts = {
        "patient": (WEB / "patient-record.js").read_text(encoding="utf-8"),
        "family": (WEB / "family-documents.js").read_text(encoding="utf-8"),
        "continuity": (WEB / "continuity.js").read_text(encoding="utf-8"),
        "privacy": (WEB / "privacy-controls.js").read_text(encoding="utf-8"),
        "devices": (WEB / "profile-devices.js").read_text(encoding="utf-8"),
        "runtime": (WEB / "runtime-integrations.js").read_text(encoding="utf-8"),
    }
    for name, source in scripts.items():
        assert "window.HealthIAI18n" in source, f"{name} is not bound to the shared i18n runtime"
        assert "Accept-Language" in source, f"{name} does not propagate the visible locale to API calls"
    for marker in ("renderPatientOS", "data-health-action", "localeTag"):
        assert marker in scripts["patient"]
    assert "setupVoice" not in scripts["patient"]
    assert "setupVoiceInput" in scripts["runtime"]
    assert "recognition.lang" in scripts["runtime"]
    assert 'recognition.lang = "es-DO"' not in scripts["runtime"]
    assert "recognition.lang='es-DO'" not in scripts["runtime"]
    for marker in ('text("Family genogram"', 'text("Documents"', "/api/family", "/api/documents/upload"):
        assert marker in scripts["family"]
    for marker in ('text("Health timeline"', 'text("Treatment"', 'text("Appointments & visit"', "/api/appointments"):
        assert marker in scripts["continuity"]
    for marker in ('text("Permissions & privacy"', "/api/consent", "/api/export"):
        assert marker in scripts["privacy"]
    for marker in ('text("Patient profile"', 'text("Devices"', "Health Connect", 'text("Nutritional status"'):
        assert marker in scripts["devices"]


def test_visual_system_is_consolidated_and_icon_driven() -> None:
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    icons = (WEB / "icons.js").read_text(encoding="utf-8")
    for marker in (".genogram-board", ".document-grid", ".timeline-list", ".control-grid", ".vital-matrix", ".device-grid"):
        assert marker in css
    assert "MutationObserver" not in icons
    assert "const viewIcon=" in icons
    assert "family:'family'" in icons
    assert "devices:'device'" in icons
    assert "healthia:ui-updated" in icons
    assert "healthia:locale-changed" in icons


def test_left_rail_reopens_and_composer_floats_inside_chat_surface() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    interactions = (WEB / "interactions.css").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'id="expandLeft"' in html
    assert ".left-collapsed .rail-reopen" in interactions
    assert 'refs.expandLeft?.addEventListener("click"' in app
    assert "#view-chat .composer-wrap" in interactions and "position: absolute" in interactions
    assert 'class="composer-context"' not in html


def test_device_page_exposes_real_pairing_and_no_hardware_demo_paths() -> None:
    js = (WEB / "profile-devices.js").read_text(encoding="utf-8")
    for marker in (
        'text("Connect device"',
        "/api/devices/pairing",
        'text("Temporary code"',
        'text("Test without hardware"',
        "LAN IP",
    ):
        assert marker in js
