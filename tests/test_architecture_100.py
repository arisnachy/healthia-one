from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from threading import Lock

import pytest

from healthia_one.config import Settings
from healthia_one.distributed_events import FirestoreEventBroker
from healthia_one.fcm_registration import FirestoreFCMRegistrationStore, build_fcm_registration_store
from healthia_one.google_constellation_runtime import _stores as build_google_stores
from healthia_one.models import PatientState
from healthia_one.pairing import DevicePairingManager, PairingError, PairingSession, utc_now
from healthia_one.pairing_backends import FirestorePairingBackend
from healthia_one.runtime_architecture import build_pairing_manager, build_service, runtime_readiness
from healthia_one.store import FirestoreStore


class SharedDurablePairingBackend:
    """Small deterministic backend used to model two independent instances."""

    persistence = "test_durable_shared"

    def __init__(self) -> None:
        self.values: dict[str, PairingSession] = {}
        self.lock = Lock()

    def create(self, session: PairingSession) -> bool:
        with self.lock:
            if session.code in self.values:
                return False
            self.values[session.code] = replace(session)
            return True

    def get(self, code: str) -> PairingSession | None:
        with self.lock:
            value = self.values.get(code)
            if value is None or value.expires_at <= utc_now():
                self.values.pop(code, None)
                return None
            return replace(value)

    def delete(self, code: str) -> None:
        with self.lock:
            self.values.pop(code, None)

    def claim(self, code: str, device_id: str, display_name: str) -> PairingSession:
        with self.lock:
            session = self.values.get(code)
            if session is None or session.expires_at <= utc_now():
                raise PairingError("El código no existe o expiró.")
            if session.claimed:
                if session.device_id != device_id:
                    raise PairingError("El código ya fue utilizado por otro dispositivo.")
                return replace(session)
            session.claimed = True
            session.device_id = device_id
            session.display_name = display_name
            self.values[code] = session
            return replace(session)

    def wait_for_claim(self, code: str, _timeout_seconds: float) -> PairingSession | None:
        return self.get(code)


def _clear_cloud_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "HEALTHIA_GCS_BUCKET",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(name, raising=False)


def _cloud_test_settings(monkeypatch: pytest.MonkeyPatch, *, store_backend: str = "memory") -> Settings:
    _clear_cloud_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "healthia-architecture-test")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("HEALTHIA_DEVICE_TOKEN_SECRET", "d" * 64)
    return Settings(env="cloud", store_backend=store_backend, llm_backend="mock")


def _is_firestore_client_call(node: ast.Call) -> bool:
    function = node.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr in {"Client", "AsyncClient"}
        and isinstance(function.value, ast.Name)
        and function.value.id == "firestore"
    )


def test_no_firestore_client_is_constructed_inside_any_init() -> None:
    violations: list[str] = []
    for path in sorted(Path("healthia_one").glob("*.py")):
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != "__init__":
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and _is_firestore_client_call(child):
                    violations.append(f"{path}:{child.lineno}")
    assert violations == [], f"Eager Firestore clients in constructors: {violations}"


def test_cloud_runtime_construction_is_network_lazy_and_multi_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cloud_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "healthia-architecture-test")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("HEALTHIA_DEVICE_TOKEN_SECRET", "d" * 64)

    settings = Settings(env="cloud", store_backend="firestore", llm_backend="gemini_api")
    service = build_service(settings)
    pairing = build_pairing_manager(settings)
    fcm = build_fcm_registration_store(settings)
    google_stores = build_google_stores(settings)

    assert isinstance(service.store, FirestoreStore)
    assert service.store.client_initialized is False
    assert isinstance(service.broker, FirestoreEventBroker)
    assert service.broker.client_initialized is False
    assert isinstance(pairing.backend, FirestorePairingBackend)
    assert pairing.backend.client_initialized is False
    assert pairing.session_persistence == "firestore_transactional"
    assert pairing.credential_persistence == "restart_safe"
    assert isinstance(fcm, FirestoreFCMRegistrationStore)
    assert fcm.client_initialized is False
    assert len(google_stores) == 6
    assert all(getattr(store, "client_initialized", False) is False for store in google_stores)


@pytest.mark.asyncio
async def test_local_readiness_is_live_bounded_and_zero_ai_spend(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cloud_env(monkeypatch)
    settings = Settings(env="local", store_backend="memory", llm_backend="mock")
    service = build_service(settings)
    await service.initialize()
    pairing = build_pairing_manager(settings)
    fcm = build_fcm_registration_store(settings)

    payload = await runtime_readiness(service, settings, pairing, fcm, timeout_seconds=0.5, force=True)

    assert payload["ready"] is True
    assert payload["startup"] == {"ready": True, "mode": "startup_complete"}
    assert payload["store"] == {"ready": True, "mode": "live_read"}
    assert payload["evidence"]["ready"] is True
    assert payload["ai_probe_performed"] is False
    assert payload["ai_spend"] == "zero"


@pytest.mark.asyncio
async def test_cloud_liveness_survives_dependency_startup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _cloud_test_settings(monkeypatch)
    service = build_service(settings)

    class FailingStore:
        async def load(self):
            raise RuntimeError("simulated dependency loss")

        async def save(self, _state):
            raise RuntimeError("simulated dependency loss")

    service.store = FailingStore()
    await service.initialize()
    assert service.startup_error == "RuntimeError"

    pairing = build_pairing_manager(settings)
    fcm = build_fcm_registration_store(settings)
    payload = await runtime_readiness(service, settings, pairing, fcm, timeout_seconds=0.1, force=True)
    assert payload["ready"] is False
    assert payload["startup"]["ready"] is False
    assert payload["store"]["ready"] is False
    assert payload["store"]["error"] == "RuntimeError"


@pytest.mark.asyncio
async def test_readiness_retries_full_startup_before_recovering(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _cloud_test_settings(monkeypatch)
    service = build_service(settings)

    class RecoveringStore:
        def __init__(self) -> None:
            self.loads = 0

        async def load(self):
            self.loads += 1
            if self.loads == 1:
                raise RuntimeError("first boot dependency loss")
            return PatientState()

        async def save(self, _state):
            return None

    store = RecoveringStore()
    service.store = store
    await service.initialize()
    assert service.startup_error == "RuntimeError"

    pairing = build_pairing_manager(settings)
    fcm = build_fcm_registration_store(settings)
    payload = await runtime_readiness(service, settings, pairing, fcm, timeout_seconds=0.5, force=True)

    assert payload["ready"] is True
    assert payload["startup"] == {"ready": True, "mode": "startup_retry_recovered"}
    assert service.startup_error is None
    assert store.loads >= 3  # failed boot, recovery init, then independent live read


def test_pairing_survives_instance_replacement_and_rejects_double_claim() -> None:
    backend = SharedDurablePairingBackend()
    secret = "restart-safe-device-secret-" + ("x" * 40)
    instance_a = DevicePairingManager(backend=backend, token_secret=secret)
    instance_b = DevicePairingManager(backend=backend, token_secret=secret)
    replacement_instance = DevicePairingManager(backend=backend, token_secret=secret)

    session = instance_a.create(patient_id="patient_demo")
    assert instance_b.status(session["code"])["claimed"] is False

    claim = instance_b.claim(session["code"], "phone-100", "Phone 100")
    assert claim["session_persistence"] == "test_durable_shared"
    assert replacement_instance.validate(claim["access_token"], "phone-100") is True

    # Simulate a lost first HTTP response: the same phone can retry the exact
    # claim and receive a fresh signed bearer without reopening ownership.
    replay = replacement_instance.claim(session["code"], "phone-100", "Phone 100")
    assert instance_a.validate(replay["access_token"], "phone-100") is True

    with pytest.raises(PairingError, match="otro dispositivo"):
        instance_a.claim(session["code"], "phone-200", "Phone 200")


def test_firestore_pairing_backend_uses_atomic_claim_and_snapshot_wait() -> None:
    source = Path("healthia_one/pairing_backends.py").read_text("utf-8")
    assert "@firestore.transactional" in source
    assert "txn.set(ref" in source
    assert ".on_snapshot(on_snapshot)" in source
    assert "ttl_at" in source
    assert "same device may safely retry" in source


def test_production_entrypoint_uses_truthful_readiness_and_distributed_runtime() -> None:
    main = Path("app/main.py").read_text("utf-8")
    deploy = Path("deployment/deploy-cloud-demo.ps1").read_text("utf-8")

    assert "service = build_service(settings)" in main
    assert "pairing_manager = build_pairing_manager(settings)" in main
    assert "await runtime_readiness(" in main
    assert '"dependency_readiness": dependency_readiness' in main
    assert '"multi_instance_pairing"' in main
    assert '"distributed_event_fanout"' in main
    assert '"--max-instances", "3"' in deploy
    assert "max 1" not in deploy
