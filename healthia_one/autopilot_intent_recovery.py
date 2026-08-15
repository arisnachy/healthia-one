from __future__ import annotations

import os
from typing import Any

from healthia_one.autopilot_event_intents import pending_event_intents
from healthia_one.autopilot_events import FirestoreEventOutboxStore, OutboxRecord
from healthia_one.autopilot_runtime import AutopilotEvent
from healthia_one.models import PatientState
from healthia_one.store import PATIENT_STATE_COLLECTION


def plan_intent_recovery(
    state: PatientState,
    *,
    existing_event_ids: set[str] | None = None,
) -> tuple[list[OutboxRecord], dict[str, Any]]:
    """Build a deterministic recovery plan and mark intents emitted in memory.

    This pure planner is used inside one Firestore transaction. Existing outbox
    documents are treated as already emitted; missing ones are created with the
    exact stable event ID stored in the patient intent.
    """
    existing = set(existing_event_ids or set())
    create_records: list[OutboxRecord] = []
    recovered_existing: list[str] = []
    emitted: list[str] = []

    for intent in pending_event_intents(state):
        event = AutopilotEvent.model_validate(intent.details.get("event") or {})
        if event.patient_id != state.profile.id:
            raise PermissionError("Recovery intent patient does not match canonical patient state")
        if event.id in existing:
            recovered_existing.append(event.id)
        else:
            create_records.append(OutboxRecord(id=event.id, patient_id=event.patient_id, event=event))
        intent.details["status"] = "emitted"
        intent.details["recovered_by"] = "firestore_intent_recovery"
        intent.details["last_error"] = ""
        intent.details["attempts"] = int(intent.details.get("attempts") or 0) + 1
        emitted.append(event.id)

    return create_records, {
        "emitted_event_ids": emitted,
        "created_event_ids": [item.id for item in create_records],
        "already_present_event_ids": recovered_existing,
    }


def recover_firestore_event_intents(
    project: str | None = None,
    *,
    limit: int = 250,
) -> dict[str, Any]:
    """Recover post-commit intents that were not flushed before process loss.

    For each patient with pending intents, this performs a Firestore transaction:
    read canonical PatientState and relevant outbox docs first, then create any
    missing outbox records and persist `status=emitted` back into the same patient
    document. No Gemini/model/network discovery work occurs in this producer.
    """
    from google.cloud import firestore

    project_id = project or os.getenv("GOOGLE_CLOUD_PROJECT") or None
    client = firestore.Client(project=project_id)
    scanned = 0
    patients_recovered = 0
    events_created = 0
    events_already_present = 0
    failures: list[dict[str, str]] = []

    snapshots = client.collection(PATIENT_STATE_COLLECTION).limit(max(1, min(limit, 1000))).stream()
    for snapshot in snapshots:
        scanned += 1
        patient_ref = client.collection(PATIENT_STATE_COLLECTION).document(snapshot.id)
        transaction = client.transaction()

        @firestore.transactional
        def recover_one(txn):
            fresh = patient_ref.get(transaction=txn)
            if not fresh.exists:
                return {"changed": False, "created": 0, "existing": 0}
            state = PatientState.model_validate(fresh.to_dict() or {})
            if state.profile.id != snapshot.id:
                raise PermissionError("Firestore document ID does not match PatientState profile ID")
            pending = pending_event_intents(state)
            if not pending:
                return {"changed": False, "created": 0, "existing": 0}

            event_refs = {}
            existing_ids: set[str] = set()
            # All reads happen before writes, as required by Firestore transactions.
            for intent in pending:
                event = AutopilotEvent.model_validate(intent.details.get("event") or {})
                event_ref = client.collection(FirestoreEventOutboxStore.COLLECTION).document(event.id)
                event_refs[event.id] = event_ref
                if event_ref.get(transaction=txn).exists:
                    existing_ids.add(event.id)

            records, report = plan_intent_recovery(state, existing_event_ids=existing_ids)
            for record in records:
                txn.create(event_refs[record.id], record.model_dump(mode="json"))
            txn.set(patient_ref, state.model_dump(mode="json"))
            return {
                "changed": True,
                "created": len(report["created_event_ids"]),
                "existing": len(report["already_present_event_ids"]),
            }

        try:
            result = recover_one(transaction)
            if result.get("changed"):
                patients_recovered += 1
                events_created += int(result.get("created") or 0)
                events_already_present += int(result.get("existing") or 0)
        except Exception as exc:
            failures.append({"patient_id": snapshot.id, "error_type": type(exc).__name__})

    return {
        "status": "completed" if not failures else "completed_with_failures",
        "patient_states_scanned": scanned,
        "patients_recovered": patients_recovered,
        "events_created": events_created,
        "events_already_present": events_already_present,
        "failure_count": len(failures),
        "failures": failures[:20],
        "model_calls": 0,
    }
