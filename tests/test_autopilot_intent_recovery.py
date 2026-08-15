from __future__ import annotations

from healthia_one.autopilot_event_intents import pending_event_intents, stage_event_intent
from healthia_one.autopilot_intent_recovery import plan_intent_recovery
from healthia_one.models import PatientState


def _state_with_intent() -> tuple[PatientState, str]:
    state = PatientState()
    event = stage_event_intent(
        state,
        "patient_state_changed",
        dedupe_key="guardian|recover|1",
        payload={"source": "guardian_context", "mission_id": "mission_1"},
    )
    return state, event.id


def test_recovery_creates_missing_outbox_record_and_marks_intent_emitted() -> None:
    state, event_id = _state_with_intent()

    records, report = plan_intent_recovery(state, existing_event_ids=set())

    assert [record.id for record in records] == [event_id]
    assert report["created_event_ids"] == [event_id]
    assert report["already_present_event_ids"] == []
    assert pending_event_intents(state) == []


def test_recovery_does_not_duplicate_outbox_record_if_stable_event_already_exists() -> None:
    state, event_id = _state_with_intent()

    records, report = plan_intent_recovery(state, existing_event_ids={event_id})

    assert records == []
    assert report["created_event_ids"] == []
    assert report["already_present_event_ids"] == [event_id]
    assert pending_event_intents(state) == []


def test_recovery_rejects_cross_patient_event_intent() -> None:
    import pytest

    state, _ = _state_with_intent()
    intent = state.audit_events[-1]
    intent.details["event"]["patient_id"] = "patient_other"

    with pytest.raises(PermissionError):
        plan_intent_recovery(state)
