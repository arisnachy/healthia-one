from pathlib import Path


def test_lab_omega_targets_the_login_wordmark_that_is_actually_shipped() -> None:
    login = Path("web/login.html").read_text(encoding="utf-8")
    lab = Path("scripts/lab_omega.py").read_text(encoding="utf-8")

    assert 'class="auth-wordmark"' in login
    assert 'page.locator(".auth-wordmark").inner_text()' in lab
    assert '.brand-wordmark' not in lab
    assert 'data-i18n="auth.hero"' in login
    assert "Your health continues" in lab
    assert "Tu salud continúa" in lab
