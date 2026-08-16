from healthia_one.autopilot_events import MemoryEventOutboxStore, stable_event_id
from healthia_one.autopilot_receipts import MemoryAutopilotReceiptStore
from healthia_one.autopilot_runtime import AutopilotEvent, OpportunityAutopilot
from healthia_one.autopilot_worker import FIRESTORE_CREATED, event_id_from_cloudevent_headers, process_outbox_event
from healthia_one.opportunity_store import MemoryOpportunityStore
from healthia_one.service import seed_state


def test_stable_event_id_deduplicates_same_mutation_key():
    patient_id = "patient_demo"
    first = stable_event_id(patient_id, "family_history.changed", "member_1|autism")
    second = stable_event_id(patient_id, "family_history.changed", "member_1|autism")
    different = stable_event_id(patient_id, "family_history.changed", "member_2|autism")

    assert first == second
    assert first != different
    assert first.startswith("event_")


def test_worker_accepts_only_firestore_created_event_for_autopilot_collection():
    event_id = "event_abc123"
    headers = {
        "ce-type": FIRESTORE_CREATED,
        "ce-subject": f"documents/healthia_autopilot_events/{event_id}",
    }
    assert event_id_from_cloudevent_headers(headers) == event_id

    bad_type = dict(headers, **{"ce-type": "google.cloud.firestore.document.v1.updated"})
    try:
        event_id_from_cloudevent_headers(bad_type)
    except ValueError as exc:
        assert "Unsupported CloudEvent type" in str(exc)
    else:
        raise AssertionError("updated Firestore event must not be accepted")

    bad_path = dict(headers, **{"ce-subject": "documents/other_collection/event_abc123"})
    try:
        event_id_from_cloudevent_headers(bad_path)
    except ValueError as exc:
        assert "not a HealthIA autopilot outbox" in str(exc)
    else:
        raise AssertionError("unrelated Firestore document must not be accepted")


async def test_worker_reads_durable_event_and_marks_it_processed_once():
    state = seed_state()
    outbox = MemoryEventOutboxStore()
    receipts = MemoryAutopilotReceiptStore()
    engine = OpportunityAutopilot(
        MemoryOpportunityStore(),
        receipt_store=receipts,
    )
    event = AutopilotEvent(
        id="event_worker_once",
        patient_id=state.profile.id,
        event_type="patient_state_changed",
    )
    outbox.put(event)

    async def load_patient(patient_id):
        assert patient_id == state.profile.id
        return state

    first = await process_outbox_event(
        event.id,
        outbox_store=outbox,
        engine=engine,
        state_loader=load_patient,
    )
    second = await process_outbox_event(
        event.id,
        outbox_store=outbox,
        engine=engine,
        state_loader=load_patient,
    )

    assert first["status"] == "processed"
    assert outbox.get(event.id).status == "processed"
    assert len(receipts.list_recent(state.profile.id)) == 1
    assert second == {"event_id": event.id, "status": "duplicate_processed", "duplicate": True}
    assert len(receipts.list_recent(state.profile.id)) == 1
