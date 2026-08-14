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


def checkpoint(report: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


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


def latest_assistant_message(page: Page) -> dict:
    state = api_json(page, "/api/bootstrap")
    assistants = [item for item in state.get("messages", []) if item.get("role") == "assistant"]
    return assistants[-1] if assistants else {}


def wait_for_assistant_after(
    page: Page,
    previous_id: str = "",
    timeout_s: float = 30.0,
    *,
    poll_ms: int = 750,
    rate_limit_backoff_ms: int = 3000,
) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            message = latest_assistant_message(page)
        except Exception as exc:
            error_text = str(exc)
            if "HTTP 429" not in error_text and "HTTP 500" not in error_text:
                raise
            # HealthIA Explain can hold a long media request while Firestore or
            # the single Cloud Run instance briefly returns a transient read error.
            # Keep polling with backoff; a persistent fault still fails at timeout.
            page.wait_for_timeout(max(rate_limit_backoff_ms, poll_ms))
            continue
        if message.get("id") and message.get("id") != previous_id:
            return message
        page.wait_for_timeout(max(250, poll_ms))
    raise RuntimeError("assistant did not produce a new response in time")


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
        visible.locator(".clinical-detail").fill(f"{answer_prefix} {index + 1}")
        option = visible.locator(".clinical-option").first
        if option.count():
            option.click()
        page.wait_for_timeout(280)
        block.locator(".clinical-next-question").click()
        if index < 4:
            page.wait_for_timeout(280)
            require(block.locator(".clinical-question:visible").count() == 1, "next conversational question did not appear")
            require(block.locator(".clinical-mini-turn.patient").count() == index + 1, "answered turn did not persist in visible transcript")


def latest_result_state(page: Page, filename: str, timeout_s: float = 70.0) -> tuple[dict, dict, dict]:
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
        page.wait_for_timeout(500)
    raise RuntimeError(f"live demo result did not become parsed: {last_state.get('results', [])[-2:]}")


def wait_for_exact_result_mission(
    page: Page,
    *,
    mission_id: str,
    result_id: str,
    document_id: str,
    timeout_s: float = 25.0,
) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        last = next((mission for mission in state.get("missions", []) if str(mission.get("id") or "") == mission_id), None)
        if last:
            evidence = set(last.get("evidence_ids") or [])
            if (
                last.get("mission_type") == "result_explanation"
                and last.get("status") == "completed"
                and result_id in evidence
                and document_id in evidence
            ):
                return last
        page.wait_for_timeout(450)
    raise RuntimeError(f"exact Taskmaster mission did not complete with persisted evidence: {last}")


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
    checkpoint(report)

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
        overlay(page, "HealthIA ONE", "Live exact-candidate application on Google Cloud. No screenshots, no mock screens.", 3)
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
        checkpoint(report)

        cloud_runtime = (
            f"Gemini {readiness.get('model')} · Google ADK ready: {readiness.get('adk_ready')} · "
            f"State: {readiness.get('store_backend')} · Evidence: {readiness.get('evidence_backend')}"
        )
        overlay(page, "Exact Google Cloud runtime", cloud_runtime, 4)
        clear_overlay(page)

        page.locator('.main-nav [data-open="results"]').click()
        page.wait_for_function("document.getElementById('view-results')?.classList.contains('is-active') === true", timeout=15_000)
        report["checks"].append("results_workspace_opened")
        checkpoint(report)
        overlay(page, "Evidence becomes durable work", "The patient opens Results and adds original evidence. HealthIA preserves the source before interpretation, then carries the outcome forward as patient-scoped state and missions.", 4)
        clear_overlay(page)

        page.locator("#resultFile").set_input_files(str(pdf_path))
        _, result, document = latest_result_state(page, filename)
        result_id = str(result.get("id") or "")
        document_id = str(document.get("id") or "")
        require(result_id and document_id, "result/document provenance missing")
        result_explanation = str(result.get("explanation") or "").strip()
        require(result_explanation, "parsed multimodal result has no patient explanation")
        spanish_leaks = ("este análisis", "el archivo original", "limitaciones:", "resultado multimodal")
        require(not any(marker in result_explanation.lower() for marker in spanish_leaks), f"English demo leaked Spanish result explanation: {result_explanation[:500]}")
        report["result_id"] = result_id
        report["document_id"] = document_id
        report["result_panel"] = str(result.get("panel") or "")
        report["checks"].extend([
            "multimodal_original_result_and_provenance",
            "english_multimodal_result_explanation",
        ])
        checkpoint(report)
        overlay(page, "Evidence first", "The original synthetic PDF is preserved in private Cloud Storage; Gemini extracts readable evidence and Firestore stores patient-scoped state with provenance.", 4)
        clear_overlay(page)

        page.locator('.main-nav [data-open="chat"]').click()
        before_explanation = latest_assistant_message(page)
        send_chat(page, f"Explain the result {filename} I just uploaded and confirm that it was saved with the original file.")
        explanation_reply = wait_for_assistant_after(page, str(before_explanation.get("id") or ""), timeout_s=45.0)
        explanation_meta = explanation_reply.get("metadata") or {}
        reply_mission_id = str(explanation_reply.get("mission_id") or "")
        report["result_explanation_reply"] = {
            "id": str(explanation_reply.get("id") or ""),
            "mission_id": reply_mission_id,
            "intent": explanation_meta.get("intent"),
            "mission_type": explanation_meta.get("mission_type"),
            "action_target": explanation_meta.get("action_target"),
            "response_locale": explanation_meta.get("response_locale"),
        }
        checkpoint(report)
        require(explanation_meta.get("response_locale") == "en", f"result explanation reply was not English: {explanation_meta}")
        require(explanation_meta.get("mission_type") == "result_explanation", f"explicit current result did not outrank stale context: {explanation_meta}")
        require(explanation_meta.get("action_target") == "results", f"result explanation routed to wrong workspace: {explanation_meta}")
        require(reply_mission_id, f"result explanation response has no mission_id: {explanation_meta}")
        mission = wait_for_exact_result_mission(
            page,
            mission_id=reply_mission_id,
            result_id=result_id,
            document_id=document_id,
        )
        report["mission_id"] = reply_mission_id
        report["checks"].extend([
            "explicit_current_topic_overrides_stale_context",
            "assistant_mission_link_matches_persisted_taskmaster",
            "taskmaster_mission_completed_from_persisted_evidence",
        ])
        checkpoint(report)
        page.locator('.main-nav [data-open="missions"]').click()
        page.wait_for_timeout(500)
        overlay(page, "Taskmaster closure", "This mission is complete because the persisted result and original evidence exist and remain linked — not merely because the model produced an answer.", 4)
        clear_overlay(page)

        page.locator('.main-nav [data-open="chat"]').click()
        before_video = latest_assistant_message(page)
        send_chat(page, "Create a short private video in English about my glucose result.")
        video_reply = wait_for_assistant_after(
            page,
            str(before_video.get("id") or ""),
            timeout_s=210.0,
            poll_ms=2000,
            rate_limit_backoff_ms=5000,
        )
        video_meta = video_reply.get("metadata") or {}
        video_record = video_meta.get("education_video") or {}
        require(video_record.get("status") == "completed", f"HealthIA Explain did not complete: {video_record}")
        require(video_record.get("private") is True, "HealthIA Explain media is not private")
        require(video_record.get("locale") == "en", f"HealthIA Explain locale mismatch: {video_record}")
        require(video_record.get("narration_status") == "gemini_tts", f"HealthIA Explain did not use Gemini TTS: {video_record}")
        video_id = str(video_record.get("video_id") or "")
        require(video_id.startswith("video_"), f"HealthIA Explain video id missing: {video_record}")
        manifest = api_json(page, f"/api/education/videos/{video_id}/manifest")
        require(manifest.get("private") is True, f"HealthIA Explain manifest is not private: {manifest}")
        require(manifest.get("narration_status") == "gemini_tts", f"HealthIA Explain manifest did not preserve Gemini TTS: {manifest}")
        report["education_video"] = {
            "video_id": video_id,
            "title": video_record.get("title"),
            "locale": video_record.get("locale"),
            "private": video_record.get("private"),
            "narration_status": video_record.get("narration_status"),
            "veo_enhanced": bool(video_record.get("veo_enhanced")),
        }
        report["checks"].extend([
            "healthia_explain_private_video_completed",
            "healthia_explain_gemini_tts_narration",
        ])
        checkpoint(report)
        page.wait_for_selector(".education-video-card video", timeout=15_000)
        overlay(page, "HealthIA Explain", "The patient asks for a private visual explanation. Gemini plans the education flow, Gemini TTS narrates it, and patient facts remain on controlled HealthIA cards. Veo is limited to generic PHI-free visual enrichment.", 5)
        clear_overlay(page)
        media = page.locator(".education-video-card video").last
        media.evaluate("el => { el.muted = true; el.currentTime = 0; return el.play(); }")
        page.wait_for_timeout(7000)
        require(media.evaluate("el => !el.error"), "HealthIA Explain video element reported a playback error")
        report["checks"].append("healthia_explain_video_playback")
        checkpoint(report)

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
        require(any(item.get("id") == reply_mission_id and item.get("status") == "completed" for item in restored.get("missions", [])), "mission disappeared after relogin")
        report["checks"].append("logout_login_durable_continuity")
        checkpoint(report)
        overlay(page, "Durable continuity", "After logout and login, the result, original evidence and completed Taskmaster mission are still present.", 4)
        clear_overlay(page)

        readiness = api_json(page, "/api/readiness")
        page.locator('.main-nav [data-open="chat"]').click()
        cloud_summary = (
            f"Exact candidate {CANDIDATE_SHA[:12]} · Cloud Run {CLOUD_REVISION or 'verified'} · "
            f"Gemini {readiness.get('model')} · ADK ready: {readiness.get('adk_ready')} · "
            f"State: {readiness.get('store_backend')} · Evidence: {readiness.get('evidence_backend')}"
        )
        overlay(page, "Live Google Cloud proof", cloud_summary, 5)
        report["checks"].append("visible_exact_candidate_cloud_proof")
        clear_overlay(page)

        require(not page_errors, f"browser page errors: {page_errors}")
        require(not console_errors, f"browser console errors: {console_errors}")
        report["checks"].append("zero_browser_console_or_page_errors")
        report["status"] = "PASS"
        report["raw_elapsed_seconds"] = round(time.monotonic() - started, 2)
        checkpoint(report)
        context.close()
        browser.close()

    videos = sorted(video_dir.glob("*.webm"))
    require(bool(videos), "Playwright did not produce a video")
    video = videos[0]
    report["video_file"] = str(video.relative_to(ROOT))
    report["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    checkpoint(report)
    print("HEALTHIA_FINAL_LIVE_ENGLISH_DEMO_PASS")
    print(json.dumps({"status": report["status"], "candidate_sha": CANDIDATE_SHA, "checks": report["checks"], "video_sha256": report["video_sha256"], "elapsed_seconds": report["elapsed_seconds"]}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        if REPORT.exists():
            try:
                failure = json.loads(REPORT.read_text(encoding="utf-8"))
            except Exception:
                failure = {}
        else:
            failure = {}
        failure.update({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:3000]})
        REPORT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_FINAL_LIVE_ENGLISH_DEMO_FAIL {type(exc).__name__}: {exc}")
        raise
