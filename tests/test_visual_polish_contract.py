from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v6_assets_are_loaded_after_prior_layers():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '/assets/ui-v6.css' in html
    assert '/assets/ui-v6.js' in html
    assert html.index('/assets/ui-v5.css') < html.index('/assets/ui-v6.css')
    assert html.index('/assets/ui-v5.js') < html.index('/assets/ui-v6.js')


def test_v6_keeps_the_existing_slate_palette_and_integrates_composer():
    css = (ROOT / "web" / "ui-v6.css").read_text(encoding="utf-8")
    assert "Keeps the existing light/slate palette" in css
    assert ".composer-wrap" in css
    assert "border-top: 1px solid" in css
    assert ".composer {" in css
    assert "box-shadow: none" in css
    assert ".nav-icon" in css
    assert ".health-card-icon" in css


def test_v6_uses_one_short_entry_message_and_moves_proactive_items_out_of_chat():
    js = (ROOT / "web" / "ui-v6.js").read_text(encoding="utf-8")
    assert "Ya revisé tus datos recientes" in js
    assert "¿Qué te gustaría revisar hoy?" in js
    assert "message.metadata?.proactive" in js
    assert 'scroll.classList.add("entry-mode")' in js
    assert 'scroll.classList.add("conversation-started")' in js
    assert "list.replaceChildren()" in js


def test_v6_has_consistent_svg_icons_for_core_health_navigation():
    js = (ROOT / "web" / "ui-v6.js").read_text(encoding="utf-8")
    for marker in (
        '"Genograma familiar": "family"',
        '"Documentos": "file"',
        '"Línea de salud": "heart"',
        '"Tratamiento": "pill"',
        '"Permisos y privacidad": "shield"',
        '"Misiones de salud": "target"',
    ):
        assert marker in js
    assert '<svg viewBox="0 0 24 24">' in js
