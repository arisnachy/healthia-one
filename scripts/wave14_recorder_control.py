from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from healthia_one.auth import patient_scope
from healthia_one.autopilot_events import FirestoreEventOutboxStore
from healthia_one.bp_followup_guardian import CONSENT_SIGNAL as BP_CONSENT, MISSION_TYPE as BP_MISSION_TYPE
from healthia_one.config import Settings
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.guardian_email_reply import GUARDIAN_EMAIL_REPLY_CONSENT
from healthia_one.models import DEFAULT_SIGNAL_TYPES, MissionStatus, PatientState, VitalRecord
from healthia_one.service import HealthIAService
from healthia_one.store import PATIENT_STATE_COLLECTION

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "healthia-6088a").strip()
PATIENT_ID = os.environ.get("HEALTHIA_WAVE14_PROOF_PATIENT_ID", "").strip()
RUN_ID = os.environ.get("HEALTHIA_WAVE14_PROOF_RUN_ID", "").strip()
PROOF_COLLECTION = "healthia_wave14_stitch_proofs"
BACKUP_COLLECTION = "healthia_wave14_stitch_backups"
OUTBOX_COLLECTION = "healthia_autopilot_events"


def cfg() -> Settings:
    return Settings(env="cloud", store_backend="firestore", llm_backend="mock", proactive_enabled=True)


def db() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


def require_identity() -> None:
    if not PROJECT_ID or not PATIENT_ID.startswith("patient_") or not RUN_ID:
        raise RuntimeError("Wave14 recorder control requires project, patient id and run id")


def proof_ref(client: firestore.Client):
    return client.collection(PROOF_COLLECTION).document(RUN_ID)


def backup_ref(client: firestore.Client):
    return client.collection(BACKUP_COLLECTION).document(RUN_ID)


def _mailbox() -> str:
    constellation = build_google_constellation_service(cfg())
    connection = constellation.runtime.oauth_connection_store.load(PATIENT_ID)
    if connection is None or not connection.enabled:
        raise RuntimeError("Synthetic recorder patient has no enabled Google OAuth connection")
    mailbox = str(connection.google_account or "").strip().lower()
    scopes = {str(item).strip().lower() for item in connection.granted_scopes}
    if not mailbox or "@" not in mailbox or not any("gmail" in item for item in scopes):
        raise RuntimeError("Synthetic recorder patient does not have a usable Gmail connection")
    return mailbox


def _controlled_state(mailbox: str) -> PatientState:
    state = PatientState()
    state.profile.id = PATIENT_ID
    state.profile.display_name = "Ana Martínez · Synthetic Judge Demo"
    state.profile.email = mailbox
    state.profile.medications = []
    state.profile.confirmed_conditions = ["Synthetic hypertension follow-up proof"]
    state.profile.care_plan.blood_pressure_due_days = 1
    state.consent.proactive_enabled = True
    state.consent.quiet_hours_start = "00:00"
    state.consent.quiet_hours_end = "00:00"
    state.consent.signal_types = list(dict.fromkeys([
        *DEFAULT_SIGNAL_TYPES,
        BP_CONSENT,
        "guardian_email",
        "guardian_email_auto_send",
        GUARDIAN_EMAIL_REPLY_CONSENT,
    ]))
    state.vitals = [VitalRecord(
        patient_id=PATIENT_ID,
        measured_at=datetime.now(timezone.utc) - timedelta(days=3),
        systolic=138,
        diastolic=86,
        note="Synthetic Wave14 baseline only.",
    )]
    return state


def prestage() -> None:
    require_identity()
    client = db()
    patient_ref = client.collection(PATIENT_STATE_COLLECTION).document(PATIENT_ID)
    original = patient_ref.get()
    if backup_ref(client).get().exists:
        raise RuntimeError("Wave14 recorder backup already exists for this run")
    backup_ref(client).set({
        "patient_id": PATIENT_ID,
        "patient_state_existed": bool(original.exists),
        "patient_state": original.to_dict() if original.exists else None,
        "created_at": firestore.SERVER_TIMESTAMP,
    })
    state = _controlled_state(_mailbox())
    # Direct Firestore prestage deliberately avoids HealthIAService reconciliation.
    # The browser can therefore show the patient history before the autonomous
    # Guardian mission exists. Activation below crosses the real service boundary.
    patient_ref.set(state.model_dump(mode="json"))
    proof_ref(client).set({
        "patient_id": PATIENT_ID,
        "status": "recorder_prestaged",
        "prestage_at": firestore.SERVER_TIMESTAMP,
    })
    print(json.dumps({"phase": "prestage", "status": "ready"}))


async def activate() -> None:
    require_identity()
    client = db()
    if not backup_ref(client).get().exists:
        raise RuntimeError("Recorder activation requires the reversible prestage backup")
    patient_snapshot = client.collection(PATIENT_STATE_COLLECTION).document(PATIENT_ID).get()
    if not patient_snapshot.exists:
        raise RuntimeError("Prestaged patient state is missing")
    state = PatientState.model_validate(patient_snapshot.to_dict() or {})
    service = HealthIAService(cfg())
    with patient_scope(PATIENT_ID):
        await service.store.save(state)
        persisted = await service.snapshot()
    missions = [mission for mission in persisted.missions if mission.mission_type == BP_MISSION_TYPE]
    if len(missions) != 1:
        raise RuntimeError(f"Expected exactly one autonomous BP mission, found {len(missions)}")
    mission = missions[0]
    if mission.status != MissionStatus.WAITING_PATIENT:
        raise RuntimeError(f"Autonomous BP mission opened in unexpected state: {mission.status.value}")
    event_ids: list[str] = []
    for snapshot in client.collection(OUTBOX_COLLECTION).where("patient_id", "==", PATIENT_ID).stream():
        raw = snapshot.to_dict() or {}
        payload = ((raw.get("event") or {}).get("payload") or {})
        if payload.get("mission_id") == mission.id:
            event_ids.append(snapshot.id)
    if len(event_ids) != 1:
        raise RuntimeError(f"Expected one durable Guardian event, found {len(event_ids)}")
    event_id = event_ids[0]
    record = FirestoreEventOutboxStore(project=PROJECT_ID).get(event_id)
    if record is None or record.status not in {"pending", "processed"}:
        raise RuntimeError("Autonomous Guardian outbox is not durable")
    proof_ref(client).set({
        "mission_id": mission.id,
        "event_id": event_id,
        "status": "setup_complete",
        "setup_at": firestore.SERVER_TIMESTAMP,
        "outbound_processor": "eventarc_only",
    }, merge=True)
    print(json.dumps({"phase": "activate", "status": "ok", "mission_status": mission.status.value}))


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"prestage", "activate"}:
        raise SystemExit("usage: wave14_recorder_control.py prestage|activate")
    if sys.argv[1] == "prestage":
        prestage()
        return
    import asyncio
    asyncio.run(activate())


if __name__ == "__main__":
    main()
