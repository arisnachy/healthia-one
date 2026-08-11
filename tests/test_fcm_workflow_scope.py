from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fcm_workflow_tracks_production_wiring_and_consent_contracts() -> None:
    workflow = (ROOT / ".github/workflows/google-fcm-live-delivery.yml").read_text(encoding="utf-8")

    for path in (
        "app/main.py",
        "healthia_one/auth_web.py",
        "healthia_one/fcm_registration.py",
        "healthia_one/fcm_device_api.py",
        "tests/test_fcm_delivery_ack.py",
        "tests/test_fcm_device_api_e2e.py",
        "tests/test_fcm_app_wiring.py",
    ):
        assert path in workflow


def test_fcm_preflight_scopes_firestore_and_reports_privacy_tombstones() -> None:
    workflow = (ROOT / ".github/workflows/google-fcm-live-delivery.yml").read_text(encoding="utf-8")

    assert "path.startswith('healthia_fcm_registrations/')" in workflow
    assert "fcm_registration_documents" in workflow
    assert "fcm_privacy_tombstones" in workflow
    assert "fcm_token_bearing_documents" in workflow
    assert "active_fcm_registration_count" in workflow
    assert "healthia_fcm_registrations/*/devices/*" in workflow
    assert "len(candidates)!=1" in workflow
