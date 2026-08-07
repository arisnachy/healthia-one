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
    assert "button.dataset.tooltip=label" in icons
    assert "button.setAttribute('aria-label',label)" in icons
    assert "button.title=label" in icons
    assert "button.setAttribute('aria-label','Nueva consulta')" in icons


def test_one_click_windows_launcher_runs_from_its_own_folder() -> None:
    launcher = (ROOT / "START-HEALTHIA.cmd").read_text(encoding="utf-8")
    assert 'cd /d "%~dp0"' in launcher
    assert r"deployment\run-local-secure.ps1" in launcher
    assert "-GuardedAi -RequestLimit 10" in launcher
    assert "Local seguro - 0 llamadas" in launcher
