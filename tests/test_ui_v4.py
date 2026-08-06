from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_timeline_treatment_and_consultation_ui_contract():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "ui-v4.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "ui-v4.css").read_text(encoding="utf-8")
    assert "/assets/ui-v4.css" in html
    assert "/assets/ui-v4.js" in html
    for marker in ["Línea de salud", "Tratamiento", "Citas y consulta", "/api/treatment/checkins", "/api/appointments"]:
        assert marker in script
    for marker in [".timeline-list", ".treatment-grid", ".appointment-grid", ".brief-hero"]:
        assert marker in css


def test_v4_javascript_is_valid():
    subprocess.run(["node", "--check", str(ROOT / "web" / "ui-v4.js")], check=True)
