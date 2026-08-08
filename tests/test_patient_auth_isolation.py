from __future__ import annotations

import asyncio

import pytest

from healthia_one.auth import AccountManager, AuthError, patient_scope, principal_scope
from healthia_one.config import Settings
from healthia_one.models import PatientState, WeightRecord
from healthia_one.service import EventBroker
from healthia_one.store import JsonStore


def auth_settings(tmp_path) -> Settings:
    return Settings(
        env="local",
        store_backend="json",
        data_path=tmp_path / "state.json",
        accounts_path=tmp_path / "accounts.json",
        auth_required=True,
        allow_registration=True,
    )


def test_account_password_session_and_tamper_rejection(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    manager = AccountManager(auth_settings(tmp_path))
    principal = manager.register("a@example.test", "VerySafePassword!42", "Paciente A")

    assert manager.authenticate("A@example.test", "VerySafePassword!42") == principal
    with pytest.raises(AuthError):
        manager.authenticate("a@example.test", "wrong-password")

    token = manager.issue_session(principal)
    assert manager.verify_session(token) == principal
    version, body, signature = token.split(".", 2)
    tampered = f"{version}.{body[:-1]}A.{signature}"
    assert manager.verify_session(tampered) is None

    accounts_text = (tmp_path / "accounts.json").read_text("utf-8")
    assert "VerySafePassword!42" not in accounts_text
    assert "scrypt$" in accounts_text


@pytest.mark.asyncio
async def test_json_store_keeps_two_patient_namespaces_separate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = auth_settings(tmp_path)
    manager = AccountManager(settings)
    patient_a = manager.register("a@example.test", "VerySafePassword!42", "Paciente A")
    patient_b = manager.register("b@example.test", "VerySafePassword!43", "Paciente B")
    store = JsonStore(settings.data_path)

    with principal_scope(patient_a):
        state_a = PatientState()
        state_a.profile.display_name = "Paciente A"
        state_a.weights = [WeightRecord(weight_kg=81.2, note="A only")]
        await store.save(state_a)

    with principal_scope(patient_b):
        state_b = PatientState()
        state_b.profile.display_name = "Paciente B"
        state_b.weights = [WeightRecord(weight_kg=63.4, note="B only")]
        await store.save(state_b)

    with principal_scope(patient_a):
        loaded_a = await store.load()
    with principal_scope(patient_b):
        loaded_b = await store.load()

    assert loaded_a.profile.id == patient_a.patient_id
    assert loaded_b.profile.id == patient_b.patient_id
    assert loaded_a.weights[0].weight_kg == 81.2
    assert loaded_b.weights[0].weight_kg == 63.4
    assert loaded_a.weights[0].note == "A only"
    assert loaded_b.weights[0].note == "B only"


@pytest.mark.asyncio
async def test_event_broker_does_not_cross_patient_boundary() -> None:
    broker = EventBroker()

    async def receive(patient_id: str):
        with patient_scope(patient_id):
            stream = broker.subscribe()
            return await anext(stream)

    task_a = asyncio.create_task(receive("patient_a"))
    task_b = asyncio.create_task(receive("patient_b"))
    await asyncio.sleep(0)

    with patient_scope("patient_a"):
        await broker.publish({"type": "message", "message": {"content": "A only"}})

    payload_a = await asyncio.wait_for(task_a, timeout=1)
    assert payload_a["message"]["content"] == "A only"
    await asyncio.sleep(0.02)
    assert not task_b.done()

    with patient_scope("patient_b"):
        await broker.publish({"type": "message", "message": {"content": "B only"}})
    payload_b = await asyncio.wait_for(task_b, timeout=1)
    assert payload_b["message"]["content"] == "B only"


def test_local_launcher_enables_auth_and_nonrobotic_ai_budget() -> None:
    script = (__import__("pathlib").Path(__file__).resolve().parents[1] / "deployment" / "run-local-secure.ps1").read_text("utf-8")
    assert '$env:HEALTHIA_AUTH_REQUIRED = "true"' in script
    assert '$env:HEALTHIA_PROACTIVE_ENABLED = "false"' in script
    assert "[int]$MaxOutputTokens = 1400" in script
    assert "HEALTHIA_SESSION_SECRET" in script
    assert "HEALTHIA_DEVICE_TOKEN_SECRET" in script


def test_browser_loads_progressive_dynamic_questions_and_real_account_controls() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    index = (root / "web" / "index.html").read_text("utf-8")
    clinical = (root / "web" / "clinical-council.js").read_text("utf-8")
    account = (root / "web" / "account.js").read_text("utf-8")

    assert '/assets/clinical-council.js' in index
    assert '/assets/account.js' in index
    assert "Preguntas creadas para este caso" in clinical
    assert "Gemini + ADK" not in clinical
    assert "Continuar con las 3 restantes" in clinical
    assert "No pude completar las próximas preguntas personalizadas" in clinical
    assert "/api/auth/logout" in account
    assert "event.stopImmediatePropagation()" in account
