from __future__ import annotations

import json
import os
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_URL = os.environ.get("HEALTHIA_CLOUD_URL", "").rstrip("/")
IDENTITY_TOKEN = os.environ.get("HEALTHIA_CLOUD_ID_TOKEN", "")
EMAIL = os.environ.get("HEALTHIA_WAVE14_RECORDER_EMAIL", "")
PASSWORD = os.environ.get("HEALTHIA_WAVE14_RECORDER_PASSWORD", "")
PATIENT_ID = os.environ.get("HEALTHIA_WAVE14_PROOF_PATIENT_ID", "")
OUTPUT = Path("dist/wave14-autonomous-live-recorder")
VIDEO_DIR = OUTPUT / "video"
READY = OUTPUT / "browser-ready"
MISSION_VISIBLE = OUTPUT / "mission-visible"
REPORT = OUTPUT / "recorder-report.json"
MISSION_TYPE = "bp_followup_guardian_measurement"
# Cloud Run Jobs can spend several minutes provisioning before user code starts.
# These are recorder synchronization bounds, not product timing claims.
MISSION_WAIT_SECONDS = 480
COMPLETION_WAIT_SECONDS = 900


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def checkpoint(report: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def bootstrap(page: Page) -> dict:
    return page.evaluate(
        """async () => {
          const response = await fetch('/api/bootstrap', {cache:'no-store'});
          if (!response.ok) throw new Error(`bootstrap ${response.status}`);
          return await response.json();
        }"""
    )


def bp_mission(state: dict) -> dict | None:
    for mission in state.get("missions") or []:
        if str(mission.get("mission_type") or "") == MISSION_TYPE:
            return mission
    return None


def click_view(page: Page, view: str) -> None:
    button = page.locator(f'[data-open="{view}"]').first
    require(button.count() == 1, f"HealthIA navigation button missing: {view}")
    button.click()
    page.wait_for_timeout(350)


def reload_view(page: Page, view: str) -> None:
    page.reload(wait_until="networkidle", timeout=60_000)
    page.wait_for_selector("#app", timeout=30_000)
    click_view(page, view)


def main() -> None:
    require(BASE_URL.startswith("https://") and ".run.app" in BASE_URL, "private Cloud Run app URL required")
    require(bool(IDENTITY_TOKEN), "Cloud Run identity token required")
    require(bool(EMAIL and PASSWORD and PATIENT_ID.startswith("patient_")), "recorder credentials/patient id required")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    for marker in (READY, MISSION_VISIBLE):
        marker.unlink(missing_ok=True)

    report: dict = {
        "status": "running",
        "live_app_only": True,
        "static_screenshots_used": False,
        "synthetic_patient": True,
        "no_chat_prompt_used": True,
        "patient_id": PATIENT_ID,
        "checks": [],
        "timeline": {},
        "recorder_sync_bounds": {
            "mission_wait_seconds": MISSION_WAIT_SECONDS,
            "completion_wait_seconds": COMPLETION_WAIT_SECONDS,
        },
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
            extra_http_headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
        )
        page = context.new_page()
        console_errors: list[str] = []
        page_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)
        page.locator('#loginForm input[name="email"]').fill(EMAIL)
        page.locator('#loginForm input[name="password"]').fill(PASSWORD)
        page.locator('#loginForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=30_000)
        page.wait_for_load_state("networkidle")
        session = page.evaluate("fetch('/api/auth/session',{cache:'no-store'}).then(r=>r.json())")
        require(session.get("authenticated") is True, "recorder login did not establish a patient session")
        require(str((session.get("account") or {}).get("patient_id") or "") == PATIENT_ID, "recorder account is not bound to proof patient")

        click_view(page, "missions")
        initial = bootstrap(page)
        require(bp_mission(initial) is None, "BP mission already exists before autonomous activation")
        require(page.locator("#chatInput").input_value() == "", "chat composer is not empty")
        report["checks"].append("idle_healthia_before_autonomous_activation")
        report["timeline"]["browser_ready_s"] = round(time.monotonic() - started, 3)
        checkpoint(report)
        page.wait_for_timeout(2200)
        READY.write_text("ready\n", encoding="utf-8")

        # The external workflow starts the real Cloud Run activation only after
        # browser-ready. Provisioning can itself take >120 s, so the camera must
        # remain patient rather than timing out before HealthIA actually runs.
        deadline = time.monotonic() + MISSION_WAIT_SECONDS
        mission = None
        while time.monotonic() < deadline:
            current = bootstrap(page)
            mission = bp_mission(current)
            if mission is not None:
                break
            page.wait_for_timeout(450)
        require(mission is not None, "autonomous BP mission did not appear within recorder synchronization bound")
        require(str(mission.get("status") or "") == "waiting_patient", f"mission did not open WAITING_PATIENT: {mission}")
        report["mission_id"] = str(mission.get("id") or "")
        report["timeline"]["mission_created_s"] = round(time.monotonic() - started, 3)
        report["checks"].append("mission_created_without_chat_prompt")
        reload_view(page, "missions")
        page.wait_for_function(
            """() => [...document.querySelectorAll('#missionList .data-card')].some(card => /Complete blood-pressure follow-up/i.test(card.innerText) && /waiting_patient/i.test(card.innerText))""",
            timeout=30_000,
        )
        page.wait_for_timeout(2800)
        MISSION_VISIBLE.write_text("visible\n", encoding="utf-8")
        checkpoint(report)

        # Hold the real product on the open mission while Eventarc -> Gmail ->
        # Gmail watch/PubSub completes outside the browser. No chat message or
        # manual measurement is sent by this recorder. The longer bound covers
        # sequential Cloud Run cold starts; it does not alter the live chain.
        deadline = time.monotonic() + COMPLETION_WAIT_SECONDS
        final_state = None
        final_mission = None
        gmail_vital = None
        while time.monotonic() < deadline:
            current = bootstrap(page)
            candidate = bp_mission(current)
            if candidate is not None and str(candidate.get("status") or "") == "completed":
                vitals = [
                    item for item in (current.get("vitals") or [])
                    if str(((item.get("source") or {}).get("source_type")) or "") == "patient_email_reply"
                    and item.get("systolic") == 128 and item.get("diastolic") == 80
                ]
                if len(vitals) == 1:
                    final_state, final_mission, gmail_vital = current, candidate, vitals[0]
                    break
            page.wait_for_timeout(700)
        require(final_state is not None and final_mission is not None and gmail_vital is not None, "browser never observed the real Gmail-derived mission resolution within recorder synchronization bound")
        require(str(final_mission.get("id") or "") == report["mission_id"], "a different mission was completed")
        report["timeline"]["mission_completed_s"] = round(time.monotonic() - started, 3)
        report["checks"].extend([
            "same_mission_completed_from_external_email_reply",
            "gmail_reply_persisted_as_canonical_vital",
        ])

        reload_view(page, "missions")
        page.wait_for_function(
            """() => [...document.querySelectorAll('#missionList .data-card')].some(card => /Complete blood-pressure follow-up/i.test(card.innerText) && /completed/i.test(card.innerText))""",
            timeout=30_000,
        )
        page.wait_for_timeout(2600)
        click_view(page, "measurements")
        page.wait_for_function(
            """() => [...document.querySelectorAll('#measurementList .data-card')].some(card => /128\\/80/.test(card.innerText))""",
            timeout=30_000,
        )
        page.wait_for_timeout(3200)

        # End on the mission itself so the before/after state is unmistakable.
        click_view(page, "missions")
        page.wait_for_timeout(2200)
        report["checks"].append("completed_state_visible_in_real_product_ui")
        report["console_errors"] = console_errors
        report["page_errors"] = page_errors
        require(not console_errors and not page_errors, f"browser errors during recorder: console={console_errors}, page={page_errors}")
        report["checks"].append("zero_browser_console_or_page_errors")
        report["status"] = "PASS"
        report["duration_s"] = round(time.monotonic() - started, 3)
        checkpoint(report)
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
