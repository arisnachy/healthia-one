from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_google_sdk_matches_interactions_api() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    gemini = (ROOT / "healthia_one/gemini.py").read_text(encoding="utf-8")
    assert '"google-genai>=2.13,<3"' in pyproject
    assert '"google-adk[gcp]>=2.5,<3"' in pyproject
    assert gemini.count(".interactions.create(") >= 2
    assert "def _interaction_text" in gemini
    assert 'genai.Client(api_key=api_key)' in gemini
    assert "cost_guard.authorize" in gemini
    assert '"max_output_tokens"' in gemini
    assert '"thinking_level": "minimal"' in gemini


def test_secure_launcher_defaults_to_zero_spend_and_requires_explicit_ai() -> None:
    launcher = (ROOT / "deployment/run-local-secure.ps1").read_text(encoding="utf-8")
    verifier = (ROOT / "deployment/verify_google_ai.py").read_text(encoding="utf-8")
    assert '[switch]$GuardedAi' in launcher
    assert '$useGuardedAi = $GuardedAi -or $Gemini' in launcher
    assert '$env:HEALTHIA_LLM_BACKEND = "mock"' in launcher
    assert '$env:HEALTHIA_COST_MODE = "local"' in launcher
    assert '$env:HEALTHIA_AI_REQUEST_LIMIT = "0"' in launcher
    assert "LOCAL SEGURO - cero llamadas" in launcher
    assert '$env:HEALTHIA_COST_GUARD_START_ENABLED' in launcher
    assert 'Join-Path $PSScriptRoot "verify_google_ai.py"' in launcher
    assert "if ($LiveProbe)" in launcher
    assert "$probeOutput = & $venvPython $probeScript" in launcher
    assert "La prueba consumio 1" in launcher
    assert "-c $probe" not in launcher
    assert "$env:PYTHONUTF8 = \"1\"" in launcher
    assert "Get-NetIPAddress" in launcher
    assert "Telefono en la misma Wi-Fi" in launcher
    assert "--host 0.0.0.0" in launcher
    assert "client.interactions.create" in verifier
    assert "HEALTHIA_GOOGLE_AI_READY" in verifier
    assert "HEALTHIA_GOOGLE_AI_ERROR" in verifier
    assert "store=False" in verifier


def test_android_bridge_uses_supported_compose_toolchain() -> None:
    root_gradle = (ROOT / "android-health-bridge/build.gradle.kts").read_text(encoding="utf-8")
    app_gradle = (ROOT / "android-health-bridge/app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'id("org.jetbrains.kotlin.plugin.compose") version "2.1.0"' in root_gradle
    assert 'id("org.jetbrains.kotlin.plugin.compose")' in app_gradle
    assert "compileSdk = 35" in app_gradle
    assert "targetSdk = 35" in app_gradle
    assert "minSdk = 28" in app_gradle
    assert "composeOptions" not in app_gradle


def test_ci_validates_semantic_runtime_modules() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in workflow
    assert "deployment/verify_google_ai.py" in workflow
    assert "node --check web/runtime-integrations.js" in workflow
    assert "node --check web/provider-integrations.js" in workflow
    assert "node --check web/cost-control.js" in workflow
    assert "deployment/deploy-cloud-demo.ps1" in workflow
    assert "deployment/remove-cloud-demo.ps1" in workflow


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
    assert 'fetch("/api/devices")' in providers
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
