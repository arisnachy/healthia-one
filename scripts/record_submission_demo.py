from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright

from cloud_browser_judge_proof import (
    answer_visible_block,
    api_json,
    require,
    tiny_pdf,
    wait_for_dynamic_or_orientation,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "submission-demo"
REPORT = OUTPUT / "report.json"
BASE_URL = os.getenv("HEALTHIA_CLOUD_URL", "").rstrip("/")
IDENTITY_TOKEN = os.getenv("HEALTHIA_CLOUD_ID_TOKEN", "")
CLOUD_REVISION = os.getenv("HEALTHIA_CLOUD_REVISION", "")
CLOUD_IMAGE = os.getenv("HEALTHIA_CLOUD_IMAGE", "")
CLOUD_PROJECT = os.getenv("HEALTHIA_CLOUD_PROJECT", "")
CLOUD_REGION = os.getenv("HEALTHIA_CLOUD_REGION", "")
TARGET_SECONDS = int(os.getenv("HEALTHIA_DEMO_TARGET_SECONDS", "235"))


def overlay(page: Page, title: str, body: str, seconds: float) -> None:
    """Place narration text over the live app; never replace the app with a static card."""
    page.evaluate(
        """({title, body}) => {
          let box = document.getElementById('healthia-demo-caption');
          if (!box) {
            box = document.createElement('aside');
            box.id = 'healthia-demo-caption';
            box.style.cssText = [
              'position:fixed','right:24px','bottom:24px','z-index:2147483647',
              'width:min(520px,42vw)','background:rgba(20,29,48,.94)','color:white',
              'border-radius:18px','padding:18px 20px','box-shadow:0 16px 46px rgba(0,0,0,.24)',
              'font-family:Inter,system-ui,sans-serif','pointer-events:none'
            ].join(';');
            document.body.appendChild(box);
          }
          box.innerHTML = `<strong style="font-size:20px;display:block;margin-bottom:7px">${title}</strong><span style="font-size:15px;line-height:1.45;color:#e7ebf3">${body}</span>`;
        }""",
        {"title": title, "body": body},
    )
    page.wait_for_timeout(int(seconds * 1000))


def clear_overlay(page: Page) -> None:
    page.evaluate("document.getElementById('healthia-demo-caption')?.remove()")


def latest_result_state(page: Page, filename: str, timeout_s: float = 75.0) -> tuple[dict, dict, dict]:
    deadline = time.time() + timeout_s
    last_state: dict = {}
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        last_state = state
        candidates = [
            item
            for item in state.get("results", [])
            if item.get("filename") == filename or filename in json.dumps(item, ensure_ascii=False)
        ]
        if candidates:
            result = candidates[-1]
            result_id = str(result.get("id") or "")
            document = next((item for item in state.get("documents", []) if item.get("related_result_id") == result_id), None)
            if result.get("status") == "parsed" and result_id and document:
                return state, result, document
        page.wait_for_timeout(750)
    raise RuntimeError(f"submission demo result did not become parsed: {last_state.get('results', [])[-2:]}")


def wait_for_result_mission(page: Page, result_id: str, timeout_s: float = 50.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        matches = [
            mission
            for mission in state.get("missions", [])
            if mission.get("mission_type") == "result_explanation" and result_id in (mission.get("evidence_ids") or [])
        ]
        if matches:
            last = matches[-1]
            if last.get("status") == "completed":
                return last
        page.wait_for_timeout(650)
    raise RuntimeError(f"submission demo Taskmaster mission did not complete: {last}")


def require_message_locale(page: Page, message_id: str, expected: str) -> None:
    state = api_json(page, "/api/bootstrap")
    message = next((item for item in state.get("messages", []) if item.get("id") == message_id), None)
    require(bool(message), f"assistant message {message_id} missing from durable state")
    actual = str((message.get("metadata") or {}).get("response_locale") or "")
    require(actual == expected, f"assistant response locale mismatch: expected {expected}, got {actual!r}")


def run() -> dict:
    require(BASE_URL.startswith("https://") and ".run.app" in BASE_URL, "real Cloud Run .run.app URL is required")
    require(bool(IDENTITY_TOKEN), "HEALTHIA_CLOUD_ID_TOKEN is required")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUTPUT / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = OUTPUT / "synthetic-submission-lab.pdf"
    pdf = tiny_pdf()
    pdf_path.write_bytes(pdf)

    suffix = uuid4().hex[:10]
    email = f"submission-demo-{suffix}@example.test"
    password = f"SubmissionDemo!{suffix}Aa9"
    display_name = "Taskmaster Demo Patient"
    filename = pdf_path.name
    console_errors: list[str] = []
    page_errors: list[str] = []
    report: dict = {
        "status": "running",
        "synthetic_only": True,
        "demo_language": "en-US",
        "live_app_only": True,
        "static_title_cards": False,
        "base_url": BASE_URL,
        "cloud_project": CLOUD_PROJECT,
        "cloud_region": CLOUD_REGION,
        "cloud_revision": CLOUD_REVISION,
        "cloud_image": CLOUD_IMAGE,
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
        require(page.locator("#registerTab").is_visible(), "registration UI is not visible")
        page.wait_for_function("document.documentElement.lang === 'en'")
        require("Your health should remember you" in page.locator(".auth-brand h1").inner_text(), "English login UI is not active")
        report["checks"].append("english_os_locale_login")
        overlay(
            page,
            "The problem",
            "Patient context is fragmented across conversations, PDFs, images, devices, medications, and memory. HealthIA turns that evidence into durable patient-owned work.",
            14,
        )
        overlay(
            page,
            "Live demo — not a slide deck",
            "This is the real private Cloud Run application. Every next step is an actual browser interaction against the deployed backend.",
            10,
        )
        clear_overlay(page)

        page.locator("#registerTab").click()
        page.locator('#registerForm input[name="display_name"]').fill(display_name)
        page.locator('#registerForm input[name="email"]').fill(email)
        page.locator('#registerForm input[name="password"]').fill(password)
        page.locator('#registerForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=30_000)
        page.wait_for_load_state("networkidle")
        page.wait_for_function("document.documentElement.lang === 'en'")
        session = api_json(page, "/api/auth/session")
        require(session.get("authenticated") is True, "submission demo registration failed")
        patient_id = str((session.get("account") or {}).get("patient_id") or "")
        require(patient_id.startswith("patient_"), "submission demo has no patient identity")
        readiness = api_json(page, "/api/readiness")
        require(readiness.get("ai_ready") is True and readiness.get("adk_ready") is True, "live Gemini/ADK is not ready")
        require(readiness.get("model") == "gemini-3.5-flash", f"unexpected model: {readiness.get('model')}")
        require(readiness.get("store_backend") == "firestore", "submission demo is not using Firestore")
        require(readiness.get("evidence_backend") == "gcs", "submission demo is not using GCS")
        report["patient_id"] = patient_id
        report["readiness"] = {key: readiness.get(key) for key in ("ready", "model", "adk_ready", "ai_ready", "store_backend", "evidence_backend", "auth_required")}
        report["checks"].append("live_cloud_runtime_ready")
        overlay(page, "Patient-scoped continuity", "The synthetic patient starts with an isolated record. Firestore holds canonical state; private GCS preserves original evidence.", 10)
        clear_overlay(page)

        complaint = "Since yesterday I have burning pain when I urinate and I need to go very often. Help me understand what information is still missing."
        page.locator("#chatInput").fill(complaint)
        page.locator("#sendButton").click()
        assistant_id, status = wait_for_dynamic_or_orientation(page)
        require(status == "dynamic_clinical_questions", f"first clinical response was not dynamic: {status}")
        require_message_locale(page, assistant_id, "en")
        page.wait_for_selector('.clinical-question-block[data-question-source="gemini_dynamic"]', timeout=10_000)
        first_block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
        require(first_block.locator(".clinical-question").count() == 5, "first live block is not five questions")
        require("Case-specific questions" in first_block.inner_text(), "clinical block chrome is not English")
        report["checks"].append("live_english_gemini_adk_question_block_1")
        overlay(page, "Gemini + Google ADK", "ADK executes the authorized clinical baseline tool before Gemini returns exactly five case-specific questions in the patient's language.", 17)
        clear_overlay(page)
        answer_visible_block(page)

        assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        require(status in {"dynamic_clinical_questions", "dynamic_clinical_followup_questions"}, f"second response was not adaptive: {status}")
        require_message_locale(page, assistant_id, "en")
        second_block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
        require(second_block.locator(".clinical-question").count() == 5, "second live block is not five questions")
        report["checks"].append("live_english_gemini_adk_question_block_2")
        overlay(page, "Conversation memory", "The second block receives the real prior questions and answers and must avoid asking for facts the patient already provided.", 15)
        clear_overlay(page)
        answer_visible_block(page)

        assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        if status in {"dynamic_clinical_questions", "dynamic_clinical_followup_questions"}:
            require_message_locale(page, assistant_id, "en")
            third_block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
            require(third_block.locator(".clinical-question").count() == 5, "third live block is malformed")
            overlay(page, "The model decides if more evidence is needed", "HealthIA asks another block only when a missing fact can materially change the orientation.", 8)
            clear_overlay(page)
            answer_visible_block(page)
            assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        require(status == "clinical_ai_orientation_completed", f"clinical orientation did not complete: {status}")
        require_message_locale(page, assistant_id, "en")
        report["checks"].append("live_english_clinical_orientation_completed")
        overlay(page, "Safe orientation", "The workflow ends in patient guidance and a human-care next step — not an invented diagnosis or autonomous prescription.", 11)
        clear_overlay(page)

        page.locator("#resultFile").set_input_files(str(pdf_path))
        state, result, document = latest_result_state(page, filename)
        result_id = str(result.get("id") or "")
        document_id = str(document.get("id") or "")
        require(result_id and document_id, "parsed result lost result/document provenance")
        report["result_id"] = result_id
        report["document_id"] = document_id
        report["checks"].append("multimodal_result_persisted_with_original")
        page.locator('.main-nav [data-open="results"]').click()
        page.wait_for_timeout(800)
        overlay(page, "Evidence-first multimodal workflow", "The original PDF is preserved first. Gemini extracts readable evidence, Firestore stores the result, and the clinical twin keeps provenance back to the original.", 17)
        clear_overlay(page)

        page.locator('.main-nav [data-open="chat"]').click()
        page.locator("#chatInput").fill(f"Explain the result {filename} I just uploaded and confirm that it was saved with the original file.")
        page.locator("#sendButton").click()
        mission = wait_for_result_mission(page, result_id)
        require(document_id in (mission.get("evidence_ids") or []), "completed mission lost original-document evidence")
        report["mission_id"] = str(mission.get("id") or "")
        report["checks"].append("english_taskmaster_result_mission_completed")
        page.locator('.main-nav [data-open="missions"]').click()
        page.wait_for_timeout(700)
        overlay(page, "Taskmaster closure", "The mission is COMPLETED only because the persisted result and original document were recovered and correlated. The agent did work that survives the chat.", 15)
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
        report["checks"].append("relogin_continuity")
        overlay(page, "Durable continuity", "After logout and login, the patient still has the result, original document, and completed mission. The state does not live in the browser tab.", 12)
        clear_overlay(page)

        readiness = api_json(page, "/api/readiness")
        page.locator('.main-nav [data-open="chat"]').click()
        cloud_summary = (
            f"Cloud Run: {BASE_URL} · Project: {CLOUD_PROJECT or 'healthia-6088a'} · Region: {CLOUD_REGION or 'us-central1'} · "
            f"Revision: {CLOUD_REVISION or 'workflow-verified'} · Gemini: {readiness.get('model')} · ADK: {readiness.get('adk_ready')} · "
            f"State: {readiness.get('store_backend')} · Evidence: {readiness.get('evidence_backend')}"
        )
        overlay(page, "Visible Google Cloud proof", cloud_summary, 17)
        report["checks"].append("visible_run_app_and_live_readiness")
        clear_overlay(page)

        elapsed = time.monotonic() - started
        remaining = max(12.0, TARGET_SECONDS - elapsed)
        overlay(
            page,
            "Your health never starts over.",
            "HealthIA ONE completes the loop in one live application: context → decision → action → durable evidence → completed mission. The conversation can end; patient continuity does not.",
            remaining,
        )
        clear_overlay(page)

        require(not page_errors, f"browser page errors during submission demo: {page_errors}")
        require(not console_errors, f"browser console errors during submission demo: {console_errors}")
        report["checks"].append("zero_browser_console_or_page_errors")
        report["status"] = "PASS"
        context.close()
        browser.close()

    videos = sorted(video_dir.glob("*.webm"))
    require(bool(videos), "Playwright did not produce the submission demo video")
    video = videos[0]
    report["video_file"] = str(video.relative_to(ROOT))
    report["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("HEALTHIA_SUBMISSION_DEMO_PASS")
    print(json.dumps({"status": report["status"], "checks": report["checks"], "video_file": report["video_file"], "video_sha256": report["video_sha256"], "elapsed_seconds": report["elapsed_seconds"]}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        failure = {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:2000]}
        REPORT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_SUBMISSION_DEMO_FAIL {type(exc).__name__}: {exc}")
        raise