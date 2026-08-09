from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_google_sdk_matches_interactions_api() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    gemini = (ROOT / "healthia_one/gemini.py").read_text(encoding="utf-8")
    transport_path = ROOT / "healthia_one/google_ai_transport.py"
    assert '"google-genai>=2.13,<3"' in pyproject
    assert '"google-adk>=2.5,<3"' in pyproject
    assert "google-adk[gcp]" not in pyproject
    assert '"google-cloud-firestore>=2.21,<3"' in pyproject
    assert '"google-cloud-storage>=3.3,<4"' in pyproject
    assert gemini.count(".interactions.create(") >= 2
    assert "def _interaction_text" in gemini
    if transport_path.exists():
        transport = transport_path.read_text(encoding="utf-8")
        assert "build_google_ai_client" in gemini
        assert "genai.Client(api_key=api_key)" in transport
        assert "genai.Client(vertexai=True, project=project, location=location)" in transport
        assert "VertexInteractionsAdapter" in transport
        assert "response_json_schema" in transport
        assert "thinking_config" in transport
    else:
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
    assert '[switch]$AllowLan' in launcher
    assert 'if ($AllowLan) { "0.0.0.0" } else { "127.0.0.1" }' in launcher
    assert 'if ($Reload) { $uvicornArgs += "--reload" }' in launcher
    assert "HEALTHIA_GOOGLE_AI_READY" in verifier
    assert "HEALTHIA_GOOGLE_AI_ERROR" in verifier
    assert "genai.Client(vertexai=True" in verifier
    assert "client.interactions.create" in verifier
    assert '"gemini-3.5-flash"' in verifier


def test_android_bridge_uses_supported_compose_toolchain() -> None:
    root_gradle = (ROOT / "android-health-bridge/build.gradle.kts").read_text(encoding="utf-8")
    app_gradle = (ROOT / "android-health-bridge/app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'id("org.jetbrains.kotlin.plugin.compose") version "2.1.0"' in root_gradle
    assert 'id("com.android.application") version "8.9.1"' in root_gradle
    assert 'id("org.jetbrains.kotlin.plugin.compose")' in app_gradle
    assert "compileSdk = 36" in app_gradle
    assert "targetSdk = 36" in app_gradle
    assert "minSdk = 28" in app_gradle
    assert "JavaVersion.VERSION_17" in app_gradle
    assert "jvmToolchain(17)" in app_gradle
    assert "composeOptions" not in app_gradle


def test_ci_validates_semantic_runtime_modules_and_both_labs() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in workflow
    assert "deployment/verify_google_ai.py" in workflow
    assert "node --check web/runtime-integrations.js" in workflow
    assert "node --check web/provider-integrations.js" in workflow
    assert "node --check web/cost-control.js" in workflow
    assert "LAB OMEGA core full-window functional laboratory" in workflow
    assert "python scripts/lab_omega.py" in workflow
    assert "HealthIA-LAB-OMEGA" in workflow
    assert "LAB OMEGA secondary windows and state-changing functions" in workflow
    assert "python scripts/lab_omega_secondary.py" in workflow
    assert "HealthIA-LAB-OMEGA-secondary" in workflow
    assert "deployment/deploy-cloud-demo.ps1" in workflow
    assert "deployment/remove-cloud-demo.ps1" in workflow


def test_runtime_affordances_are_real_locale_aware_and_not_decorative() -> None:
    index = (ROOT / "web/index.html").read_text(encoding="utf-8")
    runtime = (ROOT / "web/runtime-integrations.js").read_text(encoding="utf-8")
    providers = (ROOT / "web/provider-integrations.js").read_text(encoding="utf-8")
    cost_control = (ROOT / "web/cost-control.js").read_text(encoding="utf-8")
    icons = (ROOT / "web/icons.js").read_text(encoding="utf-8")
    interactions = (ROOT / "web/interactions.css").read_text(encoding="utf-8")
    for source in (runtime, providers, cost_control):
        assert "window.HealthIAI18n" in source
        assert "Accept-Language" in source
    assert "SpeechRecognition" in runtime
    assert 'json("/api/readiness")' in runtime
    assert "Continuity connected" in runtime and "Continuidad conectada" in runtime
    assert "dataset.runtimeBackend" in runtime and "dataset.runtimeModel" in runtime
    assert "dataset.aiReady" in runtime and "dataset.adkReady" in runtime
    assert 'json("/api/ai/test",{method:"POST"})' not in runtime
    assert "label.onclick=null" in runtime and "label.onkeydown=null" in runtime
    assert 'button.setAttribute("aria-pressed"' in runtime
    assert "recognition.lang=localeTag()" in runtime
    for asset in ("runtime-integrations.js", "provider-integrations.js", "cost-control.js"):
        assert index.count(f'/assets/{asset}') == 1
        assert f'/assets/{asset}' not in icons
    assert "loadScript(" not in icons
    assert "document.createElement('script')" not in icons
    assert 'fetch("/api/devices",{headers:{"Accept-Language"' in providers
    assert "provider_catalog" in providers
    assert "/api/cost-control" in cost_control
    assert "AI active" in cost_control and "IA activa" in cost_control
    assert "Vertex AI active" in cost_control and "Vertex AI activo" in cost_control
    assert "Local · 0 calls" in cost_control and "Local · 0 llamadas" in cost_control
    assert "costGuardButton" in cost_control
    assert "costGuardToggle" in cost_control
    assert "/api/ai/test" in cost_control
    assert ".provider-grid" in interactions
    assert 'id="expandLeft"' in index
    assert 'data-i18n-aria="nav.expand"' in index
    assert 'content: "Abrir menú"' not in interactions
    assert "background: transparent" in interactions


def test_cloud_demo_is_vertex_native_scale_to_zero_and_easy_to_destroy() -> None:
    deploy = (ROOT / "deployment/deploy-cloud-demo.ps1").read_text(encoding="utf-8")
    remove = (ROOT / "deployment/remove-cloud-demo.ps1").read_text(encoding="utf-8")
    assert '"--min", "0"' in deploy
    assert '"--max", "1"' in deploy
    assert "HEALTHIA_COST_MODE=cloud_demo" in deploy
    assert "HEALTHIA_PROACTIVE_ENABLED=false" in deploy
    assert "HEALTHIA_MODEL=gemini-3.5-flash" in deploy
    assert "GOOGLE_GENAI_USE_VERTEXAI=true" in deploy
    assert "GOOGLE_CLOUD_LOCATION=$VertexLocation" in deploy
    assert '"aiplatform.googleapis.com"' in deploy
    assert '"roles/aiplatform.user"' in deploy
    assert '"roles/run.builder"' in deploy
    assert "healthia-one-build" in deploy
    assert '"--build-service-account"' in deploy
    assert "healthia-one-demo" in deploy
    assert "GEMINI_API_KEY=" not in deploy
    assert "healthia-gemini-api-key" not in deploy
    assert "HEALTHIA_DEVICE_TOKEN_SECRET=" in deploy
    assert "HEALTHIA_SESSION_SECRET=" in deploy
    assert "--no-allow-unauthenticated" in deploy
    assert "gcloud run services delete" in remove
    assert "DeleteBuildServiceAccount" in remove
    assert "healthia-gemini-api-key" not in remove
    assert "gcloud projects delete" in remove
