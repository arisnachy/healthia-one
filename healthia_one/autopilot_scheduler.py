from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Literal

from healthia_one.autopilot_events import EventOutboxStore, stable_event_id
from healthia_one.autopilot_runtime import AutopilotEvent
from healthia_one.models import PatientState
from healthia_one.opportunity_autopilot import derive_watch_topics
from healthia_one.opportunity_permissions import RadarPermissionStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def period_key(mode: Literal["scientific", "resources"], now: datetime | None = None) -> str:
    now = now or utc_now()
    if mode == "scientific":
        iso_year, iso_week, _ = now.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return now.strftime("%Y-%m")


def enqueue_scheduled_refreshes(
    states: Iterable[PatientState],
    *,
    permission_store: RadarPermissionStore,
    outbox_store: EventOutboxStore,
    mode: Literal["scientific", "resources"],
    now: datetime | None = None,
) -> list[AutopilotEvent]:
    bucket = period_key(mode, now)
    created: list[AutopilotEvent] = []

    for state in states:
        permissions = permission_store.load(state.profile.id)
        allowed = permissions.scientific_enabled if mode == "scientific" else permissions.resource_enabled
        if not allowed:
            continue
        if not derive_watch_topics(state):
            continue

        event_id = stable_event_id(
            state.profile.id,
            "scheduled.discovery_refresh",
            f"{mode}|{bucket}",
        )
        if outbox_store.get(event_id) is not None:
            # The same patient/mode/period is one durable event. Re-running the
            # scheduler is therefore free of duplicate Eventarc work.
            continue
        event = AutopilotEvent(
            id=event_id,
            patient_id=state.profile.id,
            event_type="scheduled.discovery_refresh",
            payload={
                "schedule_mode": mode,
                "period_key": bucket,
                "scientific_scan": mode == "scientific",
                "resource_scan": mode == "resources",
                # Address is an explicit patient-entered search hint. It is not
                # converted into a legal residence assertion.
                "country": "",
                "region": "",
                "locality": str(state.profile.address or "")[:220],
            },
        )
        outbox_store.put(event)
        created.append(event)
    return created


def load_firestore_patient_states(project: str | None = None) -> list[PatientState]:
    from google.cloud import firestore

    client = firestore.Client(project=project)
    states: list[PatientState] = []
    for snapshot in client.collection("healthia_patient_states").stream():
        raw = snapshot.to_dict() or {}
        if not raw:
            continue
        try:
            states.append(PatientState.model_validate(raw))
        except Exception:
            # One malformed patient record must not cause the scheduler to
            # fabricate or partially repair clinical state.
            continue
    return states
