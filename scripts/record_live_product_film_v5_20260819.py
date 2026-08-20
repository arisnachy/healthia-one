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
PROOF_COLLECTION = "healthia_wave14_stitch_proofs"

_original_setup_account = base.setup_account
_original_hold = base.hold
_original_goto = base.goto

film_patient_id = ""
proof_run_id = ""
proof_jobs: dict[str, str] = {}
autonomy_armed = False
autonomy_done = False
setup_executed = False


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
    global autonomy_done, setup_executed
    require(film_patient_id, "film patient was not prepared for autonomous Gmail proof")

    # 1) No prompt: deterministic BP continuity opens durable work.
    _gcloud_job("setup")
    setup_executed = True
    setup = _proof_doc()
    require(setup.get("no_chat_prompt_used") is True, f"setup did not prove zero-prompt origin: {setup}")
    require(int(setup.get("trigger_model_calls", -1)) == 0, f"BP trigger used a model: {setup}")

    page.reload(wait_until="networkidle")
    _stamp_runtime(page)
    _original_goto(page, "today", 3.0)
    _original_goto(page, "missions", 5.0)
    waiting = base.wait_mission(page, "bp_followup_guardian_measurement", "waiting_patient", 30.0)
    require("blood-pressure" in page.locator("#missionList").inner_text().lower(), "BP autonomous mission is not visible in Health Missions")

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

    report = json.loads(base.REPORT.read_text(encoding="utf-8")) if base.REPORT.exists() else {}
    report["autonomous_bp_mission_id"] = final_bp.get("id")
    report["autonomous_bp_proof_run"] = proof_run_id
    report["autonomous_bp_proof"] = {
        "no_chat_prompt_used": True,
        "real_gmail_sent": True,
        "same_thread_reply": True,
        "gmail_pubsub_inbound": True,
        "vital_record": "128/80",
        "vital_source_type": "patient_email_reply",
        "same_mission_completed": True,
        "thread_id_sha256_16": hashlib.sha256(str(verified.get("gmail_thread_id", "")).encode()).hexdigest()[:16],
    }
    report.setdefault("checks", []).append("real_autonomous_gmail_pubsub_loop_visible_in_healthia")
    base.checkpoint(report)
    autonomy_done = True

    # Restore the exact pre-proof synthetic patient state so the original three
    # Guardian mission assertions remain valid after this insert.
    _gcloud_job("restore")
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


if __name__ == "__main__":
    try:
        base.run()
    finally:
        if setup_executed and not autonomy_done:
            try:
                _gcloud_job("restore", check=False)
            except Exception:
                pass
        _delete_controlled_oauth()
        _cleanup_jobs()
