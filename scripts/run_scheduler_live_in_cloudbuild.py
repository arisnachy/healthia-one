from __future__ import annotations

import argparse
import json
import sys
from types import SimpleNamespace

from google.cloud import firestore

from scripts.verify_gmail_scheduler_live import verify


WATCH_COLLECTION = "healthia_gmail_watch_state"
OAUTH_COLLECTION = "healthia_google_oauth_connections"
GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def discover_controlled_patient(project: str) -> str:
    db = firestore.Client(project=project)
    candidates: list[str] = []
    for watch_doc in db.collection(WATCH_COLLECTION).stream():
        watch = watch_doc.to_dict() or {}
        if not bool(watch.get("enabled", True)):
            continue
        connection_doc = db.collection(OAUTH_COLLECTION).document(watch_doc.id).get()
        if not connection_doc.exists:
            continue
        connection = connection_doc.to_dict() or {}
        if not bool(connection.get("enabled", False)):
            continue
        mailbox = str(watch.get("email_address") or "").strip().lower()
        google_account = str(connection.get("google_account") or "").strip().lower()
        scopes = {str(item) for item in (connection.get("granted_scopes") or [])}
        if mailbox and mailbox == google_account and GMAIL_READ_SCOPE in scopes:
            candidates.append(watch_doc.id)
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected exactly one controlled enabled OAuth+Gmail watch pair; found {len(candidates)}"
        )
    patient_id = candidates[0]
    if not patient_id.startswith("patient_") or patient_id == "patient_demo":
        raise RuntimeError("Discovered controlled patient identifier is invalid")
    return patient_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--job-name", default="healthia-gmail-watch-renewal")
    args = parser.parse_args()
    try:
        patient_id = discover_controlled_patient(args.project)
        result = verify(
            SimpleNamespace(
                project=args.project,
                location=args.location,
                job_name=args.job_name,
                scheduler_service_account="",
                patient_id=patient_id,
                confirmed_live_run=True,
            )
        )
        if result.get("status") != "LIVE_PASS":
            raise RuntimeError("Scheduler verifier did not return LIVE_PASS")
        if result.get("watch_expiration_future") is not True:
            raise RuntimeError("Scheduler proof did not produce a future watch expiration")
        if result.get("second_run_noop") is not True:
            raise RuntimeError("Scheduler duplicate run was not a no-op")
        if result.get("secret_material_exposed") is not False:
            raise RuntimeError("Scheduler proof secret boundary failed")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__, "detail": str(exc)[:220]}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
