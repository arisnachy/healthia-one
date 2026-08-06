from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_patient_control_ui_contract():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "ui-v5.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "ui-v5.css").read_text(encoding="utf-8")
    assert "/assets/ui-v5.css" in html
    assert "/assets/ui-v5.js" in html
    for marker in [
        "Permisos y privacidad",
        "/api/consent",
        "/api/consent/snooze",
        "/api/consent/mute",
        "/api/export",
        "Silenciar este tipo",
    ]:
        assert marker in script
    for marker in [".control-grid", ".toggle-row", ".audit-list", ".snooze-banner"]:
        assert marker in css


def test_v5_javascript_is_valid():
    subprocess.run(["node", "--check", str(ROOT / "web" / "ui-v5.js")], check=True)
