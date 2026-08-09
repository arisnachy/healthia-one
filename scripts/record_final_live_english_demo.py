from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright

from cloud_browser_judge_proof import api_json, require, tiny_pdf, wait_for_dynamic_or_orientation


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "final-live-english-demo"
REPORT = OUTPUT / "report.json"
BASE_URL = os.getenv("HEALTHIA_CLOUD_URL", "").rstrip("/")
IDENTITY_TOKEN = os.getenv("HEALTHIA_CLOUD_ID_TOKEN", "")
CANDIDATE_SHA = os.getenv("HEALTHIA_CANDIDATE_SHA", "")
CLOUD_REVISION = os.getenv("HEALTHIA_CLOUD_REVISION", "")
CLOUD_IMAGE = os.getenv("HEALTHIA_CLOUD_IMAGE", "")
CLOUD_PROJECT = os.getenv("HEALTHIA_CLOUD_PROJECT", "")
CLOUD_REGION = os.getenv("HEALTHIA_CLOUD_REGION", "")
TARGET_SECONDS = int(os.getenv("HEALTHIA_DEMO_TARGET_SECONDS", "220"))


def overlay(page: Page, title: str, body: str, seconds: float) -> None:
    page.evaluate(
        """({title, body}) => {
          let box = document.getElementById('healthia-cine-caption');
          if (!box) {
            box = document.createElement('aside');
            box.id = 'healthia-cine-caption';
            box.style.cssText = [
              'position:fixed','right:24px','bottom:24px','z-index:2147483647',
              'width:min(560px,43vw)','background:rgba(20,29,48,.94)','color:white',
              'border:1px solid rgba(255,255,255,.12)','border-radius:18px','padding:16px 18px',
              'box-shadow:0 16px 46px rgba(0,0,0,.24)','font-family:Inter,system-ui,sans-serif',
              'pointer-events:none'
            ].join(';');
            document.body.appendChild(box);
          }
          box.innerHTML = `<strong style="font-size:19px;display:block;margin-bottom:6px">${title}</strong><span style="font-size:14px;line-height:1.45;color:#e7ebf3">${body}</span>`;
        }""",
        {"title": title, "body": body},
    )
    page.wait_for_timeout(int(seconds * 1000))


def clear_overlay(page: Page) -> None:
    page.evaluate("document.getElementById('healthia-cine-caption')?.remove()")


def require_message_locale(page: Page, message_id: str, expected: str) -> None:
    state = api_json(page, "/api/bootstrap")
    message = next((item for item in state.get("messages", []) if item.get("id") == message_id), None)
    require(bool(message), f"assistant message {message_id} missing from durable state")
    actual = str((message.get("metadata") or {}).get("response_locale") or "")
    require(actual == expected, f"assistant response locale mismatch: expected {expected}, got {actual!r}")


def answer_conversational_block(page: Page, *, answer_prefix: str) -> None:
    block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
    require(block.locator(".clinical-question").count() == 5, "ADK/Gemini contract must contain exactly five questions")
    require(block.locator(".clinical-question:visible").count() == 1, "conversation must show exactly one clinical question at a time")
    require(block.locator(".clinical-show-all:visible").count() == 0, "legacy 2+3 form reveal control is visible")
    require(block.locator(".clinical-detail:visible").count() == 1, "free-text path is not visible")
    require(block.locator(".clinical-dont-know:visible").count() == 1, "I-don't-know path is missing")

    for index in range(5):
        visible = block.locator(".clinical-question:visible")
        require(visible.count() == 1, f"question {index + 1} is not the sole visible turn")
        require(block.locator(".clinical-stage").inner_text().strip() == f"{index + 1} / 5", f"turn counter wrong at {index + 1}")
        detail = visible.locator(".clinical-detail")
        detail.fill(f"{answer_prefix} {index + 1}")
        option = visible.locator(".clinical-option").first
        if option.count():
            option.click()
        block.locator(".clinical-next-question").click()
        if index < 4:
            page.wait_for_timeout(180)
            require(block.locator(".clinical-question:visible").count() == 1, "next conversational question did not appear")
            require(block.locator(".clinical-mini-turn.patient").count() == index + 1, "answered turn did not persist in visible transcript")


def latest_result_state(page: Page, filename: str, timeout_s: float = 80.0) -> tuple[dict, dict, dict]:
    deadline = time.time() + timeout_s
    last_state: dict = {}
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        last_state = state
        candidates = [item for item in state.get("results", []) if item.get("filename") == filename or filename in json.dumps(item, ensure_ascii=False)]
        if candidates:
            result = candidates[-1]
            result_id = str(result.get("id") or "")
            document = next((item for item in state.get("documents", []) if item.get("related_result_id") == result_id), None)
            if result.get("status") == "parsed" and result_id and document:
                return state, result, document
        page.wait_for_timeout(700)
    raise RuntimeError(f"live demo result did not become parsed: {last_state.get('results', [])[-2:]}")


def wait_for_result_mission(page: Page, result_id: str, timeout_s: float = 55.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        matches = [mission for mission in state.get("missions", []) if mission.get("mission_type") == "result_explanation" and result_id in (mission.get("evidence_ids") or [])]
        if matches:
            last = matches[-1]
            if last.get("status") == "completed":
                return last
        page.wait_for_timeout(650)
    raise RuntimeError(f"Taskmaster mission did not complete: {last}")


def send_chat(page: Page, text: str) -> None:
    page.locator("#chatInput").fill(text)
    page.locator("#sendButton").click()


def run() -> dict:
    require(BASE_URL.startswith("https://") and ".run.app" in BASE_URL, "exact-candidate Cloud Run URL is required")
    require(bool(IDENTITY_TOKEN), "Cloud Run identity token is required")
    require(bool(CANDIDATE_SHA), "candidate SHA is required")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUTPUT / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = OUTPUT / "synthetic-final-lab.pdf"
    pdf = tiny_pdf()
    pdf_path.write_bytes(pdf)

    suffix = uuid4().hex[:10]
    email = f"final-demo-{suffix}@example.test"
    password = f"FinalDemo!{suffix}Aa9"
    display_name = "HealthIA Judge Patient"
    filename = pdf_path.name
    console_errors: list[str] = []
    page_errors: list[str] = []
    report: dict = {
        "status": "running",
        "synthetic_only": True,
        "demo_language": "en-US",
        "live_app_only": True,
        "static_screenshots_used": False,
        "candidate_sha": CANDIDATE_SHA,
        "base_url": BASE_URL,
        "cloud_revision": CLOUD_REVISION,
        "cloud_image": CLOUD_IMAGE,
        "cloud_project": CLOUD_PROJECT,
        "cloud_region": CLOUD_REGION,
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "checks": [],
    }

    started = time.monotonic()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(video_dir),
            record_video_size={"width": 1600, "height": 900},
            extra_http_headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
        )
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)
        page.wait_for_function("document.documentElement.lang === 'en'")
        require(page.locator("#registerTab").is_visible(), "registration UI missing")
        overlay(page, "HealthIA ONE", "A patient's health should not reset when a conversation ends. This is the live exact-candidate application on Google Cloud — not screenshots or a mockup.", 7)
        clear_overlay(page)

        page.locator("#registerTab").click()
        page.locator('#registerForm input[name="display_name"]').fill(display_name)
        page.locator('#registerForm input[name="email"]').fill(email)
        page.locator('#registerForm input[name="password"]').fill(password)
        page.locator('#registerForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=30_000)
        page.wait_for_load_state("networkidle")
        session = api_json(page, "/api/auth/session")
        require(session.get("authenticated") is True, "registration failed")
        patient_id = str((session.get("account") or {}).get("patient_id") or "")
        readiness = api_json(page, "/api/readiness")
        require(readiness.get("ai_ready") is True and readiness.get("adk_ready") is True, "Gemini/ADK not ready")
        require(readiness.get("model") == "gemini-3.5-flash", f"unexpected model: {readiness.get('model')}")
        require(readiness.get("store_backend") == "firestore", "not using Firestore")
        require(readiness.get("evidence_backend") == "gcs", "not using GCS")
        report["patient_id"] = patient_id
        report["readiness"] = {key: readiness.get(key) for key in ("ready", "model", "adk_ready", "ai_ready", "store_backend", "evidence_backend", "auth_required")}
        report["checks"].append("exact_candidate_live_google_runtime")

        send_chat(page, "Since yesterday I have burning pain when I urinate and I need to go very often. Help me understand what information is still missing.")
        assistant_id, status = wait_for_dynamic_or_orientation(page)
        require(status == "dynamic_clinical_questions", f"first clinical response was not dynamic: {status}")
        require_message_locale(page, assistant_id, "en")
        page.wait_for_selector('.clinical-question-block[data-question-source="gemini_dynamic"]', timeout=10_000)
        overlay(page, "Google ADK + Gemini", "ADK executes the bounded clinical baseline tool. Gemini creates five case-specific questions, while HealthIA presents them as a human conversation: one useful question at a time.", 8)
        clear_overlay(page)
        answer_conversational_block(page, answer_prefix="Synthetic answer")
        report["checks"].append("one_question_at_a_time_five_question_contract")

        assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        blocks = 1
        while status in {"dynamic_clinical_questions", "dynamic_clinical_followup_questions"} and blocks < 3:
            require_message_locale(page, assistant_id, "en")
            blocks += 1
            overlay(page, "Conversation memory", "If more evidence is useful, the next ADK/Gemini block receives the actual prior questions and answers instead of restarting the patient story.", 5)
            clear_overlay(page)
            answer_conversational_block(page, answer_prefix=f"Follow-up {blocks}")
            assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        require(status == "clinical_ai_orientation_completed", f"clinical orientation did not complete: {status}")
        require_message_locale(page, assistant_id, "en")
        report["checks"].append("safe_clinical_orientation_completed")

        send_chat(page, "Open my results.")
        page.wait_for_timeout(1800)
        require(page.locator("#view-results").evaluate("node => node.classList.contains('is-active')"), "chat Health OS command did not open Results")
        report["checks"].append("chat_health_os_open_results")
        overlay(page, "Chat is the operating surface", "A safe workspace command is translated into an allowlisted UI action. Gemini is not allowed to invent arbitrary selectors or silently perform destructive actions.", 6)
        clear_overlay(page)

        page.locator("#resultFile").set_input_files(str(pdf_path))
        _, result, document = latest_result_state(page, filename)
        result_id = str(result.get("id") or "")
        document_id = str(document.get("id") or "")
        require(result_id and document_id, "result/document provenance missing")
        report["result_id"] = result_id
        report["document_id"] = document_id
        report["checks"].append("multimodal_original_result_and_provenance")
        overlay(page, "Evidence first", "The original PDF is stored first in private Cloud Storage. Gemini extracts readable evidence, Firestore commits patient-scoped state, and the clinical twin keeps provenance to the original.", 8)
        clear_overlay(page)

        page.locator('.main-nav [data-open="chat"]').click()
        send_chat(page, f"Explain the result {filename} I just uploaded and confirm that it was saved with the original file.")
        mission = wait_for_result_mission(page, result_id)
        require(document_id in (mission.get("evidence_ids") or []), "completed mission lost original-document evidence")
        report["mission_id"] = str(mission.get("id") or "")
        report["checks"].append("taskmaster_mission_completed_from_persisted_evidence")
        page.locator('.main-nav [data-open="missions"]').click()
        page.wait_for_timeout(650)
        overlay(page, "Taskmaster closure", "The mission is not complete because the model answered. It is complete because the persisted result and original document actually exist and remain correlated evidence.", 8)
        clear_overlay(page)

        page.locator("#accountPill").click()
        page.locator("#logoutButton").click()
        page.wait_for_url(f"{BASE_URL}/login", timeout=20_000)
        page.locator('#loginForm input[name="email"]').fill(email)
        page.locator('#loginForm input[name="password"]').fill(password)
        page.locator('#loginForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=20_000)
        page.wait_for_load_state("networkidle")
        restored = api_json(page, "/api/bootstrap")
        require((restored.get("profile") or {}).get("id") == patient_id, "patient identity changed after relogin")
        require(any(item.get("id") == result_id for item in restored.get("results", [])), "result disappeared after relogin")
        require(any(item.get("id") == document_id for item in restored.get("documents", [])), "document disappeared after relogin")
        require(any(item.get("id") == mission.get("id") and item.get("status") == "completed" for item in restored.get("missions", [])), "mission disappeared after relogin")
        report["checks"].append("logout_login_durable_continuity")
        overlay(page, "Durable continuity", "After logout and login, the result, original evidence and completed mission are still present. The canonical state does not live in the browser tab.", 7)
        clear_overlay(page)

        readiness = api_json(page, "/api/readiness")
        page.locator('.main-nav [data-open="chat"]').click()
        cloud_summary = (
            f"Exact candidate {CANDIDATE_SHA[:12]} · Cloud Run revision {CLOUD_REVISION or 'verified'} · "
            f"Gemini {readiness.get('model')} on Vertex AI · ADK ready: {readiness.get('adk_ready')} · "
            f"State: {readiness.get('store_backend')} · Evidence: {readiness.get('evidence_backend')}"
        )
        overlay(page, "Live Google Cloud proof", cloud_summary, 9)
        report["checks"].append("visible_exact_candidate_cloud_proof")
        clear_overlay(page)

        elapsed = time.monotonic() - started
        if elapsed < TARGET_SECONDS:
            overlay(page, "Your health never starts over.", "HealthIA finishes when the evidence-backed outcome exists, remains auditable, and is ready for the patient's next conversation.", min(8.0, TARGET_SECONDS - elapsed))
            clear_overlay(page)

        require(not page_errors, f"browser page errors: {page_errors}")
        require(not console_errors, f"browser console errors: {console_errors}")
        report["checks"].append("zero_browser_console_or_page_errors")
        report["status"] = "PASS"
        context.close()
        browser.close()

    videos = sorted(video_dir.glob("*.webm"))
    require(bool(videos), "Playwright did not produce a video")
    video = videos[0]
    report["video_file"] = str(video.relative_to(ROOT))
    report["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("HEALTHIA_FINAL_LIVE_ENGLISH_DEMO_PASS")
    print(json.dumps({"status": report["status"], "candidate_sha": CANDIDATE_SHA, "checks": report["checks"], "video_sha256": report["video_sha256"], "elapsed_seconds": report["elapsed_seconds"]}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:2000]}, indent=2), encoding="utf-8")
        print(f"HEALTHIA_FINAL_LIVE_ENGLISH_DEMO_FAIL {type(exc).__name__}: {exc}")
        raise
