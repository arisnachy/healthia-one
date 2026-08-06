from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_genogram_and_document_ui_contract():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "ui-v3.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "ui-v3.css").read_text(encoding="utf-8")
    assert "/assets/ui-v3.css" in html
    assert "/assets/ui-v3.js" in html
    for marker in ["Genograma familiar", "Documentos", "/api/family", "/api/documents/upload", "renderGenogram"]:
        assert marker in script
    for marker in [".genogram-board", ".family-node", ".document-grid", ".health-os-dialog"]:
        assert marker in css


def test_v3_javascript_is_valid():
    subprocess.run(["node", "--check", str(ROOT / "web" / "ui-v3.js")], check=True)
