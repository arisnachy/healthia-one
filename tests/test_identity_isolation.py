from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app, identity_verifier, settings
from healthia_one.config import Settings
from healthia_one.documents import build_document
from healthia_one.identity import AuthPrincipal, IdentityError, IdentityVerifier
from healthia_one.models import PatientProfile, WeightRecord
from healthia_one.pairing import DevicePairingManager
from healthia_one.service import HealthIAService
from healthia_one.tenant import patient_scope


def test_patient_profile_defaults_do_not_assume_synthetic_medical_facts() -> None:
    profile = PatientProfile()
    assert profile.display_name == "Paciente"
    assert profile.birth_date is None
    assert profile.sex_at_birth == "unknown"
    assert profile.height_cm is None
    assert profile.medications == []
    assert profile.confirmed_conditions == []
    assert profile.care_plan.conditions == []


def test_identity_public_config_exposes_only_web_project_identifiers() -> None:
    verifier = IdentityVerifier(
        Settings(
            auth_mode="identity_platform",
            firebase_api_key="public-web-key",
            firebase_auth_domain="healthia.example.firebaseapp.com",
            firebase_project_id="healthia-example",
            firebase_app_id="1:123:web:abc",
        )
    )
    payload = verifier.public_config()
    assert payload["enabled"] is True
    assert payload["ready"] is True
    assert set(payload["providers"]) == {"google.com", "password"}
    assert payload["firebase"]["apiKey"] == "public-web-key"
    assert "GEMINI" not in str(payload).upper()


async def test_memory_state_is_strictly_isolated_by_verified_uid() -> None:
    service = HealthIAService(Settings(store_backend="memory", auth_mode="identity_platform"))
    first = AuthPrincipal(uid="uid-alpha", email="alpha@example.com", display_name="Alpha", provider="password")
    second = AuthPrincipal(uid="uid-beta", email="beta@example.com", display_name="Beta", provider="google.com")

    with patient_scope(first.uid):
        state = await service.ensure_identity(first)
        assert state.profile.id == first.uid
        assert state.profile.confirmed_conditions == []
        await service.add_weight(WeightRecord(weight_kg=70.5))
        alpha = await service.snapshot()
        assert len(alpha.weights) == 1

    with patient_scope(second.uid):
        state = await service.ensure_identity(second)
        assert state.profile.id == second.uid
        beta = await service.snapshot()
        assert beta.weights == []
        await service.add_weight(WeightRecord(weight_kg=82.0))
        beta = await service.snapshot()
        assert [item.weight_kg for item in beta.weights] == [82.0]

    with patient_scope(first.uid):
        alpha = await service.snapshot()
        assert [item.weight_kg for item in alpha.weights] == [70.5]
        assert all(item.patient_id == first.uid for item in alpha.weights)
        assert all(item.patient_id == first.uid for item in alpha.audit_events)


async def test_event_broker_does_not_cross_patient_scopes() -> None:
    service = HealthIAService(Settings(store_backend="memory"))
    with patient_scope("alpha"):
        alpha_stream = service.broker.subscribe()
        alpha_task = asyncio.create_task(alpha_stream.__anext__())
    await asyncio.sleep(0)
    with patient_scope("beta"):
        await service.broker.publish({"type": "state", "section": "beta"})
    assert not alpha_task.done()
    with patient_scope("alpha"):
        await service.broker.publish({"type": "state", "section": "alpha"})
    payload = await asyncio.wait_for(alpha_task, timeout=1)
    assert payload["section"] == "alpha"
    await alpha_stream.aclose()


def test_document_storage_and_device_pairing_are_bound_to_patient_uid() -> None:
    with patient_scope("uid-alpha"):
        document = build_document(filename="resultado.txt", content_type="text/plain", size_bytes=12)
    assert document.patient_id == "uid-alpha"
    assert document.storage_path.startswith("uploads/uid-alpha/")

    manager = DevicePairingManager()
    pairing = manager.create("uid-alpha")
    claim = manager.claim(pairing["code"], "phone-1", "Pixel")
    assert manager.resolve_patient(claim["access_token"], "phone-1") == "uid-alpha"
    assert manager.resolve_patient(claim["access_token"], "phone-2") is None


def test_http_api_isolates_two_verified_users_and_rejects_missing_identity(monkeypatch) -> None:
    principals = {
        "token-alpha": AuthPrincipal(uid="http-alpha", email="alpha@example.com", display_name="Alpha", provider="password"),
        "token-beta": AuthPrincipal(uid="http-beta", email="beta@example.com", display_name="Beta", provider="google.com"),
    }

    async def fake_verify(authorization: str | None) -> AuthPrincipal:
        token = str(authorization or "").removeprefix("Bearer ")
        if token not in principals:
            raise IdentityError("Authentication required")
        return principals[token]

    monkeypatch.setattr(settings, "auth_mode", "identity_platform")
    monkeypatch.setattr(identity_verifier, "verify_bearer", fake_verify)

    with TestClient(app) as client:
        assert client.get("/api/bootstrap").status_code == 401

        alpha_headers = {"Authorization": "Bearer token-alpha"}
        beta_headers = {"Authorization": "Bearer token-beta"}
        assert client.post("/api/weight", headers=alpha_headers, json={"weight_kg": 71.2}).status_code == 200
        assert client.post("/api/weight", headers=beta_headers, json={"weight_kg": 84.3}).status_code == 200

        alpha = client.get("/api/bootstrap", headers=alpha_headers).json()
        beta = client.get("/api/bootstrap", headers=beta_headers).json()
        assert alpha["profile"]["id"] == "http-alpha"
        assert beta["profile"]["id"] == "http-beta"
        assert [item["weight_kg"] for item in alpha["weights"]] == [71.2]
        assert [item["weight_kg"] for item in beta["weights"]] == [84.3]
        assert alpha["profile"]["confirmed_conditions"] == []
        assert beta["profile"]["confirmed_conditions"] == []


def test_internal_pubsub_endpoint_requires_trusted_oidc_identity(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_mode", "local")
    monkeypatch.setattr(settings, "pubsub_push_service_account", "healthia-push@example.iam.gserviceaccount.com")
    with TestClient(app) as client:
        response = client.post("/api/internal/pubsub/mission", json={"message": {"data": "e30="}})
        assert response.status_code == 401
