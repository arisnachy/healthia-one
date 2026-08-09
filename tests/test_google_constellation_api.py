from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


AUTH_SOURCE = Path("healthia_one/auth_web.py").read_text(encoding="utf-8")


def test_constellation_routes_are_not_in_public_auth_allowlist():
    public_block = AUTH_SOURCE.split("public_exact = {", 1)[1].split("}", 1)[0]
    assert "/api/google-constellation" not in public_block
    assert "build_google_constellation_router" in AUTH_SOURCE


def test_capabilities_expose_connection_metadata_but_never_secret_material():
    with TestClient(app) as client:
        response = client.get("/api/google-constellation/capabilities")
        assert response.status_code == 200
        payload = response.json()
        assert payload["patient_id"] == "patient_demo"
        assert payload["google_account_connection"]["secret_material_exposed"] is False
        serialized = str(payload).lower()
        assert "refresh_token" not in serialized
        assert "client_secret" not in serialized
        assert "secret_version_resource" not in serialized


def test_api_creates_patient_scoped_mission_and_exact_authorization_without_external_action():
    with TestClient(app) as client:
        grant = client.post(
            "/api/google-constellation/grants",
            json={"bundle": "gmail_send", "enabled": True},
        )
        assert grant.status_code == 200
        assert grant.json()["patient_id"] == "patient_demo"

        created = client.post(
            "/api/google-constellation/missions/navigation",
            json={
                "condition_or_need": "autism support for son",
                "provider_query": "autism support center",
                "lat": 19.4517,
                "lng": -70.6970,
            },
        )
        assert created.status_code == 200
        mission = created.json()
        assert mission["patient_id"] == "patient_demo"
        assert mission["state"] == "received"
        assert mission["private_reasoning"] is None
        mission_id = mission["id"]

        fetched = client.get(f"/api/google-constellation/missions/{mission_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == mission_id

        exact_payload = {
            "to": ["center@example.org"],
            "subject": "Appointment",
            "body": "Please advise.",
        }
        authorization = client.post(
            f"/api/google-constellation/missions/{mission_id}/authorize",
            json={
                "action": "gmail.send",
                "payload": exact_payload,
                "ttl_minutes": 5,
                "one_time": True,
            },
        )
        assert authorization.status_code == 200
        auth_payload = authorization.json()
        assert auth_payload["external_action_performed"] is False
        assert auth_payload["authorization"]["patient_id"] == "patient_demo"
        assert auth_payload["authorization"]["mission_id"] == mission_id
        assert auth_payload["authorization"]["action"] == "gmail.send"
        assert len(auth_payload["authorization"]["intent_key"]) == 64
        assert "exact patient + mission + action + payload fingerprint" in auth_payload["truth_boundary"]
        assert "not an execution receipt" in auth_payload["truth_boundary"]
