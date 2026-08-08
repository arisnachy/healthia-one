from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_collapsed_rail_keeps_primary_navigation_visible() -> None:
    css = (ROOT / "web/clinical-council.css").read_text(encoding="utf-8")
    assert ".left-collapsed .left-rail-scroll" in css
    assert "display: flex !important" in css
    assert ".left-collapsed .main-nav" in css
    assert "visibility: visible !important" in css
    assert ".left-collapsed .main-nav button" in css
    assert ".left-collapsed .main-nav button.is-active" in css
    assert ".left-collapsed .rail-section { display: none !important; }" in css


def test_collapsed_icons_keep_accessible_labels() -> None:
    icons = (ROOT / "web/icons.js").read_text(encoding="utf-8")
    i18n = (ROOT / "web/i18n.js").read_text(encoding="utf-8")
    index = (ROOT / "web/index.html").read_text(encoding="utf-8")
    assert "button.dataset.tooltip=label" in icons
    assert "button.setAttribute('aria-label',label)" in icons
    assert "button.title=label" in icons
    assert "const label=i18n?.t('nav.new')" in icons
    assert '"nav.new": "New consultation"' in i18n
    assert '"nav.new": "Nueva consulta"' in i18n
    assert 'id="newConsultation"' in index
    assert 'data-i18n="nav.new"' in index


def test_one_click_windows_launcher_runs_from_its_own_folder() -> None:
    launcher = (ROOT / "START-HEALTHIA.cmd").read_text(encoding="utf-8")
    assert 'cd /d "%~dp0"' in launcher
    assert "%~dp0deployment" in launcher
    assert "run-local-secure.ps1" in launcher
    assert "-GuardedAi -RequestLimit 10" in launcher
    assert "Local seguro - 0 llamadas" in launcher