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
    assert html.count('rel="stylesheet"') == 1
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
    for marker in ('id="newConsultation"', 'class="left-rail-scroll"', 'id="accountPill"', 'class="brand-mark"', '<svg viewBox="0 0 48 48"'):
        assert marker in html
    assert ".left-rail-scroll" in css and "overflow-y: auto" in css
    assert ".user-pill" in css
    assert 'api("/api/demo/reset", {method:"POST"})' in app
    assert "setSendState" in app
    assert "PUBLIC_NAMES" in app


def test_patient_record_family_continuity_privacy_and_devices_contracts() -> None:
    scripts = {
        "patient": (WEB / "patient-record.js").read_text(encoding="utf-8"),
        "family": (WEB / "family-documents.js").read_text(encoding="utf-8"),
        "continuity": (WEB / "continuity.js").read_text(encoding="utf-8"),
        "privacy": (WEB / "privacy-controls.js").read_text(encoding="utf-8"),
        "devices": (WEB / "profile-devices.js").read_text(encoding="utf-8"),
    }
    for marker in ("renderPatientOS", "setupVoice", "data-health-action"):
        assert marker in scripts["patient"]
    for marker in ("Genograma familiar", "Documentos", "/api/family", "/api/documents/upload"):
        assert marker in scripts["family"]
    for marker in ("Línea de salud", "Tratamiento", "Citas y consulta", "/api/appointments"):
        assert marker in scripts["continuity"]
    for marker in ("Permisos y privacidad", "/api/consent", "/api/export"):
        assert marker in scripts["privacy"]
    for marker in ("Perfil del paciente", "Dispositivos", "Health Connect", "Estado nutricional"):
        assert marker in scripts["devices"]


def test_visual_system_is_consolidated_and_icon_driven() -> None:
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    icons = (WEB / "icons.js").read_text(encoding="utf-8")
    for marker in (".genogram-board", ".document-grid", ".timeline-list", ".control-grid", ".vital-matrix", ".device-grid"):
        assert marker in css
    assert "MutationObserver" not in icons
    assert '"Genograma familiar":"family"' in icons
    assert '"Dispositivos":"device"' in icons
    assert "healthia:ui-updated" in icons
