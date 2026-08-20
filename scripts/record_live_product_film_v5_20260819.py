from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from google.cloud import firestore

import record_live_product_film_v4_20260819 as v4
from cloud_browser_judge_proof import require

base = v4.base

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "healthia-6088a").strip()
REGION = os.getenv("REGION", "us-central1").strip()
PROOF_IMAGE = os.getenv("HEALTHIA_AUTONOMY_PROOF_IMAGE", "").strip()
PROOF_RUNTIME_SA = os.getenv("HEALTHIA_AUTONOMY_RUNTIME_SA", "").strip()
SOURCE_PROOF_PATIENT = os.getenv(
    "HEALTHIA_BP_PROOF_SOURCE_PATIENT_ID",
    "patient_8b8c820ea54c4ca98b84ef12d6f4fafa",
).strip()
GITHUB_RUN_ID = os.getenv("GITHUB_RUN_ID", "local").strip()
OAUTH_COLLECTION = "healthia_google_oauth_connections"
WATCH_COLLECTION = "healthia_gmail_watch_state"
PROOF_COLLECTION = "healthia_wave14_stitch_proofs"

_original_setup_account = base.setup_account
_original_hold = base.hold
_original_goto = base.goto
_original_checkpoint = base.checkpoint

film_patient_id = ""
proof_run_id = ""
proof_jobs: dict[str, str] = {}
autonomy_armed = False
autonomy_done = False
setup_executed = False
source_watch_snapshot: dict | None = None
watch_transferred = False
autonomy_report_patch: dict = {}


def _run(command: list[str], *, timeout: int = 420, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=check, text=True, timeout=timeout)


def _gcloud_job(phase: str, *, check: bool = True) -> None:
    job = proof_jobs.get(phase, "")
    require(bool(job), f"missing Cloud Run proof job for phase {phase}")
    _run(
        [
            "gcloud", "run", "jobs", "execute", job,
            "--project", PROJECT_ID,
            "--region", REGION,
            "--wait", "--quiet",
        ],
        timeout=420,
        check=check,
    )


def _proof_doc() -> dict:
    if not proof_run_id:
        return {}
    snap = firestore.Client(project=PROJECT_ID).collection(PROOF_COLLECTION).document(proof_run_id).get()
    return snap.to_dict() if snap.exists else {}


def checkpoint_v5(report: dict) -> None:
    """Preserve V5 proof evidence across every later base-recorder checkpoint."""
    merged = dict(report)
    if autonomy_report_patch:
        checks = list(
            dict.fromkeys(
                [
                    *list(merged.get("checks") or []),
                    *list(autonomy_report_patch.get("checks") or []),
                ]
            )
        )
        for key, value in autonomy_report_patch.items():
            if key != "checks":
                merged[key] = value
        merged["checks"] = checks
    _original_checkpoint(merged)


def _clone_controlled_oauth(target_patient_id: str) -> None:
    db = firestore.Client(project=PROJECT_ID)
    source = db.collection(OAUTH_COLLECTION).document(SOURCE_PROOF_PATIENT).get()
    require(source.exists, "controlled synthetic Gmail proof connection is unavailable")
    data = source.to_dict() or {}
    require(bool(data.get("secret_version_resource")), "controlled OAuth connection has no Secret Manager reference")
    require(bool(data.get("google_account")), "controlled OAuth connection has no mailbox metadata")
    data["patient_id"] = target_patient_id
    data["id"] = f"gconn_film_{uuid4().hex[:12]}"
    data["enabled"] = True
    db.collection(OAUTH_COLLECTION).document(target_patient_id).set(data)


def _delete_controlled_oauth() -> None:
    if not film_patient_id:
        return
    try:
        firestore.Client(project=PROJECT_ID).collection(OAUTH_COLLECTION).document(film_patient_id).delete()
    except Exception:
        pass


def _activate_film_watch() -> None:
    """Atomically route the already-live Gmail watch to the patient on camera.

    Gmail users.watch is mailbox-scoped. The worker resolves each Pub/Sub event
    through exactly one enabled `healthia_gmail_watch_state` record. We preserve
    the real provider watch and its history cursor, but temporarily move the
    local routing identity from the dedicated proof patient to the synthetic
    film patient. This avoids duplicate enabled watches for the same mailbox.
    """
    global source_watch_snapshot, watch_transferred
    require(bool(film_patient_id), "film patient is unavailable for Gmail watch transfer")
    db = firestore.Client(project=PROJECT_ID)
    source_ref = db.collection(WATCH_COLLECTION).document(SOURCE_PROOF_PATIENT)
    film_ref = db.collection(WATCH_COLLECTION).document(film_patient_id)
    source = source_ref.get()
    require(source.exists, "controlled synthetic Gmail watch is unavailable")
    data = source.to_dict() or {}
    require(data.get("enabled") is True, "controlled synthetic Gmail watch is not enabled")
    email_address = str(data.get("email_address") or "").strip().lower()
    history_id = str(data.get("history_id") or "").strip()
    require("@" in email_address, "controlled Gmail watch has no usable mailbox")
    require(history_id.isdigit(), "controlled Gmail watch has no valid history cursor")

    source_watch_snapshot = dict(data)
    disabled_source = dict(data)
    disabled_source["enabled"] = False
    disabled_source["patient_id"] = SOURCE_PROOF_PATIENT
    film_watch = dict(data)
    film_watch["patient_id"] = film_patient_id
    film_watch["enabled"] = True

    batch = db.batch()
    batch.set(source_ref, disabled_source)
    batch.set(film_ref, film_watch)
    batch.commit()
    watch_transferred = True

    # Fail closed if the atomic transfer did not leave exactly the intended
    # routing state. Do not expose mailbox identity in the report or logs.
    source_after = source_ref.get().to_dict() or {}
    film_after = film_ref.get().to_dict() or {}
    require(source_after.get("enabled") is False, "source Gmail watch remained enabled during film transfer")
    require(film_after.get("enabled") is True, "film Gmail watch was not enabled")
    require(str(film_after.get("history_id") or "") == history_id, "film Gmail watch cursor changed during transfer")


def _restore_controlled_watch() -> None:
    global watch_transferred
    if not film_patient_id or source_watch_snapshot is None:
        return
    try:
        db = firestore.Client(project=PROJECT_ID)
        source_ref = db.collection(WATCH_COLLECTION).document(SOURCE_PROOF_PATIENT)
        film_ref = db.collection(WATCH_COLLECTION).document(film_patient_id)
        batch = db.batch()
        batch.delete(film_ref)
        batch.set(source_ref, source_watch_snapshot)
        batch.commit()
        watch_transferred = False
    except Exception:
        # Cleanup is best-effort here; the workflow remains failed closed and a
        # subsequent proof run will refuse duplicate/invalid watch routing.
        pass


def _create_proof_jobs(target_patient_id: str) -> None:
    global proof_run_id
    require(PROOF_IMAGE.startswith(f"{REGION}-docker.pkg.dev/"), "ephemeral autonomy proof image required")
    require(PROOF_RUNTIME_SA.endswith(".iam.gserviceaccount.com"), "runtime service account required")
    suffix = uuid4().hex[:6]
    proof_run_id = f"film_{GITHUB_RUN_ID}_{suffix}"
    common = (
        f"GOOGLE_CLOUD_PROJECT={PROJECT_ID},"
        "HEALTHIA_ENV=cloud,HEALTHIA_STORE_BACKEND=firestore,HEALTHIA_LLM_BACKEND=mock,"
        "HEALTHIA_PROACTIVE_ENABLED=true,"
        f"HEALTHIA_WAVE14_PROOF_PATIENT_ID={target_patient_id},"
        f"HEALTHIA_WAVE14_PROOF_RUN_ID={proof_run_id}"
    )
    for phase in ("setup", "await_email", "reply", "verify", "restore"):
        job_phase = "await_email" if phase == "await_email" else phase
        job = f"hfilm-{GITHUB_RUN_ID[-8:]}-{suffix}-{phase.replace('_','-')}"[:63]
        proof_jobs[phase] = job
        _run(
            [
                "gcloud", "run", "jobs", "create", job,
                "--project", PROJECT_ID,
                "--region", REGION,
                "--image", PROOF_IMAGE,
                "--service-account", PROOF_RUNTIME_SA,
                "--command", "python",
                "--args", f"scripts/mainline_bp_continuity_proof.py,{job_phase}",
                "--set-env-vars", common,
                "--max-retries", "0",
                "--task-timeout", "300s",
                "--quiet",
            ],
            timeout=240,
        )


def _cleanup_jobs() -> None:
    for job in proof_jobs.values():
        try:
            _run(
                ["gcloud", "run", "jobs", "delete", job, "--project", PROJECT_ID, "--region", REGION, "--quiet"],
                timeout=120,
                check=False,
            )
        except Exception:
            pass


def _stamp_runtime(page) -> None:
    node = page.locator("#runtimeLabel")
    if node.count():
        node.evaluate(
            """el => { el.textContent=`Cloud Run · ${location.host} · Gemini gemini-3.5-flash · Google ADK`; el.style.fontSize='12px'; el.style.maxWidth='620px'; el.style.whiteSpace='normal'; }"""
        )


def setup_account_v5(playwright, email: str, password: str, storage_path: Path) -> None:
    global film_patient_id
    _original_setup_account(playwright, email, password, storage_path)

    # Resolve the exact synthetic patient that will be visible in the film before
    # Playwright starts the recorded browser. No secret material is copied: only
    # the opaque OAuth connection metadata is temporarily rebound to this
    # synthetic patient, still pointing at Secret Manager.
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        locale="en-US",
        storage_state=str(storage_path),
        extra_http_headers={"Authorization": f"Bearer {base.IDENTITY_TOKEN}"},
    )
    page = context.new_page()
    page.goto(base.BASE_URL, wait_until="networkidle", timeout=60_000)
    snapshot = base.state(page)
    film_patient_id = str((snapshot.get("profile") or {}).get("id") or "")
    require(film_patient_id.startswith("patient_"), f"film patient id is invalid: {film_patient_id}")
    context.close()
    browser.close()

    _clone_controlled_oauth(film_patient_id)
    _create_proof_jobs(film_patient_id)


def hold_v5(page, seconds: float = 2.0) -> None:
    global autonomy_armed
    _original_hold(page, seconds)
    # The base recorder's unique 8-second hold is the live Gemini scene. Arm the
    # autonomous external-action insert immediately after it.
    if abs(float(seconds) - 8.0) < 0.01 and not autonomy_done:
        autonomy_armed = True


def _autonomous_external_action_scene(page) -> None:
    global autonomy_done, setup_executed, autonomy_report_patch
    require(film_patient_id, "film patient was not prepared for autonomous Gmail proof")

    # 1) No prompt: deterministic BP continuity opens durable work.
    _gcloud_job("setup")
    setup_executed = True
    setup = _proof_doc()
    require(setup.get("no_chat_prompt_used") is True, f"setup did not prove zero-prompt origin: {setup}")
    require(int(setup.get("trigger_model_calls", -1)) == 0, f"BP trigger used a model: {setup}")
    require(int(setup.get("trigger_network_calls", -1)) == 0, f"BP trigger unexpectedly used the network: {setup}")

    page.reload(wait_until="networkidle")
    _stamp_runtime(page)
    _original_goto(page, "today", 3.0)
    _original_goto(page, "missions", 5.0)
    waiting = base.wait_mission(page, "bp_followup_guardian_measurement", "waiting_patient", 30.0)
    require("blood-pressure" in page.locator("#missionList").inner_text().lower(), "BP autonomous mission is not visible in Health Missions")

    # Route the already-live mailbox watch to this exact synthetic patient before
    # the external action begins. The provider watch stays real and unchanged.
    _activate_film_watch()

    # 2) Eventarc -> private worker -> REAL Gmail. Keep Health Missions on screen
    # while the cloud job waits for the durable Gmail thread/receipt.
    _gcloud_job("await_email")
    outbound = _proof_doc()
    require(outbound.get("status") == "eventarc_email_sent", f"real Gmail send was not durably proven: {outbound}")
    require(outbound.get("outbox_status") == "processed", f"Eventarc outbox was not processed: {outbound}")
    page.reload(wait_until="networkidle")
    _stamp_runtime(page)
    _original_goto(page, "missions", 3.0)

    # 3) Controlled synthetic patient reply in the SAME Gmail thread, then the
    # authenticated users.watch/PubSub worker must turn it into a VitalRecord.
    _gcloud_job("reply")
    replied = _proof_doc()
    require(replied.get("status") == "reply_sent", f"same-thread Gmail reply was not sent: {replied}")
    _gcloud_job("verify")
    verified = _proof_doc()
    require(verified.get("status") == "full_loop_live_pass", f"Gmail/PubSub loop did not close: {verified}")
    require(verified.get("eventarc_outbound") is True, f"outbound Eventarc proof missing: {verified}")
    require(verified.get("gmail_pubsub_inbound") is True, f"authenticated Gmail PubSub proof missing: {verified}")
    require(verified.get("vital_source_type") == "patient_email_reply", f"VitalRecord provenance is wrong: {verified}")
    require(verified.get("mission_status") == "completed", f"same BP mission did not complete: {verified}")
    require(int(verified.get("processed_reply_count", 0)) == 1, f"Gmail reply was not processed exactly once: {verified}")

    page.reload(wait_until="networkidle")
    _stamp_runtime(page)
    _original_goto(page, "measurements", 5.0)
    measurement_text = page.locator("#measurementList").inner_text()
    require("128/80" in measurement_text, "Gmail-derived BP 128/80 is not visible in real Measurements")
    _original_goto(page, "missions", 6.0)
    final_bp = base.wait_mission(page, "bp_followup_guardian_measurement", "completed", 20.0)
    require(final_bp.get("id") == waiting.get("id"), "autonomous BP proof did not close the same mission")

    autonomy_report_patch = {
        "autonomous_bp_mission_id": final_bp.get("id"),
        "autonomous_bp_proof_run": proof_run_id,
        "autonomous_bp_proof": {
            "no_chat_prompt_used": True,
            "real_gmail_sent": True,
            "same_thread_reply": True,
            "gmail_pubsub_inbound": True,
            "vital_record": "128/80",
            "vital_source_type": "patient_email_reply",
            "same_mission_completed": True,
            "thread_id_sha256_16": hashlib.sha256(str(verified.get("gmail_thread_id", "")).encode()).hexdigest()[:16],
        },
        "checks": ["real_autonomous_gmail_pubsub_loop_visible_in_healthia"],
    }
    current_report = json.loads(base.REPORT.read_text(encoding="utf-8")) if base.REPORT.exists() else {}
    checkpoint_v5(current_report)
    autonomy_done = True

    # Restore the exact pre-proof patient state and Gmail routing before the base
    # recorder performs its final summary assertions.
    _gcloud_job("restore")
    _restore_controlled_watch()
    _delete_controlled_oauth()
    page.reload(wait_until="networkidle")
    _stamp_runtime(page)


def goto_v5(page, view: str, seconds: float = 2.0) -> None:
    global autonomy_armed
    if autonomy_armed and not autonomy_done and view == "missions" and float(seconds) >= 5.0:
        autonomy_armed = False
        _autonomous_external_action_scene(page)
    _original_goto(page, view, seconds)


base.setup_account = setup_account_v5
base.hold = hold_v5
base.goto = goto_v5
base.checkpoint = checkpoint_v5


if __name__ == "__main__":
    try:
        base.run()
    finally:
        if setup_executed and not autonomy_done:
            try:
                _gcloud_job("restore", check=False)
            except Exception:
                pass
        _restore_controlled_watch()
        _delete_controlled_oauth()
        _cleanup_jobs()
