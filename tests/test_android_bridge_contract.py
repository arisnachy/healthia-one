from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "android-health-bridge"
SOURCE = BRIDGE / "app/src/main/java/com/healthia/one/bridge"


def test_android_health_bridge_declares_availability_permissions_and_rationale() -> None:
    gradle = (BRIDGE / "app/build.gradle.kts").read_text(encoding="utf-8")
    manifest = (BRIDGE / "app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    repository = (SOURCE / "HealthConnectRepository.kt").read_text(encoding="utf-8")
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
    assert 'package android:name="com.google.android.apps.healthdata"' in manifest
    assert "androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE" in manifest
    assert "PermissionsRationaleActivity" in manifest
    assert "HealthConnectClient.getSdkStatus" in repository
    assert "FEATURE_READ_HEALTH_DATA_IN_BACKGROUND" in repository
    assert "providerInstallIntent" in repository
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


def test_android_bridge_guides_pairing_permissions_and_background_sync() -> None:
    activity = (SOURCE / "MainActivity.kt").read_text(encoding="utf-8")
    api = (SOURCE / "HealthiaApi.kt").read_text(encoding="utf-8")
    worker = (SOURCE / "HealthSyncWorker.kt").read_text(encoding="utf-8")
    rationale = (SOURCE / "PermissionsRationaleActivity.kt").read_text(encoding="utf-8")
    assert "Código temporal de ocho dígitos" in activity
    assert "HealthiaApi.claim" in activity
    assert 'putString("access_token"' in activity
    assert "Instalar o actualizar Health Connect" in activity
    assert "Abrir configuración de Health Connect" in activity
    assert "supportsBackgroundRead" in activity
    assert 'setRequestProperty("Authorization", "Bearer $token")' in api
    assert 'getString("base_url"' in worker
    assert 'getString("access_token"' in worker
    assert "supportsBackgroundRead" in worker
    assert "Cómo usa HealthIA tus datos" in rationale


def test_android_fcm_registration_delivery_and_ack_contract_is_wired_end_to_end() -> None:
    gradle = (BRIDGE / "app/build.gradle.kts").read_text(encoding="utf-8")
    manifest = (BRIDGE / "app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    activity = (SOURCE / "MainActivity.kt").read_text(encoding="utf-8")
    api = (SOURCE / "HealthiaApi.kt").read_text(encoding="utf-8")
    runtime = (SOURCE / "FirebaseRuntime.kt").read_text(encoding="utf-8")
    service = (SOURCE / "HealthiaFirebaseMessagingService.kt").read_text(encoding="utf-8")
    registration_worker = (SOURCE / "FcmRegistrationWorker.kt").read_text(encoding="utf-8")
    ack_worker = (SOURCE / "FcmDeliveryAckWorker.kt").read_text(encoding="utf-8")

    assert "firebase-messaging" in gradle
    assert "work-runtime-ktx" in gradle
    for build_value in (
        "HEALTHIA_FIREBASE_APP_ID",
        "HEALTHIA_FIREBASE_API_KEY",
        "HEALTHIA_FIREBASE_PROJECT_ID",
        "HEALTHIA_FIREBASE_SENDER_ID",
    ):
        assert build_value in gradle
    assert "android.permission.POST_NOTIFICATIONS" in manifest
    assert "HealthiaFirebaseMessagingService" in manifest
    assert "com.google.firebase.MESSAGING_EVENT" in manifest
    assert activity.count("FirebaseRuntime.syncRegistration") >= 2
    assert "requestNotificationPermissionIfNeeded" in activity
    assert "Desactivar notificaciones privadas" in activity
    assert "Reactivar notificaciones privadas" in activity
    assert "HealthiaApi.disableFcm" in activity
    assert "HealthiaApi.explicitlyEnableFcm" in activity
    assert "/api/devices/fcm/register" in api
    assert "/api/devices/fcm/register/enable" in api
    assert 'method = "DELETE"' in api
    assert "/api/devices/fcm/ack" in api
    assert "fcm_notifications_enabled" in runtime
    assert "FcmRegistrationWorker.cancel" in runtime
    assert "FcmRegistrationWorker.enqueue" in runtime
    assert "FcmDeliveryAckWorker.enqueue" in runtime
    assert "onNewToken" in service
    assert "FirebaseRuntime.syncRegistration" in service
    assert "FirebaseRuntime.notificationsEnabled" in service
    assert "onMessageReceived" in service
    assert 'message.data["proof_id"]' in service
    assert 'kind != "healthia_update"' in service
    assert 'setContentTitle("HealthIA")' in service
    assert 'setContentText("Tienes una actualización disponible en HealthIA.")' in service

    for worker in (registration_worker, ack_worker):
        assert "CoroutineWorker" in worker
        assert "NetworkType.CONNECTED" in worker
        assert "BackoffPolicy.EXPONENTIAL" in worker
        assert "setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)" in worker
        assert "Result.retry()" in worker
    assert "FirebaseRuntime.notificationsEnabled" in registration_worker
    assert "FirebaseMessaging.getInstance().token" in registration_worker
    assert "Tasks.await" in registration_worker
    assert "ExistingWorkPolicy.REPLACE" in registration_worker
    assert "cancelUniqueWork" in registration_worker
    assert "HealthiaApi.registerFcm" in registration_worker
    assert "ExistingWorkPolicy.KEEP" in ack_worker
    assert "HealthiaApi.acknowledgeFcm" in ack_worker
    assert "MessageDigest.getInstance(\"SHA-256\")" in ack_worker


def test_repository_compiles_android_but_only_publishes_fcm_ready_apk() -> None:
    workflow = (ROOT / ".github/workflows/android-bridge.yml").read_text(encoding="utf-8")
    guide = (ROOT / "docs/CONNECT_ANDROID.md").read_text(encoding="utf-8")
    extractor = (ROOT / "scripts/extract_firebase_android_config.py").read_text(encoding="utf-8")
    assert "gradle :app:assembleDebug" in workflow
    assert "HEALTHIA_FIREBASE_ANDROID_CONFIG_B64" in workflow
    assert "HEALTHIA_FIREBASE_ANDROID_CONFIG_JSON" in workflow
    assert "scripts/extract_firebase_android_config.py" in workflow
    assert "--format base64" in workflow
    assert "base64.b64decode" in extractor
    assert "com.healthia.one.bridge" in workflow
    assert "GOOGLE_SERVICES_JSON_BASE64_SECRET" in workflow
    assert "GOOGLE_SERVICES_JSON_SECRET" in workflow
    assert "FIREBASE_MANAGEMENT_API_EPHEMERAL" in workflow
    assert "FOUR_ACTIONS_SECRETS" in workflow
    assert "BLOCKED_FIREBASE_CONFIG" in workflow
    assert "CODE PASS != FCM-READY APK" in workflow
    assert "steps.firebase.outputs.fcm_ready == 'true'" in workflow
    assert "Remove non-FCM-ready APK from workspace" in workflow
    assert "HealthIA-Bridge-debug.apk" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "HealthIA-Android-APK-Readiness" in workflow
    assert "HEALTHIA_FIREBASE_ANDROID_CONFIG_B64" in guide
    assert "HEALTHIA_FIREBASE_ANDROID_CONFIG_JSON" in guide
    assert "HealthIA-Bridge-debug" in guide
    assert "127.0.0.1" in guide
    assert "ipconfig" in guide


def test_firebase_readonly_iam_gate_is_narrow_and_chains_only_after_success() -> None:
    workflow = (ROOT / ".github/workflows/google-firebase-ci-readonly-iam.yml").read_text(encoding="utf-8")
    assert "I_AUTHORIZE_FCM_VIEWER_FOR_CI" in workflow
    assert "roles/firebasecloudmessaging.viewer" in workflow
    assert "roles/firebase.viewer" not in workflow
    assert "firebase.clients.get" in workflow
    assert "firebase.clients.list" in workflow
    assert "firebase.projects.get" in workflow
    assert "resourcemanager.projects.setIamPolicy" in workflow
    assert "testIamPermissions" in workflow
    assert "can_set_iam_policy" in workflow
    assert "firebase_ready: ${{ steps.postcheck.outputs.firebase_ready }}" in workflow
    assert "needs.firebase-ci-readonly-iam.outputs.firebase_ready == 'true'" in workflow
    assert "actions: write" in workflow
    assert '"ref":"kira/google-constellation-wave2-live"' in workflow
    assert "actions/workflows/android-bridge.yml/dispatches" in workflow
    assert "api_enable_mutation':False" in workflow
    assert "provider_write':False" in workflow


def test_fcm_live_proof_uses_unpredictable_nonce_and_waits_for_durable_ack() -> None:
    workflow = (ROOT / ".github/workflows/google-fcm-live-delivery.yml").read_text(encoding="utf-8")
    assert "FcmRegistrationWorker.kt" in workflow
    assert "FcmDeliveryAckWorker.kt" in workflow
    assert "secrets.token_hex(16)" in workflow
    assert "proof_id_sha256" in workflow
    assert "raw_proof_id_exposed':False" in workflow
    assert "for _ in range(60)" in workflow
    assert "time.sleep(4)" in workflow
    assert "I_AUTHORIZE_CONTROLLED_FCM_PROOF" in workflow
    assert "provider accepted" not in workflow.lower()
