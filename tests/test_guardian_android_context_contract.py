from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "android-health-bridge"
SOURCE = BRIDGE / "app/src/main/java/com/healthia/one/bridge"


def test_android_guardian_requests_only_coarse_health_context_not_exercise_routes() -> None:
    manifest = (BRIDGE / "app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    repository = (SOURCE / "HealthConnectRepository.kt").read_text(encoding="utf-8")

    for permission in (
        "android.permission.health.READ_EXERCISE",
        "android.permission.health.READ_HEART_RATE_VARIABILITY",
        "android.permission.health.READ_SLEEP",
    ):
        assert permission in manifest

    assert "READ_EXERCISE_ROUTES" not in manifest
    assert "ExerciseRoute" not in repository
    assert "ExerciseSessionRecord" in repository
    assert "HeartRateVariabilityRmssdRecord" in repository
    assert "SleepSessionRecord" in repository


def test_android_guardian_correlates_context_into_signal_metadata() -> None:
    repository = (SOURCE / "HealthConnectRepository.kt").read_text(encoding="utf-8")
    api = (SOURCE / "HealthiaApi.kt").read_text(encoding="utf-8")

    for marker in (
        'metadata["exercise_session_active"] = true',
        'metadata["activity_type"]',
        'metadata["hrv_rmssd_ms"]',
        'metadata["sleep_minutes"]',
        "guardianMetadata = contextAt(sample.time)",
        "guardianMetadata = contextAt(record.time)",
    ):
        assert marker in repository

    assert "val metadata: Map<String, Any> = emptyMap()" in repository
    assert 'put("metadata", JSONObject(record.metadata))' in api


def test_android_guardian_activity_mapping_is_bounded_and_does_not_invent_location() -> None:
    repository = (SOURCE / "HealthConnectRepository.kt").read_text(encoding="utf-8")

    assert '-> "running"' in repository
    assert '-> "walking"' in repository
    assert '-> "cycling"' in repository
    assert 'else -> "exercise"' in repository
    assert '"location_context"' not in repository
    assert '"semantic_location_authorized"' not in repository
