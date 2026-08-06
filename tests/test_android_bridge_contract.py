from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_android_health_bridge_declares_health_connect_and_background_access() -> None:
    gradle = (ROOT / "android-health-bridge/app/build.gradle.kts").read_text(encoding="utf-8")
    manifest = (ROOT / "android-health-bridge/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    repository = (ROOT / "android-health-bridge/app/src/main/java/com/healthia/one/bridge/HealthConnectRepository.kt").read_text(encoding="utf-8")
    assert 'androidx.health.connect:connect-client:1.1.0' in gradle
    for permission in (
        "READ_STEPS",
        "READ_HEART_RATE",
        "READ_BLOOD_PRESSURE",
        "READ_WEIGHT",
        "READ_OXYGEN_SATURATION",
        "READ_HEALTH_DATA_IN_BACKGROUND",
    ):
        assert permission in manifest
    assert "HealthConnectClient.getOrCreate" in repository
    assert "sourcePackage" in repository
    assert "externalId" in repository


def test_profile_and_devices_ui_contract() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    js = (ROOT / "web/profile-devices.js").read_text(encoding="utf-8")
    css = (ROOT / "web/styles.css").read_text(encoding="utf-8")
    assert "/assets/styles.css" in html
    assert "/assets/profile-devices.js" in html
    for marker in (
        "Perfil del paciente",
        "Dispositivos",
        "Salud gineco-obstétrica",
        "Health Connect",
        "Glicemia",
        "Estado nutricional",
    ):
        assert marker in js
    assert ".vital-matrix" in css
    assert ".device-grid" in css
