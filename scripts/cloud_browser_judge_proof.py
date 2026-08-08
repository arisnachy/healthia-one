from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "cloud-browser-judge-proof"
REPORT = OUTPUT / "report.json"
BASE_URL = os.getenv("HEALTHIA_CLOUD_URL", "").rstrip("/")
IDENTITY_TOKEN = os.getenv("HEALTHIA_CLOUD_ID_TOKEN", "")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def tiny_pdf() -> bytes:
    text = "SYNTHETIC BROWSER JUDGE LAB - Glucose 103 mg/dL - Hemoglobin 14.1 g/dL"
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>endobj\n",
        b"4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
        b"5 0 obj<< /Length " + str(len(stream)).encode() + b" >>stream\n" + stream + b"\nendstream endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(f"trailer<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(out)


def api_json(page: Page, path: str) -> dict:
    return page.evaluate(
        """async path => {
          const r = await fetch(path, {credentials:'same-origin'});
          let body = {};
          try { body = await r.json(); } catch (_) {}
          if (!r.ok) throw new Error(`${path} HTTP ${r.status}: ${JSON.stringify(body)}`);
          return body;
        }""",
        path,
    )


def screenshot(page: Page, name: str) -> None:
    page.screenshot(path=str(OUTPUT / name), full_page=True)


def answer_visible_block(page: Page) -> None:
    block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
    require(block.locator(".clinical-question").count() == 5, "dynamic clinical block is not exactly five questions")
    for field in block.locator(".clinical-question").all():
        field.locator(".clinical-option").first.click()
    block.locator(".clinical-submit").click()


def latest_assistant(page: Page) -> tuple[str, str]:
    state = api_json(page, "/api/bootstrap")
    assistants = [item for item in state.get("messages", []) if item.get("role") == "assistant"]
    if not assistants:
        return "", ""
    latest = assistants[-1]
    return str(latest.get("id") or ""), str((latest.get("metadata") or {}).get("llm_status") or "")


def wait_for_dynamic_or_orientation(page: Page, previous_id: str = "", timeout_s: float = 70.0) -> tuple[str, str]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        message_id, status = latest_assistant(page)
        if message_id and message_id != previous_id and status in {"dynamic_clinical_questions", "dynamic_clinical_followup_questions", "clinical_ai_orientation_completed"}:
            return message_id, status
        page.wait_for_timeout(500)
    raise RuntimeError("clinical AI did not produce a new dynamic block or final orientation in time")


def run() -> dict:
    require(BASE_URL.startswith("https://"), "HEALTHIA_CLOUD_URL must be the real HTTPS Cloud Run URL")
    require(bool(IDENTITY_TOKEN), "HEALTHIA_CLOUD_ID_TOKEN is required")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pdf_path = OUTPUT / "browser-judge-synthetic-lab.pdf"
    pdf = tiny_pdf()
    pdf_path.write_bytes(pdf)

    suffix = uuid4().hex[:10]
    email = f"browser-judge-{suffix}@example.test"
    password = f"BrowserJudge!{suffix}Aa9"
    display_name = "Paciente Browser Judge"
    filename = pdf_path.name
    console_errors: list[str] = []
    page_errors: list[str] = []
    report: dict = {
        "status": "running",
        "base_url": BASE_URL,
        "synthetic_only": True,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "checks": [],
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(OUTPUT / "video"),
            record_video_size={"width": 1600, "height": 900},
            extra_http_headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
        )
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)
        require(page.locator("#registerTab").is_visible(), "registration UI is not visible")
        screenshot(page, "01-login.png")
        page.locator("#registerTab").click()
        page.locator('#registerForm input[name="display_name"]').fill(display_name)
        page.locator('#registerForm input[name="email"]').fill(email)
        page.locator('#registerForm input[name="password"]').fill(password)
        page.locator('#registerForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=30_000)
        page.wait_for_load_state("networkidle")
        session = api_json(page, "/api/auth/session")
        require(session.get("authenticated") is True, "browser registration did not create an authenticated session")
        patient_id = str((session.get("account") or {}).get("patient_id") or "")
        require(patient_id.startswith("patient_"), "browser session has no patient identity")
        report["patient_id"] = patient_id
        report["checks"].append("secure_browser_registration_and_session")
        require(page.locator("#accountPill strong").inner_text().strip() == display_name, "account pill did not render authenticated identity")
        readiness_before = api_json(page, "/api/readiness")
        runtime_label = page.locator("#runtimeLabel").inner_text().strip()
        require(readiness_before.get("ai_ready") is True, "Cloud browser started without live Google AI readiness")
        require(readiness_before.get("model") == "gemini-3.5-flash", f"unexpected browser model: {readiness_before.get('model')}")
        require("falta" not in runtime_label.lower() and "no disponible" not in runtime_label.lower(), f"runtime label contradicts live AI readiness: {runtime_label}")
        require("vertex" in runtime_label.lower() or "google ai" in runtime_label.lower(), f"runtime label does not expose active Google AI transport: {runtime_label}")
        report["runtime_label"] = runtime_label
        report["checks"].append("browser_runtime_label_matches_live_vertex_readiness")
        screenshot(page, "02-authenticated-home.png")

        page.locator("#accountPill").click()
        page.wait_for_selector("#accountDialog[open]", timeout=10_000)
        account_identity = page.locator("#accountIdentity").inner_text()
        require(email in account_identity, "account settings did not show authenticated email")
        require(display_name in account_identity, "account settings did not show authenticated display name")
        report["checks"].append("account_settings_dialog")
        screenshot(page, "03-account-settings.png")
        page.locator("#closeAccountButton").click()

        complaint = "Desde ayer me arde al orinar y tengo que ir al baño a cada rato. Quiero orientación sobre qué información hace falta."
        page.locator("#chatInput").fill(complaint)
        page.locator("#sendButton").click()
        assistant_id, status = wait_for_dynamic_or_orientation(page)
        require(status == "dynamic_clinical_questions", f"first clinical response was not a live dynamic question block: {status}")
        page.wait_for_selector('.clinical-question-block[data-question-source="gemini_dynamic"]', timeout=10_000)
        first_block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
        require(first_block.locator(".clinical-question").count() == 5, "first live Gemini block does not have five questions")
        badge = first_block.locator(".clinical-source.is-dynamic").inner_text().strip()
        require(badge == "Preguntas creadas para este caso · Gemini + ADK", f"live source badge mismatch: {badge}")
        report["checks"].append("live_gemini_adk_first_five_question_block")
        screenshot(page, "04-live-question-block-1.png")
        answer_visible_block(page)

        assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        require(status in {"dynamic_clinical_questions", "dynamic_clinical_followup_questions"}, f"second response did not preserve live adaptive questioning: {status}")
        page.wait_for_timeout(500)
        second_block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
        require(second_block.locator(".clinical-question").count() == 5, "second live Gemini block does not have five questions")
        report["checks"].append("live_gemini_adk_second_five_question_block")
        screenshot(page, "05-live-question-block-2.png")
        answer_visible_block(page)

        assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        if status in {"dynamic_clinical_questions", "dynamic_clinical_followup_questions"}:
            page.wait_for_timeout(500)
            third_block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
            require(third_block.locator(".clinical-question").count() == 5, "AI-requested third block is malformed")
            screenshot(page, "06-live-question-block-3.png")
            answer_visible_block(page)
            assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        require(status == "clinical_ai_orientation_completed", f"Gemini did not close with clinical orientation: {status}")
        report["checks"].append("live_gemini_selected_clinical_orientation")
        screenshot(page, "07-live-clinical-orientation.png")

        page.locator('#resultFile').set_input_files(str(pdf_path))
        deadline = time.time() + 70
        result = None
        while time.time() < deadline:
            state = api_json(page, "/api/bootstrap")
            candidates = [item for item in state.get("results", []) if item.get("source_filename") == filename or item.get("filename") == filename]
            if not candidates:
                candidates = [item for item in state.get("results", []) if filename in json.dumps(item, ensure_ascii=False)]
            if candidates:
                result = candidates[-1]
                result_id_candidate = str(result.get("id") or "")
                document_candidate = next(
                    (item for item in state.get("documents", []) if item.get("related_result_id") == result_id_candidate),
                    None,
                )
                if result.get("status") == "parsed" and result_id_candidate and document_candidate:
                    break
            page.wait_for_timeout(750)
        require(result is not None and result.get("status") == "parsed", f"browser PDF did not become a parsed multimodal result: {result}")
        result_id = str(result.get("id") or "")
        document = next(
            (item for item in state.get("documents", []) if item.get("related_result_id") == result_id),
            None,
        )
        document_id = str((document or {}).get("id") or "")
        require(result_id and document_id, "browser PDF result lacks canonical result/original provenance")
        report["result_id"] = result_id
        report["document_id"] = document_id
        report["checks"].append("browser_multimodal_pdf_result_with_original_provenance")
        page.locator('[data-open="results"]').click()
        page.wait_for_timeout(700)
        screenshot(page, "08-persisted-result.png")

        page.locator('.main-nav [data-open="chat"]').click()
        page.locator("#chatInput").fill(f"Explícame el resultado {filename} que acabo de subir y confirma que quedó guardado.")
        page.locator("#sendButton").click()
        deadline = time.time() + 50
        mission = None
        while time.time() < deadline:
            state = api_json(page, "/api/bootstrap")
            matches = [m for m in state.get("missions", []) if m.get("mission_type") == "result_explanation" and result_id in (m.get("evidence_ids") or [])]
            if matches:
                mission = matches[-1]
                if mission.get("status") == "completed":
                    break
            page.wait_for_timeout(650)
        require(mission is not None and mission.get("status") == "completed", f"browser Taskmaster result mission did not complete: {mission}")
        require(document_id in (mission.get("evidence_ids") or []), "completed browser mission lost original document provenance")
        report["mission_id"] = mission.get("id")
        report["checks"].append("browser_taskmaster_result_mission_completed")
        page.locator('[data-open="missions"]').click()
        page.wait_for_timeout(700)
        screenshot(page, "09-completed-mission.png")

        page.locator("#accountPill").click()
        page.locator("#logoutButton").click()
        page.wait_for_url(f"{BASE_URL}/login", timeout=20_000)
        report["checks"].append("browser_logout")
        page.locator('#loginForm input[name="email"]').fill(email)
        page.locator('#loginForm input[name="password"]').fill(password)
        page.locator('#loginForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=20_000)
        page.wait_for_load_state("networkidle")
        restored = api_json(page, "/api/bootstrap")
        require((restored.get("profile") or {}).get("id") == patient_id, "patient identity changed after browser relogin")
        require(any(item.get("id") == result_id for item in restored.get("results", [])), "result disappeared after browser relogin")
        require(any(item.get("id") == document_id for item in restored.get("documents", [])), "original document metadata disappeared after browser relogin")
        require(any(item.get("id") == mission.get("id") and item.get("status") == "completed" for item in restored.get("missions", [])), "completed mission disappeared after browser relogin")
        report["checks"].append("browser_relogin_restores_result_document_and_completed_mission")
        screenshot(page, "10-relogin-continuity.png")

        readiness = api_json(page, "/api/readiness")
        require(readiness.get("ready") is True, "Cloud readiness false during browser proof")
        require(readiness.get("model") == "gemini-3.5-flash", f"unexpected Cloud model: {readiness.get('model')}")
        require(readiness.get("store_backend") == "firestore" and readiness.get("evidence_backend") == "gcs", "browser proof did not run against Firestore + GCS")
        require(readiness.get("adk_ready") is True and readiness.get("ai_ready") is True, "browser proof did not run with live ADK/AI")
        report["readiness"] = {key: readiness.get(key) for key in ("ready", "llm_backend", "model", "adk_ready", "ai_ready", "store_backend", "evidence_backend", "auth_required", "patient_session_persistence")}
        report["checks"].append("cloud_readiness_vertex_adk_firestore_gcs")

        require(not page_errors, f"browser page errors: {page_errors}")
        require(not console_errors, f"browser console errors: {console_errors}")
        report["checks"].append("zero_browser_console_or_page_errors")
        report["status"] = "PASS"
        context.close()
        browser.close()

    videos = sorted((OUTPUT / "video").glob("*.webm"))
    require(bool(videos), "Playwright did not produce a browser video")
    report["video_file"] = str(videos[0].relative_to(ROOT))
    report["video_sha256"] = hashlib.sha256(videos[0].read_bytes()).hexdigest()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("HEALTHIA_CLOUD_BROWSER_JUDGE_PROOF_PASS")
    print(json.dumps({"status": report["status"], "checks": report["checks"], "patient_id": patient_id, "result_id": report["result_id"], "mission_id": report["mission_id"], "video_sha256": report["video_sha256"]}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        failure = {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:2000]}
        REPORT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_CLOUD_BROWSER_JUDGE_PROOF_FAIL {type(exc).__name__}: {exc}")
        raise
