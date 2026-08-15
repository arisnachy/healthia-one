from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from healthia_one.autopilot_events import EventOutboxStore, stable_event_id
from healthia_one.autopilot_runtime import AutopilotEvent
from healthia_one.control import audit
from healthia_one.models import AuditEvent, PatientState


INTENT_ACTION = "autopilot_event_intent"
INTENT_RESOURCE_TYPE = "autopilot_event"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stage_event_intent(
    state: PatientState,
    event_type: str,
    *,
    dedupe_key: str,
    subject_id: str = "",
    condition: str = "",
    program_id: str = "",
    payload: dict[str, Any] | None = None,
) -> AutopilotEvent:
    """Persist an event *intent* inside PatientState before external outbox work.

    The caller must save PatientState before flushing. This ordering guarantees a
    Firestore/Eventarc worker can never observe the event before the mission and
    clinical/device context that caused it are durable.
    """
    event_id = stable_event_id(state.profile.id, event_type, dedupe_key)
    existing = next(
        (
            item
            for item in state.audit_events
            if item.action == INTENT_ACTION and item.resource_id == event_id
        ),
        None,
    )
    event = AutopilotEvent(
        id=event_id,
        patient_id=state.profile.id,
        event_type=event_type,
        subject_id=subject_id,
        condition=condition,
        program_id=program_id,
        payload=payload or {},
    )
    if existing is not None:
        return event

    audit(
        state,
        actor="system",
        action=INTENT_ACTION,
        resource_type=INTENT_RESOURCE_TYPE,
        resource_id=event_id,
        details={
            "status": "pending",
            "event": event.model_dump(mode="json"),
            "dedupe_key": dedupe_key,
            "attempts": 0,
            "last_error": "",
            "staged_at": utc_now_iso(),
        },
    )
    return event


def pending_event_intents(state: PatientState) -> list[AuditEvent]:
    return [
        item
        for item in state.audit_events
        if item.action == INTENT_ACTION
        and item.resource_type == INTENT_RESOURCE_TYPE
        and str(item.details.get("status") or "pending") != "emitted"
    ]


def flush_event_intents(state: PatientState, outbox_store: EventOutboxStore) -> dict[str, Any]:
    """Flush already-persisted intents to the durable outbox idempotently.

    `EventOutboxStore.put()` is stable by event ID. If the process crashes after
    outbox persistence but before PatientState is saved with `status=emitted`, a
    retry reuses the same event ID and cannot create a second Eventarc unit of work.
    """
    emitted: list[str] = []
    failed: list[str] = []
    for intent in pending_event_intents(state):
        raw_event = intent.details.get("event") or {}
        try:
            event = AutopilotEvent.model_validate(raw_event)
            if event.patient_id != state.profile.id:
                raise PermissionError("Autopilot event intent patient does not match PatientState")
            outbox_store.put(event)
            intent.details["status"] = "emitted"
            intent.details["emitted_at"] = utc_now_iso()
            intent.details["last_error"] = ""
            intent.details["attempts"] = int(intent.details.get("attempts") or 0) + 1
            emitted.append(event.id)
        except Exception as exc:
            intent.details["status"] = "pending"
            intent.details["last_error"] = f"{type(exc).__name__}: {exc}"[:500]
            intent.details["attempts"] = int(intent.details.get("attempts") or 0) + 1
            failed.append(intent.resource_id)
    return {
        "emitted_event_ids": emitted,
        "failed_event_ids": failed,
        "pending_after": len(pending_event_intents(state)),
        "state_changed": bool(emitted or failed),
    }
