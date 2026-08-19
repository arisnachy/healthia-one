from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright

from cloud_browser_judge_proof import wait_for_dynamic_or_orientation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "guardian-director-cut"
REPORT = OUT / "recording-report.json"
DURATIONS = OUT / "audio" / "scene-durations.json"
VIDEO_DIR = OUT / "video"

JUDGE_URL = os.environ.get("HEALTHIA_MAINLINE_JUDGE_URL", "").rstrip("/")
GUARDIAN_URL = os.environ.get("HEALTHIA_GUARDIAN_DEMO_URL", "").rstrip("/")
PRODUCT_URL = os.environ.get("HEALTHIA_GUARDIAN_PRODUCT_URL", "").rstrip("/")
JUDGE_TOKEN_FILE = os.environ.get("HEALTHIA_MAINLINE_JUDGE_TOKEN_FILE", "")
GUARDIAN_TOKEN_FILE = os.environ.get("HEALTHIA_GUARDIAN_DEMO_TOKEN_FILE", "")
PRODUCT_TOKEN_FILE = os.environ.get("HEALTHIA_GUARDIAN_PRODUCT_TOKEN_FILE", "")
CANDIDATE_SHA = os.environ.get("HEALTHIA_GUARDIAN_SOURCE_SHA", "")


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def token(path_value: str) -> str:
    require(bool(path_value), "token file missing")
    value = Path(path_value).read_text(encoding="utf-8").strip()
    require(bool(value), "token file empty")
    return value


def checkpoint(report: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")


def scene_map() -> dict[str, float]:
    payload = json.loads(DURATIONS.read_text(encoding="utf-8"))
    return {item["id"]: float(item["duration"]) for item in payload["scenes"]}


def hold(page: Page, seconds: float) -> None:
    page.wait_for_timeout(max(1000, int(seconds * 1000)))


def set_auth(page: Page, auth_token: str) -> None:
    page.set_extra_http_headers({"Authorization": f"Bearer {auth_token}"})


def visible_state(page: Page) -> dict:
    return page.evaluate("fetch('/api/state',{cache:'no-store'}).then(r=>r.json())")


def click_and_wait(page: Page, label: str) -> dict:
    page.get_by_role("button", name=label, exact=True).click()
    page.wait_for_timeout(700)
    return visible_state(page)


def register_live_patient(page: Page) -> None:
    suffix = uuid4().hex[:10]
    email = f"guardian-film-{suffix}@example.test"
    password = f"GuardianFilm!{suffix}Aa9"
    page.goto(f"{PRODUCT_URL}/login", wait_until="networkidle", timeout=60_000)
    page.locator("#registerTab").click()
    page.locator('#registerForm input[name="display_name"]').fill("Guardian Film Patient")
    page.locator('#registerForm input[name="email"]').fill(email)
    page.locator('#registerForm input[name="password"]').fill(password)
    page.locator('#registerForm button[type="submit"]').click()
    page.wait_for_url(f"{PRODUCT_URL}/", timeout=30_000)
    page.wait_for_load_state("networkidle")


def main() -> None:
    require(JUDGE_URL.startswith("https://") and ".run.app" in JUDGE_URL, "mainline Judge Mode URL required")
    require(GUARDIAN_URL.startswith("https://") and ".run.app" in GUARDIAN_URL, "Guardian demo URL required")
    require(PRODUCT_URL.startswith("https://") and ".run.app" in PRODUCT_URL, "Guardian product URL required")
    require(DURATIONS.exists(), "scene durations missing")
    durations = scene_map()
    judge_token = token(JUDGE_TOKEN_FILE)
    guardian_token = token(GUARDIAN_TOKEN_FILE)
    product_token = token(PRODUCT_TOKEN_FILE)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "status": "running",
        "synthetic_only": True,
        "new_recording": True,
        "recycled_video_footage": False,
        "guardian_source_sha": CANDIDATE_SHA,
        "checks": [],
        "scenes": [],
    }
    checkpoint(report)
    started = time.monotonic()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1600, "height": 900},
        )
        page = context.new_page()
        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # Scene 1 — promoted no-prompt Cloud/Gmail continuity proof.
        set_auth(page, judge_token)
        page.goto(JUDGE_URL, wait_until="networkidle", timeout=60_000)
        require("Your health never starts over" in page.locator("body").inner_text(), "mainline Judge Mode not visible")
        report["checks"].append("promoted_mainline_no_prompt_gmail_proof_visible")
        report["scenes"].append("mainline")
        hold(page, durations["mainline"] * 0.55)
        page.locator(".grid").scroll_into_view_if_needed()
        hold(page, durations["mainline"] * 0.45)

        # Scene 2 — separate research build, clearly labeled.
        set_auth(page, guardian_token)
        page.goto(GUARDIAN_URL, wait_until="networkidle", timeout=60_000)
        require("GUARDIAN RESEARCH BUILD" in page.locator("body").inner_text(), "research-build label missing")
        click_and_wait(page, "Reset Twin")
        state = visible_state(page)
        require(state["chat_prompts_used"] == 0 and state["treatment"][0]["name"].lower() == "losartan", "synthetic Twin not armed")
        report["checks"].append("guardian_research_build_truth_boundary_visible")
        report["scenes"].append("twin")
        hold(page, durations["twin"])

        # Scene 3 — treatment-aware evidence gap from real Result Guardian code.
        state = click_and_wait(page, "Renal result")
        result_missions = [m for m in state["missions"] if m["type"].startswith("result_guardian")]
        require(len(result_missions) == 1 and result_missions[0]["status"] == "waiting_patient", "Result Guardian did not open mission")
        require(state["notifications"] and state["notifications"][-1]["delivery_mode"] == "eligible_auto_send", "Guardian email plan not eligible under standing consent")
        require(state["chat_prompts_used"] == 0, "Guardian sequence used chat")
        report["checks"].extend(["result_guardian_treatment_aware_gap_opened", "guardian_patient_email_plan_eligible_auto_send"])
        report["scenes"].append("result_gap")
        hold(page, durations["result_gap"])

        # Scene 4 — evidence closes same treatment mission.
        state = click_and_wait(page, "Potassium arrives")
        mission = [m for m in state["missions"] if m["type"].startswith("result_guardian")][0]
        require(mission["status"] == "completed" and mission["closure_evidence"], "Result Guardian did not close from evidence")
        report["checks"].append("result_guardian_same_mission_closed_from_evidence")
        report["scenes"].append("result_close")
        hold(page, durations["result_close"])

        # Scene 5 — appointment preparation audit.
        state = click_and_wait(page, "Upcoming visit")
        appt = [m for m in state["missions"] if m["type"] == "appointment_guardian_preparation"][0]
        require(appt["status"] == "waiting_patient" and "Insurance" in appt["next_action"], "Appointment Guardian did not isolate missing insurance")
        report["checks"].append("appointment_guardian_verified_existing_twin_and_opened_missing_evidence")
        report["scenes"].append("appointment_gap")
        hold(page, durations["appointment_gap"])

        # Scene 6 — appointment preparation closes from document evidence.
        state = click_and_wait(page, "Insurance arrives")
        appt = [m for m in state["missions"] if m["type"] == "appointment_guardian_preparation"][0]
        require(appt["status"] == "completed" and appt["closure_evidence"], "Appointment Guardian did not close")
        report["checks"].append("appointment_guardian_closed_from_insurance_evidence")
        report["scenes"].append("appointment_close")
        hold(page, durations["appointment_close"])

        # Scene 7 — post-visit gap without invented content.
        state = click_and_wait(page, "Visit completed")
        post = [m for m in state["missions"] if m["type"] == "postvisit_guardian_summary_capture"][0]
        require(post["status"] == "waiting_patient", "Post-Visit Guardian did not open")
        report["checks"].append("postvisit_guardian_opened_missing_outcome_mission")
        report["scenes"].append("postvisit_gap")
        hold(page, durations["postvisit_gap"])

        # Scene 8 — post-visit mission closes from consultation note.
        state = click_and_wait(page, "Consult note arrives")
        post = [m for m in state["missions"] if m["type"] == "postvisit_guardian_summary_capture"][0]
        require(post["status"] == "completed" and post["closure_evidence"], "Post-Visit Guardian did not close")
        require(state["chat_prompts_used"] == 0, "autonomous Guardian scenes used chat prompts")
        report["checks"].extend(["postvisit_guardian_closed_from_note_evidence", "three_guardian_sequences_zero_chat_prompts"])
        report["scenes"].append("postvisit_close")
        hold(page, durations["postvisit_close"])

        # Scene 9 — live Gemini + ADK adaptive clinical interaction in the same research build product.
        set_auth(page, product_token)
        register_live_patient(page)
        readiness = page.evaluate("fetch('/api/readiness',{cache:'no-store'}).then(r=>r.json())")
        require(readiness.get("model") == "gemini-3.5-flash" and readiness.get("adk_ready") is True, "live Gemini/ADK readiness failed")
        page.locator("#chatInput").fill("Since yesterday I have burning pain when I urinate and I need to go very often. Help me understand what information is still missing.")
        page.locator("#sendButton").click()
        _, status = wait_for_dynamic_or_orientation(page)
        require(status == "dynamic_clinical_questions", f"adaptive Gemini interview not visible: {status}")
        page.wait_for_selector('.clinical-question-block[data-question-source="gemini_dynamic"]', timeout=20_000)
        require(page.locator('.clinical-question-block[data-question-source="gemini_dynamic"] .clinical-question').count() == 5, "dynamic five-question block missing")
        report["checks"].append("live_gemini_35_flash_adk_adaptive_clinical_interview")
        report["scenes"].append("clinical_ai")
        hold(page, durations["clinical_ai"])

        # Scene 10 — published ONE SAFETY proof, shown on the research surface as frozen-main evidence.
        set_auth(page, guardian_token)
        page.goto(GUARDIAN_URL, wait_until="networkidle", timeout=60_000)
        page.locator(".proof").scroll_into_view_if_needed()
        body = page.locator(".proof").inner_text()
        require("HealthActionTicket" in body and "receipt_95ba26286e6f4e15" in body, "ONE SAFETY proof not visible")
        report["checks"].append("frozen_main_one_safety_trace_ticket_receipt_visible")
        report["scenes"].append("safety")
        hold(page, durations["safety"])

        # Scene 11 — close on the product thesis and truth boundary.
        page.locator(".top").scroll_into_view_if_needed()
        report["scenes"].append("close")
        hold(page, durations["close"])

        # We tolerate browser console noise only if it is not an uncaught page error;
        # the film gate records both for audit rather than silently hiding them.
        report["page_errors"] = page_errors
        report["console_errors"] = console_errors[-20:]
        require(not page_errors, f"page errors during recording: {page_errors}")
        report["checks"].append("zero_browser_page_errors")
        report["status"] = "PASS"
        report["raw_elapsed_seconds"] = round(time.monotonic() - started, 3)
        checkpoint(report)
        context.close()
        browser.close()

    videos = sorted(VIDEO_DIR.glob("*.webm"))
    require(bool(videos), "Playwright video missing")
    report["video_file"] = str(videos[0].relative_to(ROOT))
    report["video_sha256"] = hashlib.sha256(videos[0].read_bytes()).hexdigest()
    checkpoint(report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        failure = {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)}
        if REPORT.exists():
            try:
                failure.update(json.loads(REPORT.read_text(encoding="utf-8")))
                failure["status"] = "FAIL"
                failure["error_type"] = type(exc).__name__
                failure["error"] = str(exc)
            except Exception:
                pass
        checkpoint(failure)
        raise
