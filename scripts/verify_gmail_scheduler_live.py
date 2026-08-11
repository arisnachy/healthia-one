from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any
from urllib import error, request

from google.auth import default
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud import firestore


CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
WATCH_COLLECTION = "healthia_gmail_watch_state"
PROOF_SCHEMA_VERSION = "scheduler-live-v1"


def _token() -> str:
    credentials, _ = default(scopes=[CLOUD_SCOPE])
    credentials.refresh(GoogleAuthRequest())
    value = str(credentials.token or "")
    if not value:
        raise RuntimeError("ADC did not produce a Cloud access token")
    return value


def _json_call(method: str, url: str, *, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=payload, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw or "{}")
    except error.HTTPError as exc:
        detail = ""
        try:
            parsed = json.loads(exc.read().decode("utf-8") or "{}")
            detail = str((parsed.get("error") or {}).get("status") or "")
        except Exception:
            pass
        raise RuntimeError(f"Google REST {method} failed: HTTP {exc.code} {detail}".strip()) from exc


def _job_url(project: str, location: str, job: str) -> str:
    return (
        "https://cloudscheduler.googleapis.com/v1/projects/"
        f"{project}/locations/{location}/jobs/{job}"
    )


def _safe_patient_key(patient_id: str) -> str:
    return hashlib.sha256(patient_id.encode("utf-8")).hexdigest()[:16]


def _watch_snapshot(client: firestore.Client, patient_id: str) -> dict[str, Any]:
    snap = client.collection(WATCH_COLLECTION).document(patient_id).get()
    if not snap.exists:
        raise RuntimeError("Controlled patient has no Gmail watch metadata")
    data = snap.to_dict() or {}
    return {
        "history_id": str(data.get("history_id") or ""),
        "expiration_ms": int(data["expiration_ms"]) if data.get("expiration_ms") is not None else None,
        "enabled": bool(data.get("enabled", True)),
        "updated_at": str(data.get("updated_at") or ""),
    }


def _job_attempt(job: dict[str, Any]) -> tuple[str, int | None]:
    return str(job.get("lastAttemptTime") or ""), (job.get("status") or {}).get("code")


def _wait_for_attempt(
    *, project: str, location: str, job: str, token: str, previous: str, timeout_seconds: int = 90
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    url = _job_url(project, location, job)
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = _json_call("GET", url, token=token)
        attempt, code = _job_attempt(latest)
        if attempt and attempt != previous and code in {None, 0}:
            return latest
        time.sleep(2)
    raise RuntimeError("Cloud Scheduler did not expose a successful new attempt before timeout")


def _wait_for_watch_change(
    client: firestore.Client,
    patient_id: str,
    before: dict[str, Any],
    *,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        current = _watch_snapshot(client, patient_id)
        if (
            current["expiration_ms"] is not None
            and current["expiration_ms"] != before["expiration_ms"]
            and current["history_id"].isdigit()
        ):
            return current
        time.sleep(2)
    raise RuntimeError("Gmail watch metadata did not advance after Scheduler execution")


def verify(args: argparse.Namespace) -> dict[str, Any]:
    if args.patient_id and (not args.patient_id.startswith("patient_") or args.patient_id == "patient_demo"):
        raise RuntimeError("--patient-id must be a controlled real HealthIA patient_ identifier")
    token = _token()
    job_url = _job_url(args.project, args.location, args.job_name)
    job = _json_call("GET", job_url, token=token)

    target = job.get("httpTarget") or {}
    oidc = target.get("oidcToken") or {}
    uri = str(target.get("uri") or "")
    method = str(target.get("httpMethod") or "")
    service_account = str(oidc.get("serviceAccountEmail") or "")
    audience = str(oidc.get("audience") or "")
    if not uri.endswith("/scheduled/renew-gmail-watches"):
        raise RuntimeError("Scheduler target is not the Gmail renewal endpoint")
    if method != "POST":
        raise RuntimeError("Scheduler Gmail renewal target must use POST")
    if args.scheduler_service_account and service_account != args.scheduler_service_account:
        raise RuntimeError("Scheduler OIDC service account does not match the expected identity")
    worker_url = uri.removesuffix("/scheduled/renew-gmail-watches")
    if audience.rstrip("/") != worker_url.rstrip("/"):
        raise RuntimeError("Scheduler OIDC audience does not match the private worker URL")

    result: dict[str, Any] = {
        "proof_schema": PROOF_SCHEMA_VERSION,
        "status": "CONFIG_PASS",
        "job_name": args.job_name,
        "schedule": str(job.get("schedule") or ""),
        "time_zone": str(job.get("timeZone") or ""),
        "worker_target": "/scheduled/renew-gmail-watches",
        "oidc_identity_configured": bool(service_account),
        "secret_material_exposed": False,
    }
    if not args.confirmed_live_run:
        return result
    if not args.patient_id:
        raise RuntimeError("--patient-id is required with --confirmed-live-run")

    db = firestore.Client(project=args.project)
    document = db.collection(WATCH_COLLECTION).document(args.patient_id)
    original = _watch_snapshot(db, args.patient_id)
    if not original["enabled"]:
        raise RuntimeError("Controlled patient Gmail watch is disabled")

    document.update({"expiration_ms": 0, "updated_at": datetime.now(timezone.utc).isoformat()})
    due = _watch_snapshot(db, args.patient_id)
    first_before_attempt, _ = _job_attempt(job)

    try:
        _json_call("POST", f"{job_url}:run", token=token, body={})
        first_job = _wait_for_attempt(
            project=args.project,
            location=args.location,
            job=args.job_name,
            token=token,
            previous=first_before_attempt,
        )
        renewed = _wait_for_watch_change(db, args.patient_id, due)
        if renewed["expiration_ms"] is None or renewed["expiration_ms"] <= int(time.time() * 1000):
            raise RuntimeError("Scheduler ran but Gmail watch expiration is not in the future")

        first_attempt, first_code = _job_attempt(first_job)
        stable_before_second = renewed.copy()
        _json_call("POST", f"{job_url}:run", token=token, body={})
        second_job = _wait_for_attempt(
            project=args.project,
            location=args.location,
            job=args.job_name,
            token=token,
            previous=first_attempt,
        )
        time.sleep(3)
        after_second = _watch_snapshot(db, args.patient_id)
        if after_second["history_id"] != stable_before_second["history_id"]:
            raise RuntimeError("Second Scheduler run unexpectedly changed Gmail history cursor")
        if after_second["expiration_ms"] != stable_before_second["expiration_ms"]:
            raise RuntimeError("Second Scheduler run unexpectedly renewed a non-due Gmail watch")
        _, second_code = _job_attempt(second_job)

        result.update(
            {
                "status": "LIVE_PASS",
                "patient_key": _safe_patient_key(args.patient_id),
                "first_scheduler_status_code": first_code,
                "second_scheduler_status_code": second_code,
                "watch_history_id_advanced": renewed["history_id"] != original["history_id"],
                "watch_expiration_future": True,
                "second_run_noop": True,
            }
        )
        return result
    except Exception:
        current = _watch_snapshot(db, args.patient_id)
        if current["expiration_ms"] == 0:
            document.update(
                {
                    "history_id": original["history_id"],
                    "expiration_ms": original["expiration_ms"],
                    "enabled": original["enabled"],
                    "updated_at": original["updated_at"],
                }
            )
        raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Verify HealthIA Gmail Scheduler renewal against Google Cloud")
    value.add_argument("--project", required=True)
    value.add_argument("--location", default="us-central1")
    value.add_argument("--job-name", default="healthia-gmail-watch-renewal")
    value.add_argument("--scheduler-service-account", default="")
    value.add_argument("--patient-id", default="")
    value.add_argument("--confirmed-live-run", action="store_true")
    return value


def main() -> int:
    try:
        result = verify(parser().parse_args())
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__, "detail": str(exc)[:240]}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
