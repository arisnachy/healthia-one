from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chat_composer_is_part_of_primary_view() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="view-chat"' in html
    assert 'class="composer-wrap"' in html
    assert 'id="chatInput"' in html
    assert 'id="voiceButton"' in html
    assert 'id="sendButton"' in html
    assert '/assets/ui-v2.css' in html
    assert '/assets/ui-v2.js' in html


def test_layout_reserves_visible_space_for_composer() -> None:
    css = (ROOT / "web" / "ui-v2.css").read_text(encoding="utf-8")
    assert "height: 100dvh" in css
    assert "#view-chat.is-active" in css
    assert "grid-template-rows: minmax(0, 1fr) auto" in css
    assert ".chat-scroll" in css and "min-height: 0" in css
    assert ".composer-wrap" in css and "z-index: 10" in css


def test_patient_continuity_interface_contract() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "ui-v2.js").read_text(encoding="utf-8")
    for marker in ["Mi expediente", "Revisión agentica", "Contexto longitudinal activo", "Próxima acción"]:
        assert marker in html
    for marker in ["renderPatientOS", "setupVoice", "data-health-action", "has-history"]:
        assert marker in script
