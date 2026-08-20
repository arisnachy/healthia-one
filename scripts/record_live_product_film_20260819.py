from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright

from cloud_browser_judge_proof import api_json, require

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "live-product-film"
REPORT = OUT / "recording-report.json"
BASE_URL = os.getenv("HEALTHIA_CLOUD_URL", "").rstrip("/")
IDENTITY_TOKEN = os.getenv("HEALTHIA_CLOUD_ID_TOKEN", "")
SOURCE_SHA = os.getenv("HEALTHIA_SOURCE_SHA", "")
CLOUD_REVISION = os.getenv("HEALTHIA_CLOUD_REVISION", "")

RESULT_GUARDIAN = "result_guardian_losartan_monitoring_context"
APPOINTMENT_GUARDIAN = "appointment_guardian_preparation"
POSTVISIT_GUARDIAN = "postvisit_guardian_summary_capture"


def checkpoint(report: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def hold(page: Page, seconds: float = 2.0) -> None:
    page.wait_for_timeout(int(seconds * 1000))


def state(page: Page) -> dict:
    return api_json(page, "/api/bootstrap")


def wait_mission(page: Page, mission_type: str, status: str | None = None, timeout_s: float = 30.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        snap = state(page)
        candidates = [m for m in snap.get("missions", []) if m.get("mission_type") == mission_type]
        if candidates:
            last = candidates[-1]
            if status is None or last.get("status") == status:
                return last
        page.wait_for_timeout(350)
    raise RuntimeError(f"mission {mission_type} did not reach {status}: {last}")


def wait_result(page: Page, filename: str, timeout_s: float = 30.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        matches = [r for r in state(page).get("results", []) if r.get("filename") == filename]
        if matches and matches[-1].get("status") == "parsed":
            return matches[-1]
        page.wait_for_timeout(350)
    raise RuntimeError(f"result did not parse: {filename}")


def goto(page: Page, view: str, seconds: float = 2.0) -> None:
    button = page.locator(f'.main-nav [data-open="{view}"]')
    require(button.count() > 0, f"HealthIA navigation missing: {view}")
    button.first.click()
    page.wait_for_function(f"document.getElementById('view-{view}')?.classList.contains('is-active') === true")
    hold(page, seconds)


def upload_result(page: Page, path: Path) -> dict:
    goto(page, "results", 1.0)
    target = page.locator("#resultFilePage")
    require(target.count() == 1, "real Results file input missing")
    target.set_input_files(str(path))
    result = wait_result(page, path.name, 45.0)
    page.wait_for_function("document.getElementById('resultProcessing')?.hidden === true", timeout=45_000)
    hold(page, 2.5)
    return result


def upload_document(page: Page, path: Path, *, title: str, category: str) -> None:
    goto(page, "documents", 1.2)
    page.locator("#addDocumentButton").click()
    page.locator('#documentForm input[name="file"]').set_input_files(str(path))
    page.locator('#documentForm input[name="title"]').fill(title)
    page.locator('#documentForm select[name="category"]').select_option(category)
    with page.expect_response(lambda r: r.request.method == "POST" and "/api/documents/upload" in r.url, timeout=70_000) as pending:
        page.locator('#documentForm button[type="submit"]').click()
    response = pending.value
    body = response.text()
    require(response.ok, f"real Documents upload failed HTTP {response.status}: {body[:1500]}")
    page.wait_for_function("!document.getElementById('documentDialog')?.open", timeout=60_000)
    hold(page, 2.5)


def setup_account(playwright, email: str, password: str, storage_path: Path) -> None:
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        locale="en-US",
        extra_http_headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
    )
    page = context.new_page()
    page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)
    page.locator("#registerTab").click()
    page.locator('#registerForm input[name="display_name"]').fill("Ana Martinez")
    page.locator('#registerForm input[name="email"]').fill(email)
    page.locator('#registerForm input[name="password"]').fill(password)
    page.locator('#registerForm button[type="submit"]').click()
    page.wait_for_url(f"{BASE_URL}/", timeout=30_000)
    page.wait_for_load_state("networkidle")
    response = page.evaluate("""async () => {
      const r = await fetch('/api/treatment/plans', {
        method:'POST', headers:{'Content-Type':'application/json','Accept-Language':'en'},
        body: JSON.stringify({
          original_text:'Losartan 50 mg by mouth once daily', name:'Losartan', generic_name:'losartan',
          strength:'50 mg', dose_value:50, dose_unit:'mg', dosage_form:'tablet', route:'oral',
          schedule:'once daily', frequency_times_per_day:1, purpose:'Blood pressure control',
          instructions:'Follow the treating clinician instructions.', prescribed_by:'Treating clinician — synthetic demo',
          verification_status:'professional_confirmed', active:true
        })
      });
      return {ok:r.ok, status:r.status, text:await r.text()};
    }""")
    require(response["ok"], f"could not seed clinician-confirmed losartan: {response}")
    context.storage_state(path=str(storage_path))
    context.close()
    browser.close()


def submit_real_appointment_form(page: Page) -> dict:
    values = page.locator("#appointmentForm").evaluate("""form => Object.fromEntries(new FormData(form).entries())""")
    require(bool(values.get("title")), f"appointment title missing before submit: {values}")
    require(bool(values.get("scheduled_at")), f"appointment date missing before submit: {values}")
    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/api/appointments"), timeout=75_000) as pending:
        page.locator('#appointmentForm button[type="submit"]').click()
    response = pending.value
    body = response.text()
    require(response.ok, f"real appointment UI POST failed HTTP {response.status}: {body[:2000]} | form={values}")
    page.wait_for_function("!document.getElementById('appointmentDialog')?.open", timeout=60_000)
    payload = json.loads(body)
    require(payload.get("title") == values.get("title"), f"appointment response mismatch: {payload}")
    return payload


def run() -> dict:
    require(BASE_URL.startswith("https://") and ".run.app" in BASE_URL, "Cloud Run .run.app URL required")
    require(bool(IDENTITY_TOKEN), "Cloud Run identity token required")
    OUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUT / "video"
    video_dir.mkdir(parents=True, exist_ok=True)

    renal = OUT / "renal-function-creatinine.json"
    renal.write_text(json.dumps({"panel":"Renal function","results":[{"name":"Creatinine","value":0.9,"unit":"mg/dL","reference":"0.6-1.2"}]}, indent=2), encoding="utf-8")
    potassium = OUT / "potassium-followup.json"
    potassium.write_text(json.dumps({"panel":"Electrolytes","results":[{"name":"Potassium","value":4.2,"unit":"mmol/L","reference":"3.5-5.1"}]}, indent=2), encoding="utf-8")
    insurance = OUT / "insurance-card.txt"
    insurance.write_text("SYNTHETIC INSURANCE DOCUMENT\nMember: Ana Martinez\nPlan: Demo Health Plan\n", encoding="utf-8")
    note = OUT / "family-medicine-consultation-note.txt"
    note.write_text("SYNTHETIC CONSULTATION NOTE\nFamily medicine follow-up completed.\nNo autonomous diagnosis or treatment change is represented in this demo file.\n", encoding="utf-8")

    suffix = uuid4().hex[:10]
    email = f"healthia-live-{suffix}@example.test"
    password = f"LiveFilm!{suffix}Aa9"
    storage_path = OUT / "session.json"
    console_errors: list[str] = []
    page_errors: list[str] = []
    report = {
        "schema":"healthia-live-product-film/v1",
        "status":"running",
        "synthetic_only":True,
        "live_app_only":True,
        "slides_used":False,
        "director_surface_used":False,
        "source_sha":SOURCE_SHA,
        "cloud_url":BASE_URL,
        "cloud_revision":CLOUD_REVISION,
        "checks":[],
    }
    checkpoint(report)

    with sync_playwright() as p:
        setup_account(p, email, password, storage_path)
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            locale="en-US",
            viewport={"width":1920,"height":1080},
            record_video_dir=str(video_dir),
            record_video_size={"width":1920,"height":1080},
            storage_state=str(storage_path),
            extra_http_headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
        )
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.goto(BASE_URL, wait_until="networkidle", timeout=60_000)
        page.wait_for_selector("#app")

        readiness = api_json(page, "/api/readiness")
        require(readiness.get("ai_ready") is True, f"Gemini not ready: {readiness}")
        require(readiness.get("adk_ready") is True, f"ADK not ready: {readiness}")
        require(readiness.get("model") == "gemini-3.5-flash", f"wrong model: {readiness.get('model')}")
        require(readiness.get("store_backend") == "firestore", "film is not using Firestore")
        require(readiness.get("evidence_backend") == "gcs", "film is not using GCS")
        page.locator("#runtimeLabel").evaluate("""(el, p) => {
          el.textContent = `Cloud Run · ${location.host} · Gemini ${p.model} · Google ADK`;
          el.style.fontSize='12px'; el.style.maxWidth='620px'; el.style.whiteSpace='normal';
        }""", {"model":readiness.get("model")})
        report["checks"].append("visible_run_app_gemini_adk_inside_real_product")

        goto(page, "treatment", 4.0)
        require(page.locator("#treatmentRoot").inner_text().lower().find("losartan") >= 0, "Losartan not visible in real Treatment view")
        report["checks"].append("real_product_shows_registered_treatment")

        upload_result(page, renal)
        result_mission = wait_mission(page, RESULT_GUARDIAN, "waiting_patient", 35.0)
        report["result_mission_id"] = result_mission["id"]
        goto(page, "missions", 4.0)
        require("losartan" in page.locator("#missionList").inner_text().lower(), "treatment-aware Guardian mission not visible")
        report["checks"].append("result_guardian_opens_without_chat_prompt_in_real_ui")

        upload_result(page, potassium)
        result_closed = wait_mission(page, RESULT_GUARDIAN, "completed", 35.0)
        require(result_closed["id"] == result_mission["id"], "Result Guardian did not close the same mission")
        goto(page, "missions", 4.0)
        report["checks"].append("result_guardian_same_mission_closes_from_new_evidence")

        goto(page, "appointments", 2.0)
        page.locator("#addAppointmentButton").click()
        appt_time = datetime.now().astimezone() + timedelta(hours=36)
        page.locator('#appointmentForm input[name="title"]').fill("Family medicine follow-up")
        page.locator('#appointmentForm input[name="specialty"]').fill("Family medicine")
        page.locator('#appointmentForm input[name="scheduled_at"]').fill(appt_time.strftime("%Y-%m-%dT%H:%M"))
        page.locator('#appointmentForm input[name="location"]').fill("HealthIA synthetic clinic")
        page.locator('#appointmentForm input[name="required_documents"]').fill("Recent results, Medication list, Insurance")
        page.locator('#appointmentForm textarea[name="questions"]').fill("What blood pressure target should I discuss?")
        appointment_created = submit_real_appointment_form(page)
        report["appointment_id"] = appointment_created["id"]
        hold(page, 2.0)
        appt_mission = wait_mission(page, APPOINTMENT_GUARDIAN, "waiting_patient", 45.0)
        report["appointment_mission_id"] = appt_mission["id"]
        goto(page, "missions", 4.0)
        report["checks"].append("appointment_guardian_verifies_twin_and_opens_missing_insurance")

        upload_document(page, insurance, title="Insurance card", category="insurance")
        appt_closed = wait_mission(page, APPOINTMENT_GUARDIAN, "completed", 45.0)
        require(appt_closed["id"] == appt_mission["id"], "Appointment Guardian did not close the same mission")
        goto(page, "missions", 3.5)
        report["checks"].append("appointment_guardian_closes_from_real_document_upload")

        goto(page, "appointments", 2.0)
        snap = state(page)
        appointment = next(item for item in snap["appointments"] if item["id"] == appointment_created["id"])
        completed = dict(appointment)
        completed["status"] = "completed"
        completed["scheduled_at"] = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        update = page.evaluate("""async payload => {
          const r = await fetch('/api/appointments',{method:'POST',headers:{'Content-Type':'application/json','Accept-Language':'en'},body:JSON.stringify(payload)});
          return {ok:r.ok,status:r.status,text:await r.text()};
        }""", completed)
        require(update["ok"], f"external appointment update failed: {update}")
        post_mission = wait_mission(page, POSTVISIT_GUARDIAN, "waiting_patient", 45.0)
        report["postvisit_mission_id"] = post_mission["id"]
        page.reload(wait_until="networkidle")
        page.locator("#runtimeLabel").evaluate("""(el, p) => { el.textContent=`Cloud Run · ${location.host} · Gemini ${p.model} · Google ADK`; el.style.fontSize='12px'; el.style.maxWidth='620px'; el.style.whiteSpace='normal'; }""", {"model":readiness.get("model")})
        goto(page, "appointments", 2.5)
        require("completed" in page.locator("#appointmentsRoot").inner_text().lower(), "completed appointment not visible")
        goto(page, "missions", 3.5)
        report["checks"].append("postvisit_guardian_opens_from_completed_visit_event")

        upload_document(page, note, title="Family medicine consultation note", category="consultation")
        post_closed = wait_mission(page, POSTVISIT_GUARDIAN, "completed", 45.0)
        require(post_closed["id"] == post_mission["id"], "Post-Visit Guardian did not close same mission")
        goto(page, "missions", 4.0)
        report["checks"].append("postvisit_guardian_closes_from_real_consultation_document")

        # Prove the current Chat UI is driven by the real Gemini response, not by a stale selector or a scripted panel.
        goto(page, "chat", 1.5)
        complaint = "Desde ayer me arde al orinar y tengo que ir al baño a cada rato. Quiero entender qué información necesitas."
        page.locator("#chatInput").fill(complaint)
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/api/chat"), timeout=90_000) as pending_chat:
            page.locator("#sendButton").click()
        chat_response = pending_chat.value
        chat_body = chat_response.text()
        require(chat_response.ok, f"real Chat /api/chat failed HTTP {chat_response.status}: {chat_body[:2000]}")
        chat_payload = json.loads(chat_body)
        assistant = chat_payload.get("message") or {}
        metadata = assistant.get("metadata") or {}
        interview = metadata.get("clinical_interview") or {}
        block = interview.get("question_block") or {}
        questions = block.get("questions") or []
        require(metadata.get("llm_status") == "dynamic_clinical_questions", f"Gemini did not return dynamic clinical questions: {metadata.get('llm_status')}")
        require(metadata.get("question_source") == "gemini_dynamic", f"question source was not Gemini: {metadata.get('question_source')}")
        require(metadata.get("model") == "gemini-3.5-flash", f"wrong model in live Chat response: {metadata.get('model')}")
        require(len(questions) == 5, f"Gemini live response did not contain exactly five questions: {len(questions)}")
        assistant_id = assistant.get("id")
        require(bool(assistant_id), "live Chat response has no assistant message id")
        selector = f'.message[data-id="{assistant_id}"] .clinical-question-block[data-question-source="gemini_dynamic"]'
        page.wait_for_selector(selector, timeout=90_000)
        require(page.locator(f'{selector} .clinical-question').count() == 5, "real Chat UI did not render all five Gemini questions")
        require(page.locator(f'{selector} .clinical-question:visible').count() == 1, "adaptive interview is not one-question-at-a-time")
        first_prompt = str(questions[0].get("prompt") or "").strip()
        require(bool(first_prompt), "Gemini first question has no prompt")
        require(first_prompt in page.locator(selector).inner_text(), "visible adaptive interview does not match Gemini response")
        report["gemini_message_id"] = assistant_id
        report["gemini_question_count"] = len(questions)
        report["gemini_first_question"] = first_prompt
        hold(page, 8.0)
        report["checks"].append("live_gemini_35_flash_google_adk_adaptive_interview")

        goto(page, "missions", 5.0)
        final = state(page)
        require(any(m.get("id") == result_mission["id"] and m.get("status") == "completed" for m in final.get("missions", [])), "result mission lost")
        require(any(m.get("id") == appt_mission["id"] and m.get("status") == "completed" for m in final.get("missions", [])), "appointment mission lost")
        require(any(m.get("id") == post_mission["id"] and m.get("status") == "completed" for m in final.get("missions", [])), "postvisit mission lost")
        report["checks"].append("three_durable_guardian_missions_visible_in_real_healthia")

        require(not page_errors, f"page errors: {page_errors}")
        noisy = [e for e in console_errors if "favicon" not in e.lower()]
        require(not noisy, f"console errors: {noisy}")
        report["checks"].append("zero_browser_errors")
        report["status"] = "PASS"
        checkpoint(report)
        context.close()
        browser.close()

    videos = sorted(video_dir.glob("*.webm"))
    require(bool(videos), "Playwright produced no live application video")
    report["video_file"] = str(videos[0].relative_to(ROOT))
    report["video_sha256"] = hashlib.sha256(videos[0].read_bytes()).hexdigest()
    checkpoint(report)
    print("HEALTHIA_LIVE_PRODUCT_FILM_PASS")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        failure = {}
        if REPORT.exists():
            try:
                failure = json.loads(REPORT.read_text(encoding="utf-8"))
            except Exception:
                pass
        failure.update({"status":"FAIL","error_type":type(exc).__name__,"error":str(exc)[:3000]})
        checkpoint(failure)
        print(f"HEALTHIA_LIVE_PRODUCT_FILM_FAIL {type(exc).__name__}: {exc}")
        raise
