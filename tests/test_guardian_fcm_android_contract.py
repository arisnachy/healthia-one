from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "android-health-bridge/app/src/main/java/com/healthia/one/bridge"


def test_guardian_fcm_uses_stable_proof_to_avoid_repeated_visible_alerts() -> None:
    runtime = (SOURCE / "FirebaseRuntime.kt").read_text(encoding="utf-8")
    service = (SOURCE / "HealthiaFirebaseMessagingService.kt").read_text(encoding="utf-8")

    assert "deliveryProofAlreadyShown" in runtime
    assert "markDeliveryProofShown" in runtime
    assert "SHOWN_PROOF_IDS" in runtime
    assert "MAX_SHOWN_PROOFS" in runtime

    assert "FirebaseRuntime.deliveryProofAlreadyShown" in service
    assert "FirebaseRuntime.markDeliveryProofShown" in service
    assert "if (alreadyShown)" in service
    assert "true" in service
    assert "showNeutralNotification()" in service
    assert "FirebaseRuntime.acknowledgeDelivery" in service
