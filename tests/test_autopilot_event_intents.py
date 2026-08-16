from __future__ import annotations

import inspect

import pytest

from healthia_one.autopilot_event_intents import flush_event_intents, pending_event_intents, stage_event_intent
from healthia_one.autopilot_events import MemoryEventOutboxStore
from healthia_one.autopilot_scheduler import load_firestore_patient_states
from healthia_one.models import PatientState
from healthia_one.store import MemoryStore, PATIENT_STATE_COLLECTION


def test_event_intent_is_durable_state_before_outbox_visibility() -> None:
    state = PatientState()
    outbox = MemoryEventOutboxStore()

    event = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key="guardian|device_1|pattern|mission_1",
        payload={"source": "guardian_context", "mission_id": "mission_1"},
    )

    assert len(pending_event_intents(state)) == 1
    assert outbox.get(event.id) is None

    report = flush_event_intents(state, outbox)

    assert report["emitted_event_ids"] == [event.id]
    assert outbox.get(event.id) is not None
    assert pending_event_intents(state) == []


def test_event_intent_redelivery_is_idempotent_by_stable_event_id() -> None:
    state = PatientState()
    outbox = MemoryEventOutboxStore()
    first = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key="guardian|same",
        payload={"source": "guardian_context"},
    )
    second = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key="guardian|same",
        payload={"source": "guardian_context"},
    )

    assert first.id == second.id
    assert len([item for item in state.audit_events if item.resource_id == first.id]) == 1
    flush_event_intents(state, outbox)
    assert outbox.get(first.id) is not None
    assert flush_event_intents(state, outbox)["emitted_event_ids"] == []


@pytest.mark.asyncio
async def test_memory_store_commits_pending_intent_before_post_commit_flush(monkeypatch) -> None:
    state = PatientState()
    stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key="guardian|ordering",
        payload={"source": "guardian_context"},
    )
    store = MemoryStore(PatientState())
    observed = {"committed_before_flush": False}

    async def fake_flush(current_state):
        persisted = store._states["patient_demo"]
        observed["committed_before_flush"] = bool(pending_event_intents(persisted))
        for item in pending_event_intents(current_state):
            item.details["status"] = "emitted"
        return True

    monkeypatch.setattr("healthia_one.store._flush_post_commit_intents", fake_flush)
    await store.save(state)

    assert observed["committed_before_flush"] is True
    assert pending_event_intents(store._states["patient_demo"]) == []


def test_autonomous_scheduler_reads_the_same_canonical_collection_as_patient_store() -> None:
    assert PATIENT_STATE_COLLECTION == "healthia_one_patients"
    source = inspect.getsource(load_firestore_patient_states)
    assert "PATIENT_STATE_COLLECTION" in source
    assert "healthia_patient_states" not in source
