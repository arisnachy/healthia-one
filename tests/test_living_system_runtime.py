from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app, service, settings
from healthia_one.auth import patient_scope
from healthia_one.config import Settings
from healthia_one.living_system import (
    EVALUATION_PATIENT_ID,
    arm_evaluation,
    complete_living_scenario,
    living_system_snapshot,
    run_living_scenario,
)
from healthia_one.models import PatientState, utc_now
from healthia_one.service import HealthIAService, seed_state
from healthia_one.store import JsonStore, MemoryStore
from healthia_one.twin import LIVING_TWIN_EVENT_SEQUENCE


def test_living_system_runs_to_human_boundary_then_verifies_receipt() -> None:
    state = seed_state()
    initial_version = state.twin_version
    session = arm_evaluation(state, max_runs=2)

    waiting = run_living_scenario(state, session.id)

    assert waiting["session"]["status"] == "waiting_human"
    assert waiting["event_types"] == list(LIVING_TWIN_EVENT_SEQUENCE[:10])
    assert waiting["model_calls"] == 0
    assert state.twin_version == initial_version + 1
    assert len(state.device_observations) >= 4
    fixtures = [item for item in state.device_observations if item.metadata.get("evaluation_session_id") == session.id]
    assert {item.metric.value for item in fixtures} == {"blood_pressure", "weight", "heart_rate", "steps"}
    assert all(item.source_package == "healthia.synthetic.evaluation" for item in fixtures)
    assert state.anatomy_states
    assert state.medication_expectations
    assert state.organ_system_states
    assert state.obligations[0].status == "waiting"
    assert state.clinical_event_edges[0].causal_claim is False

    completed = complete_living_scenario(
        state,
        session.id,
        systolic=132,
        diastolic=82,
        pulse=70,
    )

    assert completed["session"]["status"] == "completed"
    assert completed["event_types"] == list(LIVING_TWIN_EVENT_SEQUENCE)
    assert len(completed["events"]) == 14
    assert state.twin_version == initial_version + 2
    assert completed["mission"]["status"] == "completed"
    assert completed["mission"]["closure_evidence"] == [f"vital_receipt_{session.id}"]
    receipt = next(item for item in state.vitals if item.id == f"vital_receipt_{session.id}")
    assert receipt.source.verified is False
    assert state.obligations[0].status == "completed"
    assert "chain_of_thought" not in str(completed).lower()


def test_living_scenario_is_idempotent_while_waiting() -> None:
    state = seed_state()
    session = arm_evaluation(state, max_runs=2)
    first = run_living_scenario(state, session.id)
    second = run_living_scenario(state, session.id)

    assert first["event_types"] == second["event_types"]
    assert len(state.living_twin_events) == 10
    assert len([item for item in state.missions if item.id == session.mission_id]) == 1
    assert len([item for item in state.device_observations if item.metadata.get("evaluation_session_id") == session.id]) == 4


def test_rearming_cannot_reset_an_active_durable_budget() -> None:
    state = seed_state()
    session = arm_evaluation(state, max_runs=2)
    run_living_scenario(state, session.id)

    rearmed = arm_evaluation(state, max_runs=5)

    assert rearmed.id == session.id
    assert rearmed.runs_used == 1
    assert rearmed.max_runs == 2
    assert rearmed.status == "waiting_human"


def test_new_release_cannot_reuse_prior_release_evidence() -> None:
    state = seed_state()
    old = arm_evaluation(state, release_sha="old-sha", runtime_revision="revision-old")
    run_living_scenario(state, old.id)
    complete_living_scenario(state, old.id, systolic=132, diastolic=82, pulse=70)
    old_receipt = f"vital_receipt_{old.id}"
    assert any(item.id == old_receipt for item in state.vitals)

    current = arm_evaluation(state, release_sha="new-sha", runtime_revision="revision-new")

    assert current.id != old.id
    assert current.release_sha == "new-sha"
    assert current.runtime_revision == "revision-new"
    assert current.status == "armed"
    assert current.runs_used == 0
    assert state.twin_version == 1
    assert state.twin_source_event_ids == []
    assert not any(item.id == old_receipt for item in state.vitals)
    assert not any(item.id == old.mission_id for item in state.missions)
    assert state.living_twin_events == []


def test_global_release_budget_survives_expired_sessions() -> None:
    state = seed_state()
    start = utc_now()
    first = arm_evaluation(state, now=start, session_minutes=1, max_sessions=2, max_runs=2)
    second = arm_evaluation(
        state,
        now=start + timedelta(minutes=2),
        session_minutes=1,
        max_sessions=2,
        max_runs=2,
    )

    assert first.id != second.id
    assert state.evaluation_budget.sessions_created == 2
    with pytest.raises(PermissionError, match="session budget exhausted"):
        arm_evaluation(state, now=start + timedelta(minutes=4), max_sessions=2, max_runs=2)
    assert state.evaluation_budget.sessions_created == 2


@pytest.mark.asyncio
async def test_service_evaluator_cannot_read_shared_demo_patient_data() -> None:
    demo = seed_state()
    demo.profile.confirmed_conditions = ["Sensitive condition"]
    demo.vitals[-1].source.source_id = "sensitive-demo-source"
    candidate = HealthIAService(Settings(store_backend="memory", evaluation_enabled=True, evaluation_access_key="key"))
    candidate.store = MemoryStore(demo, autonomous_enabled=False)

    snapshot = await candidate.arm_living_evaluation()

    assert snapshot["twin"]["patient_namespace"] == EVALUATION_PATIENT_ID
    assert "Sensitive condition" not in snapshot["twin"]["conditions"]
    assert "sensitive-demo-source" not in str(snapshot)
    with patient_scope("patient_demo"):
        original = await candidate.store.load()
    assert original.profile.confirmed_conditions == ["Sensitive condition"]


def test_evaluation_rejects_real_patient_and_expired_lease() -> None:
    real_state = PatientState()
    real_state.profile.id = "patient_real_123"
    with pytest.raises(PermissionError, match="synthetic"):
        arm_evaluation(real_state)

    state = seed_state()
    now = utc_now()
    session = arm_evaluation(state, now=now, session_minutes=1)
    with pytest.raises(PermissionError, match="expired"):
        run_living_scenario(state, session.id, now=now + timedelta(minutes=2))
    assert state.evaluation_session.status == "expired"


@pytest.mark.asyncio
async def test_json_restart_preserves_evaluation_lease_and_replay(tmp_path) -> None:
    store = JsonStore(tmp_path / "state.json", autonomous_enabled=False)
    state = seed_state()
    session = arm_evaluation(state)
    run_living_scenario(state, session.id)
    await store.save(state)

    restarted = JsonStore(tmp_path / "state.json", autonomous_enabled=False)
    loaded = await restarted.load()
    replay = living_system_snapshot(loaded)

    assert replay["session"]["id"] == session.id
    assert replay["session"]["runs_used"] == 1
    assert replay["event_types"] == list(LIVING_TWIN_EVENT_SEQUENCE[:10])
    assert replay["mission"]["status"] == "waiting_patient"


def test_evaluation_api_is_fail_closed_and_capability_protected(monkeypatch) -> None:
    prior_store = service.store
    service.store = MemoryStore(seed_state(), autonomous_enabled=False)
    monkeypatch.setattr(settings, "evaluation_access_key", "judge-secret")
    try:
        with TestClient(app) as client:
            monkeypatch.setattr(settings, "evaluation_enabled", False)
            assert client.post("/api/evaluation/arm", headers={"X-HealthIA-Evaluation-Key": "judge-secret"}).status_code == 404
            assert client.get("/living").status_code == 404

            monkeypatch.setattr(settings, "evaluation_enabled", True)
            assert client.get("/living").status_code == 200
            assert client.post("/api/evaluation/arm").status_code == 403
            assert client.post("/api/evaluation/arm", headers={"X-HealthIA-Evaluation-Key": "wrong"}).status_code == 403

            armed = client.post(
                "/api/evaluation/arm",
                headers={"X-HealthIA-Evaluation-Key": "judge-secret"},
            )
            assert armed.status_code == 200
            assert armed.json()["twin"]["patient_namespace"] == EVALUATION_PATIENT_ID
            session_id = armed.json()["session"]["id"]
            run = client.post(
                "/api/evaluation/run",
                json={"session_id": session_id},
                headers={"X-HealthIA-Evaluation-Key": "judge-secret"},
            )
            assert run.status_code == 200
            assert run.json()["session"]["status"] == "waiting_human"
            complete = client.post(
                "/api/evaluation/complete",
                json={"session_id": session_id, "systolic": 132, "diastolic": 82, "pulse": 70},
                headers={"X-HealthIA-Evaluation-Key": "judge-secret"},
            )
            assert complete.status_code == 200
            assert complete.json()["event_types"] == list(LIVING_TWIN_EVENT_SEQUENCE)
    finally:
        service.store = prior_store
