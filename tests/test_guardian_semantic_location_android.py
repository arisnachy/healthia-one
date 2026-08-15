from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "android-health-bridge"
SOURCE = BRIDGE / "app/src/main/java/com/healthia/one/bridge"


def test_guardian_semantic_geofence_dependency_permissions_and_private_receiver() -> None:
    gradle = (BRIDGE / "app/build.gradle.kts").read_text(encoding="utf-8")
    manifest = (BRIDGE / "app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")

    assert 'com.google.android.gms:play-services-location:21.3.0' in gradle
    for permission in (
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_BACKGROUND_LOCATION",
    ):
        assert permission in manifest
    assert 'android:name=".GuardianGeofenceReceiver"' in manifest
    assert 'android:exported="false"' in manifest
    assert "READ_EXERCISE_ROUTES" not in manifest


def test_guardian_semantic_location_keeps_coordinates_device_local() -> None:
    location = (SOURCE / "GuardianSemanticLocation.kt").read_text(encoding="utf-8")
    api = (SOURCE / "HealthiaApi.kt").read_text(encoding="utf-8")
    worker = (SOURCE / "HealthSyncWorker.kt").read_text(encoding="utf-8")

    assert 'val supportedLabels: Set<String> = setOf("home", "work", "gym")' in location
    assert '"semantic_location_authorized" to active' in location
    assert '"location_context" to if (active) currentLabel(context) else "unknown"' in location
    assert "setCircularRegion(latitude, longitude, radius)" in location
    assert "GuardianSemanticLocation.enrich(applicationContext, healthRecords)" in worker
    assert 'put("metadata", JSONObject(record.metadata))' in api

    # Raw coordinates exist only in local geofence storage/registration code and
    # are not part of HealthRecordDto/HealthiaApi field names.
    assert 'put("latitude"' not in api
    assert 'put("longitude"' not in api
    assert 'put("lat"' not in api
    assert 'put("lng"' not in api


def test_guardian_semantic_location_requires_incremental_patient_permission_and_can_be_deleted() -> None:
    activity = (SOURCE / "MainActivity.kt").read_text(encoding="utf-8")
    location = (SOURCE / "GuardianSemanticLocation.kt").read_text(encoding="utf-8")

    for marker in (
        "GUARDIAN_FOREGROUND_LOCATION_REQUEST",
        "GUARDIAN_BACKGROUND_LOCATION_REQUEST",
        "ACCESS_FINE_LOCATION",
        "ACCESS_BACKGROUND_LOCATION",
        "Settings.ACTION_APPLICATION_DETAILS_SETTINGS",
        "Marcar Casa",
        "Marcar Trabajo",
        "Marcar Gimnasio",
        "Pausar lugar",
        "Borrar lugares",
    ):
        assert marker in activity

    assert "fun disable(" in location
    assert "fun forgetAllPlaces(" in location
    assert ".edit().clear().apply()" in location


def test_geofence_receiver_updates_only_coarse_label_and_performs_no_network_action() -> None:
    location = (SOURCE / "GuardianSemanticLocation.kt").read_text(encoding="utf-8")

    assert "class GuardianGeofenceReceiver : BroadcastReceiver()" in location
    assert "GeofencingEvent.fromIntent" in location
    assert "GuardianSemanticLocation.setCurrentFromGeofence" in location
    assert "GuardianSemanticLocation.clearCurrentFromGeofence" in location
    assert "HealthiaApi" not in location
    assert "HttpURLConnection" not in location
