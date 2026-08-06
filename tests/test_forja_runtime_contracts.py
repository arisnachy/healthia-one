from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_google_sdk_matches_interactions_api() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    gemini = (ROOT / "healthia_one/gemini.py").read_text(encoding="utf-8")
    assert '"google-genai>=2.13,<3"' in pyproject
    assert '"google-adk[gcp]>=2.5,<3"' in pyproject
    assert "client.interactions.create" in gemini
    assert "def _interaction_text" in gemini
    assert 'genai.Client(api_key=api_key)' in gemini


def test_secure_launcher_probes_real_interaction_and_prints_lan_url() -> None:
    launcher = (ROOT / "deployment/run-local-secure.ps1").read_text(encoding="utf-8")
    assert "client.interactions.create" in launcher
    assert "Get-NetIPAddress" in launcher
    assert "Teléfono en la misma Wi-Fi" in launcher
    assert "--host 0.0.0.0" in launcher


def test_android_bridge_uses_supported_compose_toolchain() -> None:
    root_gradle = (ROOT / "android-health-bridge/build.gradle.kts").read_text(encoding="utf-8")
    app_gradle = (ROOT / "android-health-bridge/app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'id("org.jetbrains.kotlin.plugin.compose") version "2.1.0"' in root_gradle
    assert 'id("org.jetbrains.kotlin.plugin.compose")' in app_gradle
    assert "compileSdk = 35" in app_gradle
    assert "targetSdk = 35" in app_gradle
    assert "minSdk = 28" in app_gradle
    assert "composeOptions" not in app_gradle


def test_ci_validates_the_runtime_module() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in workflow
    assert "node --check web/runtime-integrations.js" in workflow


def test_runtime_affordances_are_real_not_decorative() -> None:
    runtime = (ROOT / "web/runtime-integrations.js").read_text(encoding="utf-8")
    icons = (ROOT / "web/icons.js").read_text(encoding="utf-8")
    interactions = (ROOT / "web/interactions.css").read_text(encoding="utf-8")
    assert "SpeechRecognition" in runtime
    assert 'json("/api/ai/test", {method: "POST"})' in runtime
    assert 'button.setAttribute("aria-pressed"' in runtime
    assert "/assets/runtime-integrations.js" in icons
    assert 'content: "Abrir menú"' in interactions
    assert "background: transparent" in interactions
