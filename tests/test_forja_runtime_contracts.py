from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_google_sdk_contract_is_modern_and_interactions_capable() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    gemini = (ROOT / "healthia_one/gemini.py").read_text(encoding="utf-8")
    verifier = (ROOT / "deployment/verify_google_ai.py").read_text(encoding="utf-8")
    assert 'google-genai>=2.13,<3' in pyproject
    assert "client.interactions.create" in gemini
    assert "output_text" in gemini
    assert "HEALTHIA_GOOGLE_AI_READY" in verifier


def test_launcher_uses_file_based_utf8_probe_and_lan_urls() -> None:
    launcher = (ROOT / "deployment/run-local-secure.ps1").read_text(encoding="utf-8")
    assert "verify_google_ai.py" in launcher
    assert "python -c" not in launcher
    assert "PYTHONUTF8" in launcher
    assert "HEALTHIA_COST_MODE" in launcher
    assert "Get-NetIPAddress" in launcher
    assert "0.0.0.0" in launcher


def test_windows_start_helper_is_location_independent() -> None:
    start = (ROOT / "START-HEALTHIA.cmd").read_text(encoding="utf-8")
    assert "%~dp0" in start
    assert "run-local-secure.ps1" in start
    assert "GuardedAi" in start


def test_android_toolchain_contract_is_buildable() -> None:
    root_gradle = (ROOT / "android-health-bridge/build.gradle.kts").read_text(encoding="utf-8")
    app_gradle = (ROOT / "android-health-bridge/app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'org.jetbrains.kotlin.plugin.compose' in root_gradle
    assert "compileSdk = 35" in app_gradle
    assert "targetSdk = 35" in app_gradle
    assert "composeOptions" not in app_gradle


def test_runtime_affordances_are_real_not_decorative() -> None:
    runtime = (ROOT / "web/runtime-integrations.js").read_text(encoding="utf-8")
    providers = (ROOT / "web/provider-integrations.js").read_text(encoding="utf-8")
    cost_control = (ROOT / "web/cost-control.js").read_text(encoding="utf-8")
    icons = (ROOT / "web/icons.js").read_text(encoding="utf-8")
    interactions = (ROOT / "web/interactions.css").read_text(encoding="utf-8")
    assert "SpeechRecognition" in runtime
    assert 'json("/api/ai/test", {method: "POST"})' in runtime
    assert 'button.setAttribute("aria-pressed"' in runtime
    assert "/assets/runtime-integrations.js" in icons
    assert "/assets/provider-integrations.js" in icons
    assert "/assets/cost-control.js" in icons
    # Device/provider discovery now inherits the one authenticated transport
    # instead of bypassing patient identity with a raw fetch.
    assert '(window.healthiaFetch || fetch)("/api/devices")' in providers
    assert "provider_catalog" in providers
    assert "/api/cost-control" in cost_control
    assert "IA activa" in cost_control
    assert "Local · 0 llamadas" in cost_control
    assert ".provider-grid" in interactions
    assert 'content: "Abrir menú"' in interactions
    assert "background: transparent" in interactions


def test_cloud_demo_is_scale_to_zero_and_easy_to_destroy() -> None:
    deploy = (ROOT / "deployment/deploy-cloud-demo.ps1").read_text(encoding="utf-8")
    remove = (ROOT / "deployment/remove-cloud-demo.ps1").read_text(encoding="utf-8")
    assert '"--min-instances", "0"' in deploy
    assert '"--max-instances", "1"' in deploy
    assert '"--cpu-throttling"' in deploy
    assert "HEALTHIA_COST_MODE=cloud_demo" in deploy
    assert "HEALTHIA_PROACTIVE_ENABLED=false" in deploy
    assert "HEALTHIA_MISSION_RUNTIME=adk" in deploy
    assert "HEALTHIA_EVENT_DISPATCH_BACKEND=pubsub" in deploy
    assert "pubsub" in deploy.lower()
    assert "scheduler" in deploy.lower() and '"pause"' in deploy
    assert "roles/run.invoker" in deploy
    assert "roles/iam.serviceAccountTokenCreator" in deploy
    assert "--no-allow-unauthenticated" in deploy
    assert '"run", "services", "delete"' in remove
    assert '"pubsub", "subscriptions", "delete"' in remove
    assert "projects delete" in remove or '"projects", "delete"' in remove
