from __future__ import annotations

# Proof-only recorder trigger revision 2. Product source remains untouched.
import hashlib
import os
import sys
from datetime import datetime, timezone

from google.cloud import firestore

from healthia_one.auth import _password_hash

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "healthia-6088a").strip()
PATIENT_ID = os.environ.get("HEALTHIA_WAVE14_PROOF_PATIENT_ID", "").strip()
RUN_ID = os.environ.get("HEALTHIA_WAVE14_PROOF_RUN_ID", "").strip()
EMAIL = os.environ.get("HEALTHIA_WAVE14_RECORDER_EMAIL", "").strip().lower()
PASSWORD = os.environ.get("HEALTHIA_WAVE14_RECORDER_PASSWORD", "").strip()
COLLECTION = "healthia_one_accounts"


def require_inputs() -> None:
    if not PROJECT_ID or not PATIENT_ID.startswith("patient_") or not RUN_ID:
        raise RuntimeError("Recorder account requires project, synthetic patient id and run id")
    if not EMAIL or "@" not in EMAIL or "." not in EMAIL.rsplit("@", 1)[-1]:
        raise RuntimeError("Recorder account email is invalid")
    if len(PASSWORD) < 10:
        raise RuntimeError("Recorder account password is too short")


def doc_id() -> str:
    return hashlib.sha256(EMAIL.encode("utf-8")).hexdigest()


def setup() -> None:
    require_inputs()
    db = firestore.Client(project=PROJECT_ID)
    ref = db.collection(COLLECTION).document(doc_id())
    if ref.get().exists:
        raise RuntimeError("Temporary recorder account already exists")
    ref.set(
        {
            "account_id": f"account_wave14_recorder_{RUN_ID}",
            "patient_id": PATIENT_ID,
            "email": EMAIL,
            "display_name": "Ana Martínez · Synthetic Judge Demo",
            "password_hash": _password_hash(PASSWORD),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "disabled": False,
            "proof_only": True,
            "proof_run_id": RUN_ID,
        }
    )
    print("WAVE14_RECORDER_ACCOUNT_READY")


def cleanup() -> None:
    require_inputs()
    db = firestore.Client(project=PROJECT_ID)
    ref = db.collection(COLLECTION).document(doc_id())
    snapshot = ref.get()
    if snapshot.exists:
        raw = snapshot.to_dict() or {}
        if raw.get("proof_only") is not True or str(raw.get("proof_run_id") or "") != RUN_ID:
            raise RuntimeError("Refusing to delete a non-proof account")
        ref.delete()
    print("WAVE14_RECORDER_ACCOUNT_REMOVED")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"setup", "cleanup"}:
        raise SystemExit("usage: wave14_recorder_account.py setup|cleanup")
    globals()[sys.argv[1]]()


if __name__ == "__main__":
    main()