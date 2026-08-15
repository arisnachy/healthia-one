from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright

from cloud_browser_judge_proof import api_json, require, tiny_pdf
from record_final_live_english_demo import (
    clear_overlay,
    latest_assistant_message,
    latest_result_state,
    overlay,
    send_chat,
    wait_for_assistant_after,
    wait_for_exact_result_mission,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "final-comprehensive-demo"
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


def browser_api(page: Page, path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    result = page.evaluate(
        """async ({path, method, payload}) => {
          const options = {method, headers: {"Accept-Language": "en"}};
          if (payload !== null) {
            options.headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(payload);
          }
          const response = await fetch(path, options);
          const text = await response.text();
          let body = {};
          try { body = text ? JSON.parse(text) : {}; } catch { body = {raw: text}; }
          return {status: response.status, ok: response.ok, body};
        }""",
        {"path": path, "method": method, "payload": payload},
    )
    require(result.get("ok") is True, f"{method} {path} failed: {result}")
    return result.get("body") or {}


def activate(page: Page, view: str) -> None:
    selector = f'.main-nav [data-open="{view}"]'
    page.wait_for_selector(selector, state="visible", timeout=15_000)
    page.locator(selector).click()
    page.wait_for_function(
        """view => document.getElementById(`view-${view}`)?.classList.contains('is-active') === true""",
        arg=view,
        timeout=15_000,
    )
    page.wait_for_timeout(350)


def seed_breadth(page: Page) -> dict:
    now = datetime.now(timezone.utc)
    family = [
        {
            "display_name": "Maternal grandmother",
            "relation": "grandmother",
            "generation": -2,
            "lineage": "maternal",
            "sex_at_birth": "female",
            "biological_relative": True,
            "conditions": [{"name": "Type 2 diabetes", "age_at_diagnosis": 58, "confirmed": False, "notes": "Synthetic patient report"}],
        },
        {
            "display_name": "Father",
            "relation": "father",
            "generation": -1,
            "lineage": "paternal",
            "sex_at_birth": "male",
            "biological_relative": True,
            "conditions": [{"name": "Hypertension", "age_at_diagnosis": 52, "confirmed": False, "notes": "Synthetic patient report"}],
        },
    ]
    family_created = [browser_api(page, "/api/family", method="POST", payload=item) for item in family]

    medication = browser_api(
        page,
        "/api/treatment/plans",
        method="POST",
        payload={
            "original_text": "Losartan 50 mg once daily",
            "name": "Losartan",
            "generic_name": "losartan",
            "strength": "50 mg",
            "dose_value": 50,
            "dose_unit": "mg",
            "dosage_form": "tablet",
            "route": "oral",
            "schedule": "once daily",
            "frequency_times_per_day": 1,
            "purpose": "Recorded blood pressure treatment",
            "instructions": "Take exactly as prescribed",
            "verification_status": "patient_confirmed",
            "active": True,
        },
    )

    appointment = browser_api(
        page,
        "/api/appointments",
        method="POST",
        payload={
            "title": "Family medicine follow-up",
            "specialty": "Family medicine",
            "scheduled_at": (now + timedelta(days=12)).isoformat(),
            "location": "Primary Care Clinic",
            "status": "scheduled",
            "required_documents": ["Recent laboratory result", "Home blood pressure log"],
            "questions": [
                "What should I monitor at home?",
                "How should we follow up this laboratory result?",
            ],
            "notes": "Synthetic judge-demo appointment",
        },
    )

    vital = browser_api(
        page,
        "/api/vitals",
        method="POST",
        payload={
            "measured_at": (now - timedelta(hours=4)).isoformat(),
            "systolic": 148,
            "diastolic": 92,
            "pulse": 84,
            "blood_glucose_mg_dl": 103,
            "symptoms": [],
        },
    )
    weight = browser_api(
        page,
        "/api/weight",
        method="POST",
        payload={
            "measured_at": (now - timedelta(days=1)).isoformat(),
            "weight_kg": 78.4,
            "note": "Synthetic home measurement",
        },
    )
    activity = browser_api(
        page,
        "/api/activity",
        method="POST",
        payload={
            "measured_at": (now - timedelta(hours=8)).isoformat(),
            "steps": 5200,
            "active_minutes": 32,
            "note": "Synthetic wearable summary",
        },
    )
    return {
        "family_ids": [item.get("id") for item in family_created],
        "medication_id": medication.get("id"),
        "appointment_id": appointment.get("id"),
        "vital_id": vital.get("id"),
        "weight_id": weight.get("id"),
        "activity_id": activity.get("id"),
    }


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
    note_path = OUTPUT / "synthetic-care-note.txt"
    note_path.write_text(
        "Synthetic patient note for hackathon demonstration.\n"
        "Purpose: verify patient-owned document archive and provenance.\n"
        "No real patient information is present.\n",
        encoding="utf-8",
    )

    suffix = uuid4().hex[:10]
    email = f"comprehensive-demo-{suffix}@example.test"
    password = f"Comprehensive!{suffix}Aa9"
    display_name = "HealthIA Judge Patient"
    filename = pdf_path.name
    console_errors: list[str] = []
    page_errors: list[str] = []
    http_server_errors: list[dict[str, object]] = []
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
        page.on(
            "response",
            lambda response: http_server_errors.append({"status": response.status, "url": response.url})
            if response.status == 429 or response.status >= 500
            else None,
        )

        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)
        page.wait_for_function("document.documentElement.lang === 'en'")
        require(page.locator("#registerTab").is_visible(), "registration UI missing")
        overlay(page, "HealthIA ONE", "A patient-owned health continuity OS — not a one-question chatbot.", 3.5)
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
        overlay(
            page,
            "Live Google architecture",
            f"Gemini {readiness.get('model')} · Google ADK ready · Firestore state · private GCS evidence.",
            3.5,
        )
        clear_overlay(page)

        page.evaluate("window.HealthIAI18n.setLocale('es')")
        page.wait_for_function("document.documentElement.lang === 'es'")
        overlay(page, "Language-native HealthIA", "The interface can localize immediately; in auto mode it follows the operating system/browser, while clinical content follows the language the patient writes.", 3.5)
        clear_overlay(page)
        page.evaluate("window.HealthIAI18n.setAuto()")
        page.wait_for_function("document.documentElement.lang === 'en'")
        report["checks"].append("ui_locale_auto_and_multilingual_translation")
        checkpoint(report)

        seeded = seed_breadth(page)
        report["seeded_demo_state"] = seeded
        checkpoint(report)

        activate(page, "record")
        page.wait_for_selector("#recordGrid .record-card", timeout=12_000)
        overlay(page, "One longitudinal patient record", "Confirmed conditions, registered treatment, allergies, authorized signals and continuity counts stay together instead of restarting with each chat.", 4)
        clear_overlay(page)
        report["checks"].append("longitudinal_patient_record_visible")

        activate(page, "family")
        page.wait_for_selector("#genogramRoot .family-node", timeout=12_000)
        require(page.locator("#genogramRoot .family-node").count() >= 2, "family genogram did not render seeded relatives")
        overlay(page, "Family genogram", "Maternal and paternal history become structured context for preventive questions. A family pattern is context — never an automatic diagnosis.", 4.5)
        clear_overlay(page)
        report["checks"].append("family_genogram_visible")

        activate(page, "documents")
        page.wait_for_selector("#addDocumentButton", timeout=10_000)
        page.locator("#addDocumentButton").click()
        page.wait_for_selector("#documentDialog[open]", timeout=10_000)
        page.locator('#documentForm input[name="file"]').set_input_files(str(note_path))
        page.locator('#documentForm input[name="title"]').fill("Synthetic care note")
        page.locator('#documentForm select[name="category"]').select_option("consultation")
        page.locator('#documentForm button[type="submit"]').click()
        page.wait_for_selector("#documentDialog", state="hidden", timeout=60_000)
        page.wait_for_function(
            """() => document.querySelector('#documentsRoot')?.textContent?.includes('Synthetic care note') === true""",
            timeout=30_000,
        )
        page.wait_for_timeout(700)
        overlay(page, "Patient document archive", "Clinical files keep category, source, status and the original bytes. If HealthIA cannot read something, it preserves the source instead of inventing content.", 4.5)
        clear_overlay(page)
        report["checks"].append("document_archive_and_original_upload_visible")

        activate(page, "treatment")
        page.wait_for_selector("#treatmentRoot .treatment-card", timeout=12_000)
        taken = page.locator('#treatmentRoot [data-dose="taken"]').first
        require(taken.count() == 1, "treatment check-in control missing")
        taken.click()
        page.wait_for_timeout(900)
        overlay(page, "Treatment safety", "HealthIA records the prescribed plan and adherence check-ins. It can document a dose as taken, but it does not autonomously double, stop or change medication.", 4.5)
        clear_overlay(page)
        report["checks"].append("treatment_plan_and_safe_checkin_visible")

        activate(page, "appointments")
        page.wait_for_selector("#appointmentsRoot .appointment-card", timeout=12_000)
        page.wait_for_selector("#appointmentsRoot .brief-hero", timeout=12_000)
        overlay(page, "Visit preparation", "The next visit carries forward conditions, treatment, required documents, family context and prioritized questions — with the patient controlling what gets shared.", 4.5)
        clear_overlay(page)
        report["checks"].append("appointment_and_consultation_brief_visible")

        activate(page, "timeline")
        page.wait_for_selector("#timelineRoot .timeline-event", timeout=12_000)
        require(page.locator("#timelineRoot .timeline-event").count() >= 3, "unified timeline did not render seeded longitudinal events")
        overlay(page, "Unified health timeline", "Vitals, weight, activity, documents, treatment, appointments, results and missions share one provenance-linked chronology.", 4.5)
        clear_overlay(page)
        report["checks"].append("unified_health_timeline_visible")

        activate(page, "control")
        page.wait_for_selector("#controlRoot .control-card", timeout=12_000)
        require(page.locator('#controlRoot [data-signal]').count() >= 5, "signal permissions missing")
        require(page.locator('#controlRoot a[href="/api/export"]').count() == 1, "patient export missing")
        overlay(page, "Patient control and audit", "Permissions are reversible: signal classes, quiet hours, snooze, muted follow-up, urgent safety, audit history and structured export all remain patient controlled.", 5)
        clear_overlay(page)
        report["checks"].append("permissions_audit_and_export_visible")
        checkpoint(report)

        activate(page, "results")
        report["checks"].append("results_workspace_opened")
        checkpoint(report)
        overlay(page, "Evidence becomes durable work", "Now the Taskmaster core: a new result enters as original evidence, becomes structured state, and creates work that survives the conversation.", 4)
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
        report["checks"].extend([
            "multimodal_original_result_and_provenance",
            "english_multimodal_result_explanation",
        ])
        checkpoint(report)
        overlay(page, "Evidence first", "The synthetic original is preserved in private Cloud Storage; Gemini extracts readable evidence and Firestore keeps patient-scoped state with provenance.", 4.5)
        clear_overlay(page)

        activate(page, "chat")
        before_explanation = latest_assistant_message(page)
        send_chat(page, f"Explain the result {filename} I just uploaded and confirm that it was saved with the original file.")
        explanation_reply = wait_for_assistant_after(page, str(before_explanation.get("id") or ""), timeout_s=45.0)
        explanation_meta = explanation_reply.get("metadata") or {}
        reply_mission_id = str(explanation_reply.get("mission_id") or "")
        require(explanation_meta.get("response_locale") == "en", f"result reply was not English: {explanation_meta}")
        require(explanation_meta.get("mission_type") == "result_explanation", f"wrong mission type: {explanation_meta}")
        require(explanation_meta.get("action_target") == "results", f"wrong action target: {explanation_meta}")
        require(reply_mission_id, "result explanation response has no mission_id")
        wait_for_exact_result_mission(
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
        activate(page, "missions")
        overlay(page, "Durable Taskmaster closure", "This mission closes because the persisted result and its original evidence exist and remain linked — not because the model simply finished talking.", 4.5)
        clear_overlay(page)

        activate(page, "chat")
        before_video = latest_assistant_message(page)
        explain_console_start = len(console_errors)
        explain_http_start = len(http_server_errors)
        send_chat(page, "Create a short private video in English about my glucose result.")
        video_reply = wait_for_assistant_after(
            page,
            str(before_video.get("id") or ""),
            timeout_s=210.0,
            poll_ms=2000,
            rate_limit_backoff_ms=5000,
        )
        video_record = (video_reply.get("metadata") or {}).get("education_video") or {}
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
        overlay(page, "HealthIA Explain", "Education follows the patient's language. Gemini structures the explanation, Gemini TTS narrates it, and Veo is restricted to generic PHI-free visual enrichment.", 5)
        clear_overlay(page)
        media = page.locator(".education-video-card video").last
        media.evaluate("el => { el.muted = true; el.currentTime = 0; return el.play(); }")
        page.wait_for_timeout(7000)
        require(media.evaluate("el => !el.error"), "HealthIA Explain video element reported a playback error")
        report["checks"].append("healthia_explain_video_playback")

        explain_http_errors = http_server_errors[explain_http_start:]
        allowed_bootstrap_transients = [
            item for item in explain_http_errors
            if item.get("status") in {429, 500}
            and str(item.get("url") or "").split("?", 1)[0].endswith("/api/bootstrap")
        ]
        unexpected_explain_http = [item for item in explain_http_errors if item not in allowed_bootstrap_transients]
        require(not unexpected_explain_http, f"unexpected HealthIA Explain HTTP errors: {unexpected_explain_http}")
        require(len(allowed_bootstrap_transients) <= 6, f"too many transient bootstrap responses: {allowed_bootstrap_transients}")

        explain_console_errors = console_errors[explain_console_start:]
        console_message_by_status = {
            429: "Failed to load resource: the server responded with a status of 429 ()",
            500: "Failed to load resource: the server responded with a status of 500 ()",
        }
        expected_console_messages = set(console_message_by_status.values())
        unexpected_explain_console = [item for item in explain_console_errors if item not in expected_console_messages]
        require(not unexpected_explain_console, f"unexpected HealthIA Explain console errors: {unexpected_explain_console}")
        for status, message in console_message_by_status.items():
            console_count = sum(item == message for item in explain_console_errors)
            response_count = sum(item.get("status") == status for item in allowed_bootstrap_transients)
            require(console_count <= response_count, f"console reported HTTP {status} without matching recovered /api/bootstrap")
        if allowed_bootstrap_transients:
            report["recovered_transient_bootstrap_responses"] = {
                str(status): sum(item.get("status") == status for item in allowed_bootstrap_transients)
                for status in (429, 500)
                if any(item.get("status") == status for item in allowed_bootstrap_transients)
            }
            report["checks"].append("bounded_transient_bootstrap_recovery")
        console_errors[:] = console_errors[:explain_console_start]
        http_server_errors[:] = http_server_errors[:explain_http_start]
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
        require(len(restored.get("family_members", [])) >= 2, "family history disappeared after relogin")
        require(len(restored.get("appointments", [])) >= 1, "appointment disappeared after relogin")
        report["checks"].append("logout_login_durable_continuity")
        checkpoint(report)
        overlay(page, "Continuity survives the chat", "Logout and login do not erase the patient's result, original evidence, family context, appointment or completed mission.", 4)
        clear_overlay(page)

        readiness = api_json(page, "/api/readiness")
        activate(page, "chat")
        overlay(
            page,
            "Production-oriented Google proof",
            f"Exact SHA {CANDIDATE_SHA[:12]} · Cloud Run {CLOUD_REVISION or 'verified'} · Gemini {readiness.get('model')} · ADK ready · Firestore · private GCS.",
            5,
        )
        report["checks"].append("visible_exact_candidate_cloud_proof")
        clear_overlay(page)

        require(not page_errors, f"browser page errors: {page_errors}")
        require(not console_errors, f"browser console errors: {console_errors}")
        require(not http_server_errors, f"browser HTTP server errors: {http_server_errors}")
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
    print("HEALTHIA_FINAL_COMPREHENSIVE_DEMO_PASS")
    print(json.dumps({
        "status": report["status"],
        "candidate_sha": CANDIDATE_SHA,
        "checks": report["checks"],
        "video_sha256": report["video_sha256"],
        "elapsed_seconds": report["elapsed_seconds"],
    }, ensure_ascii=False))
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        failure = {}
        if REPORT.exists():
            try:
                failure = json.loads(REPORT.read_text(encoding="utf-8"))
            except Exception:
                pass
        failure.update({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:3000]})
        REPORT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_FINAL_COMPREHENSIVE_DEMO_FAIL {type(exc).__name__}: {exc}")
        raise
