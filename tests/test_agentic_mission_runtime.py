import base64
import json
import os

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"
os.environ["HEALTHIA_COST_MODE"] = "local"
os.environ["HEALTHIA_AGENTIC_EVENTS_ENABLED"] = "false"

from fastapi.testclient import TestClient

from app.main import app
from healthia_one.event_dispatch import decode_pubsub_push
from healthia_one.mission_engine import (
    apply_mission_action,
    deterministic_decision,
    validate_adk_decision,
)
from healthia_one.models import AgenticEvent, MissionStatus, SourceRef, VitalRecord
from healthia_one.service import seed_state


def test_closed_loop_mission_opens_then_closes_with_verifiable_artifact() -> None:
    state = seed_state()
    first = VitalRecord(
        systolic=165,
        diastolic=102,
        source=SourceRef(source_type="synthetic_test", source_id="closed_loop"),
    )
    state.vitals.append(first)
    first_event = AgenticEvent(event_type="vital_recorded", source_id=first.id)
    first_decision = deterministic_decision(state, first_event)
    assert first_decision.action == "open_repeat_measurement"
    first_outcome = apply_mission_action(state, first_event, first_decision)
    assert first_outcome.status == MissionStatus.WAITING_PATIENT.value

    second = VitalRecord(
        systolic=138,
        diastolic=88,
        source=SourceRef(source_type="synthetic_test", source_id="closed_loop"),
    )
    state.vitals.append(second)
    second_event = AgenticEvent(event_type="vital_recorded", source_id=second.id)
    second_decision = deterministic_decision(state, second_event)
    assert second_decision.action == "close_repeat_measurement"
    second_outcome = apply_mission_action(state, second_event, second_decision)

    mission = next(item for item in state.missions if item.id == second_outcome.mission_id)
    assert mission.status == MissionStatus.COMPLETED
    assert second_outcome.artifact_ids
    artifact = next(item for item in state.mission_artifacts if item.id == second_outcome.artifact_ids[0])
    assert artifact.artifact_type == "measurement_followup_summary"
    assert len(artifact.payload["readings"]) >= 2
    assert artifact.id in mission.closure_evidence


def test_adk_candidate_cannot_downgrade_deterministic_safety() -> None:
    state = seed_state()
    vital = VitalRecord(systolic=185, diastolic=121, symptoms=["dolor de pecho"])
    state.vitals.append(vital)
    event = AgenticEvent(event_type="vital_recorded", source_id=vital.id)
    decision = validate_adk_decision(
        state,
        event,
        {"action": "no_action", "reason": "ignore"},
    )
    assert decision.action == "escalate_professional_review"
    assert decision.risk_level.value in {"priority", "urgent"}


def test_scheduled_tick_prepares_and_closes_consultation_packet() -> None:
    state = seed_state()
    event = AgenticEvent(event_type="scheduled_tick")
    decision = deterministic_decision(state, event)
    assert decision.action == "prepare_consultation_packet"
    outcome = apply_mission_action(state, event, decision)
    assert outcome.status == MissionStatus.COMPLETED.value
    assert outcome.artifact_ids
    artifact = next(item for item in state.mission_artifacts if item.id == outcome.artifact_ids[0])
    assert artifact.artifact_type == "consultation_packet"
    assert artifact.payload["requires_patient_review"] is True


def test_pubsub_push_decodes_typed_agentic_event() -> None:
    event = AgenticEvent(event_type="scheduled_tick", payload={"source": "scheduler"})
    encoded = base64.b64encode(event.model_dump_json().encode()).decode()
    decoded = decode_pubsub_push({"message": {"data": encoded}})
    assert decoded.id == event.id
    assert decoded.event_type == "scheduled_tick"


def test_zero_spend_api_demo_proves_trigger_action_persistence_and_closure() -> None:
    with TestClient(app) as client:
        response = client.post("/api/demo/agentic-closed-loop")
        assert response.status_code == 200
        payload = response.json()
        assert payload["synthetic"] is True
        assert payload["model_calls"] == 0
        assert payload["first_run"]["runtime"] == "deterministic_test"
        assert payload["second_run"]["runtime"] == "deterministic_test"
        trace = payload["final_trace"]
        assert trace["mission"]["status"] == "completed"
        assert trace["artifacts"]
        stages = {item["stage"] for item in trace["run"]["events"]}
        assert {"trigger", "tool", "persistence", "closure"}.issubset(stages)


def test_adk_runtime_source_uses_runner_tool_trace_and_hard_call_limit() -> None:
    source = open("healthia_one/adk_runtime.py", encoding="utf-8").read()
    agent = open("healthia_agent/agent.py", encoding="utf-8").read()
    assert "Runner(" in source
    assert "InMemorySessionService" in source
    assert "RunConfig(max_llm_calls=2)" in source
    assert "authorize_many" in source
    assert "commit_mission_action" in source
    assert "commit_mission_action" in agent
    assert "AGENTIC_EVENT" in agent
