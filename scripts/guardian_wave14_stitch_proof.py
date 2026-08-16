from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from healthia_one.auth import patient_scope
from healthia_one.autopilot_events import FirestoreEventOutboxStore
from healthia_one.bp_followup_guardian import CONSENT_SIGNAL as BP_CONSENT, MISSION_TYPE as BP_MISSION_TYPE
from healthia_one.config import Settings
from healthia_one.google_connector_runtime import GmailConnector
from healthia_one.google_constellation import GoogleAction
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.google_oauth_credentials import SecretManagerOAuthTokenProvider
from healthia_one.guardian_email_reply import GUARDIAN_EMAIL_REPLY_CONSENT, build_guardian_email_thread_store
from healthia_one.models import DEFAULT_SIGNAL_TYPES, MissionStatus, PatientState, VitalRecord
from healthia_one.service import HealthIAService
from healthia_one.store import PATIENT_STATE_COLLECTION

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "healthia-6088a").strip()
PATIENT_ID = os.environ.get("HEALTHIA_WAVE14_PROOF_PATIENT_ID", "").strip()
RUN_ID = os.environ.get("HEALTHIA_WAVE14_PROOF_RUN_ID", "").strip()
PROOF_COLLECTION = "healthia_wave14_stitch_proofs"
BACKUP_COLLECTION = "healthia_wave14_stitch_backups"
OUTBOX_COLLECTION = "healthia_autopilot_events"
THREAD_COLLECTION = "healthia_guardian_email_threads"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_identity() -> None:
    if not PROJECT_ID or not PATIENT_ID or not RUN_ID:
        raise RuntimeError("Stitch proof requires project, patient id and run id")
    if not PATIENT_ID.startswith("patient_"):
        raise RuntimeError("Stitch proof patient id violates synthetic patient contract")


def settings_value() -> Settings:
    return Settings(env="cloud", store_backend="firestore", llm_backend="mock", proactive_enabled=True)


def client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


def proof_ref(db: firestore.Client):
    return db.collection(PROOF_COLLECTION).document(RUN_ID)


def backup_ref(db: firestore.Client):
    return db.collection(BACKUP_COLLECTION).document(RUN_ID)


def short_hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16] if value else ""


def safe_print(payload: dict) -> None:
    allowed = {
        "phase", "status", "mission_id", "event_id", "thread_id_hash",
        "reply_message_id_hash", "mission_status", "vital_count", "outbox_status",
    }
    print(json.dumps({k: payload[k] for k in allowed if k in payload}, sort_keys=True))


async def setup() -> None:
    require_identity()
    cfg = settings_value()
    db = client()
    patient_ref = db.collection(PATIENT_STATE_COLLECTION).document(PATIENT_ID)
    original = patient_ref.get()
    if backup_ref(db).get().exists:
        raise RuntimeError("Stitch proof backup already exists for this run id")
    backup_ref(db).set({
        "patient_id": PATIENT_ID,
        "patient_state_existed": bool(original.exists),
        "patient_state": original.to_dict() if original.exists else None,
        "created_at": firestore.SERVER_TIMESTAMP,
    })

    constellation = build_google_constellation_service(cfg)
    connection = constellation.runtime.oauth_connection_store.load(PATIENT_ID)
    if connection is None or not connection.enabled:
        raise RuntimeError("Synthetic proof patient has no enabled Google OAuth connection")
    mailbox = str(connection.google_account or "").strip().lower()
    if not mailbox or "@" not in mailbox:
        raise RuntimeError("Synthetic proof OAuth connection has no usable mailbox")
    scopes = {str(item).strip().lower() for item in connection.granted_scopes}
    if not any("gmail" in item for item in scopes):
        raise RuntimeError("Synthetic proof OAuth connection has no Gmail scope")

    state = PatientState()
    state.profile.id = PATIENT_ID
    state.profile.display_name = "HealthIA Wave14 Full Loop Synthetic Proof"
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
        measured_at=utc_now() - timedelta(days=3),
        systolic=138,
        diastolic=86,
        note="Synthetic Wave14 baseline only.",
    )]

    service = HealthIAService(cfg)
    with patient_scope(PATIENT_ID):
        await service.store.save(state)
        persisted = await service.snapshot()
    missions = [m for m in persisted.missions if m.mission_type == BP_MISSION_TYPE]
    if len(missions) != 1:
        raise RuntimeError(f"Expected one BP mission, found {len(missions)}")
    mission = missions[0]
    if mission.status != MissionStatus.WAITING_PATIENT:
        raise RuntimeError(f"BP mission opened in unexpected state: {mission.status.value}")

    candidates = []
    for snapshot in db.collection(OUTBOX_COLLECTION).where("patient_id", "==", PATIENT_ID).stream():
        raw = snapshot.to_dict() or {}
        payload = ((raw.get("event") or {}).get("payload") or {})
        if payload.get("mission_id") == mission.id:
            candidates.append(snapshot.id)
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one Guardian outbox event, found {len(candidates)}")
    event_id = candidates[0]
    record = FirestoreEventOutboxStore(project=PROJECT_ID).get(event_id)
    if record is None or record.status not in {"pending", "processed"}:
        raise RuntimeError("Guardian outbox did not start in a valid durable state")

    proof_ref(db).set({
        "patient_id": PATIENT_ID,
        "mission_id": mission.id,
        "event_id": event_id,
        "setup_at": firestore.SERVER_TIMESTAMP,
        "status": "setup_complete",
        "outbound_processor": "eventarc_only",
    })
    safe_print({"phase": "setup", "status": "ok", "mission_id": mission.id, "event_id": event_id})


async def await_email() -> None:
    require_identity()
    db = client()
    metadata = proof_ref(db).get().to_dict() or {}
    mission_id = str(metadata.get("mission_id") or "")
    event_id = str(metadata.get("event_id") or "")
    if not mission_id or not event_id:
        raise RuntimeError("Stitch proof is missing mission/event metadata")

    outbox = FirestoreEventOutboxStore(project=PROJECT_ID)
    deadline = time.monotonic() + 180
    found = None
    while time.monotonic() < deadline:
        record = outbox.get(event_id)
        if record is not None and record.status == "failed":
            raise RuntimeError(f"Eventarc Autopilot failed: {record.last_error}")
        if record is not None and record.status == "processed":
            for snapshot in (
                db.collection(THREAD_COLLECTION)
                .document(PATIENT_ID)
                .collection("threads")
                .where("mission_id", "==", mission_id)
                .stream()
            ):
                raw = snapshot.to_dict() or {}
                if str(raw.get("event_id") or "") == event_id and str(raw.get("provider_message_id") or ""):
                    found = raw
                    break
        if found is not None:
            break
        await asyncio.sleep(3)
    if found is None:
        raise RuntimeError("Timed out waiting for Eventarc to process Guardian event and persist Gmail thread")

    thread_id = str(found.get("thread_id") or "")
    provider_message_id = str(found.get("provider_message_id") or "")
    if not thread_id or not provider_message_id:
        raise RuntimeError("Durable Guardian email thread link is incomplete")
    proof_ref(db).set({
        "outbound_at": firestore.SERVER_TIMESTAMP,
        "status": "eventarc_email_sent",
        "gmail_thread_id": thread_id,
        "provider_message_id": provider_message_id,
        "outbox_status": "processed",
    }, merge=True)
    safe_print({
        "phase": "await_email", "status": "ok", "mission_id": mission_id,
        "event_id": event_id, "thread_id_hash": short_hash(thread_id), "outbox_status": "processed",
    })


def _header(message: dict, name: str) -> str:
    needle = name.strip().lower()
    for item in (message.get("payload") or {}).get("headers") or []:
        if str(item.get("name") or "").strip().lower() == needle:
            return str(item.get("value") or "").strip()
    return ""


async def reply() -> None:
    require_identity()
    cfg = settings_value()
    db = client()
    metadata = proof_ref(db).get().to_dict() or {}
    thread_id = str(metadata.get("gmail_thread_id") or "")
    provider_message_id = str(metadata.get("provider_message_id") or "")
    mission_id = str(metadata.get("mission_id") or "")
    if not thread_id or not provider_message_id or not mission_id:
        raise RuntimeError("Reply phase is missing durable Gmail metadata")

    constellation = build_google_constellation_service(cfg)
    connection = constellation.runtime.oauth_connection_store.load(PATIENT_ID)
    if connection is None or not connection.enabled:
        raise RuntimeError("Synthetic proof Google connection is unavailable")
    mailbox = str(connection.google_account or "").strip().lower()
    token_provider = SecretManagerOAuthTokenProvider(connection_store=constellation.runtime.oauth_connection_store)
    gmail = GmailConnector(PATIENT_ID, token_provider)
    read = gmail.execute(
        GoogleAction.GMAIL_READ_THREAD,
        {"thread_id": thread_id},
        idempotency_key=hashlib.sha256(f"{RUN_ID}|stitch-read-thread".encode()).hexdigest(),
    )
    original = next(
        (m for m in (read.data.get("messages") or []) if str(m.get("id") or "") == provider_message_id),
        None,
    )
    if original is None:
        raise RuntimeError("Unable to reread Eventarc-sent Guardian Gmail message")
    rfc_message_id = _header(original, "Message-ID")
    subject = _header(original, "Subject") or "HealthIA Guardian proof"
    if not rfc_message_id:
        raise RuntimeError("Guardian Gmail message has no RFC Message-ID")

    result = gmail.execute(
        GoogleAction.GMAIL_REPLY,
        {
            "to": [mailbox],
            "subject": subject,
            "body": "BP 128/80",
            "thread_id": thread_id,
            "in_reply_to": rfc_message_id,
        },
        idempotency_key=hashlib.sha256(f"{RUN_ID}|stitch-synthetic-reply".encode()).hexdigest(),
    )
    reply_message_id = str(result.resource_id or "")
    if not reply_message_id:
        raise RuntimeError("Synthetic Gmail reply returned no message id")
    proof_ref(db).set({
        "reply_at": firestore.SERVER_TIMESTAMP,
        "status": "reply_sent",
        "reply_message_id": reply_message_id,
    }, merge=True)
    safe_print({
        "phase": "reply", "status": "ok", "mission_id": mission_id,
        "thread_id_hash": short_hash(thread_id), "reply_message_id_hash": short_hash(reply_message_id),
    })


async def verify() -> None:
    require_identity()
    cfg = settings_value()
    db = client()
    metadata = proof_ref(db).get().to_dict() or {}
    mission_id = str(metadata.get("mission_id") or "")
    event_id = str(metadata.get("event_id") or "")
    thread_id = str(metadata.get("gmail_thread_id") or "")
    reply_message_id = str(metadata.get("reply_message_id") or "")
    if not all((mission_id, event_id, thread_id, reply_message_id)):
        raise RuntimeError("Verify phase is missing proof metadata")

    deadline = time.monotonic() + 150
    final = None
    while time.monotonic() < deadline:
        service = HealthIAService(cfg)
        with patient_scope(PATIENT_ID):
            state = await service.snapshot()
        mission = next((m for m in state.missions if m.id == mission_id), None)
        matching = [
            v for v in state.vitals
            if v.source.source_type == "patient_email_reply"
            and v.source.source_id == f"gmail:{reply_message_id}"
        ]
        if mission is not None and mission.status == MissionStatus.COMPLETED and len(matching) == 1:
            final = (mission, matching[0])
            break
        await asyncio.sleep(3)
    if final is None:
        raise RuntimeError("Timed out waiting for Gmail Pub/Sub to close stitched Guardian mission")

    mission, vital = final
    if (vital.systolic, vital.diastolic) != (128, 80):
        raise RuntimeError("Gmail-derived BP does not match controlled synthetic reply")
    if vital.id not in mission.evidence_ids:
        raise RuntimeError("Completed mission does not preserve Gmail-derived vital evidence")
    link = build_guardian_email_thread_store(cfg).load_by_thread(PATIENT_ID, thread_id)
    if link is None or reply_message_id not in link.processed_message_ids:
        raise RuntimeError("Gmail worker did not durably mark the reply as processed")
    outbox_record = FirestoreEventOutboxStore(project=PROJECT_ID).get(event_id)
    if outbox_record is None or outbox_record.status != "processed":
        raise RuntimeError("Guardian outbox is not durably processed")

    proof_ref(db).set({
        "verify_at": firestore.SERVER_TIMESTAMP,
        "status": "full_loop_live_pass",
        "mission_status": mission.status.value,
        "vital_source_type": vital.source.source_type,
        "outbox_status": outbox_record.status,
        "processed_reply_count": link.processed_message_ids.count(reply_message_id),
        "eventarc_outbound": True,
        "gmail_pubsub_inbound": True,
    }, merge=True)
    safe_print({
        "phase": "verify", "status": "full_loop_live_pass", "mission_id": mission.id,
        "event_id": event_id, "thread_id_hash": short_hash(thread_id),
        "reply_message_id_hash": short_hash(reply_message_id), "mission_status": mission.status.value,
        "vital_count": 1, "outbox_status": outbox_record.status,
    })


async def restore() -> None:
    require_identity()
    db = client()
    backup_snapshot = backup_ref(db).get()
    if not backup_snapshot.exists:
        safe_print({"phase": "restore", "status": "no_backup"})
        return
    backup = backup_snapshot.to_dict() or {}
    patient_ref = db.collection(PATIENT_STATE_COLLECTION).document(PATIENT_ID)
    if backup.get("patient_state_existed") and isinstance(backup.get("patient_state"), dict):
        patient_ref.set(backup["patient_state"])
    else:
        patient_ref.delete()

    metadata_snapshot = proof_ref(db).get()
    metadata = metadata_snapshot.to_dict() if metadata_snapshot.exists else {}
    event_id = str((metadata or {}).get("event_id") or "")
    thread_id = str((metadata or {}).get("gmail_thread_id") or "")
    if event_id:
        db.collection(OUTBOX_COLLECTION).document(event_id).delete()
    if thread_id:
        db.collection(THREAD_COLLECTION).document(PATIENT_ID).collection("threads").document(thread_id).delete()
    backup_ref(db).delete()
    safe_print({"phase": "restore", "status": "restored"})


async def main() -> None:
    phases = {"setup", "await_email", "reply", "verify", "restore"}
    if len(sys.argv) != 2 or sys.argv[1] not in phases:
        raise SystemExit("usage: guardian_wave14_stitch_proof.py setup|await_email|reply|verify|restore")
    await globals()[sys.argv[1]]()


if __name__ == "__main__":
    asyncio.run(main())
