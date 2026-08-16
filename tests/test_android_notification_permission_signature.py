from pathlib import Path


ACTIVITY = Path("android-health-bridge/app/src/main/java/com/healthia/one/bridge/MainActivity.kt")


def test_android_notification_permission_callback_matches_component_activity_signature() -> None:
    text = ACTIVITY.read_text(encoding="utf-8")
    assert "override fun onRequestPermissionsResult(" in text
    assert "permissions: Array<String>," in text
    assert "permissions: Array<out String>," not in text
    assert "super.onRequestPermissionsResult(requestCode, permissions, grantResults)" in text
    assert "pendingNotificationOptInCompletion ?: return" in text
    assert "setPrivateNotifications(true, complete)" in text
