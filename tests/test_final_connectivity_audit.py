from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
ANDROID = ROOT / "android-health-bridge"
SOURCE = ANDROID / "app/src/main/java/com/healthia/one/bridge"


def test_gemini_calls_are_stateless_and_the_probe_is_a_live_interaction() -> None:
    gemini = (ROOT / "healthia_one/gemini.py").read_text(encoding="utf-8")
    launcher = (ROOT / "deployment/run-local-secure.ps1").read_text(encoding="utf-8")
    verifier = (ROOT / "deployment/verify_google_ai.py").read_text(encoding="utf-8")
    assert gemini.count("store=False") >= 2
    assert "def _live_probe" in gemini
    assert "live_request" in gemini
    assert '"store": False' in gemini
    assert "store=False" in verifier
    assert "HEALTHIA_GOOGLE_AI_READY" in verifier
    assert "HEALTHIA_GOOGLE_AI_ERROR" in verifier
    assert "if ($LiveProbe)" in launcher
    assert "$probeOutput = & $venvPython $probeScript" in launcher
    assert "Get-NetIPAddress" in launcher


def test_runtime_exposes_retryable_google_status_complete_device_links_and_i18n() -> None:
    runtime = (WEB / "runtime-integrations.js").read_text(encoding="utf-8")
    css = (WEB / "interactions.css").read_text(encoding="utf-8")
    for marker in (
        "/api/ai/test",
        "resource_exhausted",
        "Google AI quota is currently exhausted",
        "La cuota de Google AI",
        "Connect phone or watch",
        "Conectar teléfono o reloj",
        "actions/workflows/android-bridge.yml",
        "CONNECT_ANDROID.md",
        "HealthIA-Bridge-debug",
        "Phone and computer on the same Wi-Fi",
        "Teléfono y computadora",
        "reopen.textContent=\"›\"",
        'event.key.toLowerCase()!=="b"',
        "window.HealthIAI18n",
        "Accept-Language",
        "recognition.lang=localeTag()",
    ):
        assert marker in runtime
    assert ".runtime-ai-control" in css
    assert ".lan-help" in css


def test_composer_has_no_separate_visual_container() -> None:
    css = (WEB / "interactions.css").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "#view-chat .composer-wrap" in css
    assert "position: absolute" in css
    assert "background: transparent" in css
    assert "pointer-events: none" in css
    assert 'class="composer-context"' not in html


def test_android_checks_provider_and_background_feature_before_reading() -> None:
    manifest = (ANDROID / "app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    repository = (SOURCE / "HealthConnectRepository.kt").read_text(encoding="utf-8")
    worker = (SOURCE / "HealthSyncWorker.kt").read_text(encoding="utf-8")
    activity = (SOURCE / "MainActivity.kt").read_text(encoding="utf-8")
    assert 'package android:name="com.google.android.apps.healthdata"' in manifest
    assert "androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE" in manifest
    assert "PermissionsRationaleActivity" in manifest
    assert "HealthConnectClient.getSdkStatus" in repository
    assert "FEATURE_READ_HEALTH_DATA_IN_BACKGROUND" in repository
    assert "providerInstallIntent" in repository
    assert "supportsBackgroundRead" in worker
    assert "Instalar o actualizar Health Connect" in activity
    assert "Autorizar datos en Health Connect" in activity
    assert "Sincronizar ahora" in activity


def test_android_artifact_and_connection_guide_are_permanent() -> None:
    workflow = (ROOT / ".github/workflows/android-bridge.yml").read_text(encoding="utf-8")
    guide = (ROOT / "docs/CONNECT_ANDROID.md").read_text(encoding="utf-8")
    assert "gradle :app:assembleDebug" in workflow
    assert "HealthIA-Bridge-debug.apk" in workflow
    assert "HealthIA-Bridge-debug" in guide
    assert "127.0.0.1" in guide
    assert "ipconfig" in guide