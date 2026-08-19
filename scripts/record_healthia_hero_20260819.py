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
OUTPUT = ROOT / "dist" / "healthia-hero-video"
REPORT = OUTPUT / "recording-report.json"
BASE_URL = os.getenv("HEALTHIA_CLOUD_URL", "").rstrip("/")
JUDGE_URL = os.getenv("HEALTHIA_JUDGE_URL", "").rstrip("/")
CANDIDATE_SHA = os.getenv("HEALTHIA_CANDIDATE_SHA", "")
CLOUD_REVISION = os.getenv("HEALTHIA_CLOUD_REVISION", "")
IDENTITY_TOKEN_FILE = os.getenv("HEALTHIA_CLOUD_ID_TOKEN_FILE", "")
JUDGE_TOKEN_FILE = os.getenv("HEALTHIA_JUDGE_ID_TOKEN_FILE", "")
EVALUATION_KEY_FILE = os.getenv("HEALTHIA_EVALUATION_ACCESS_KEY_FILE", "")
ONE_SAFETY_FILE = ROOT / "hackathon" / "evidence" / "one_safety_final_proof.json"
IDENTITY_TOKEN = ""
JUDGE_TOKEN = ""


def secret(path_value: str, label: str) -> str:
    require(bool(path_value), f"{label} file is required")
    value = Path(path_value).read_text(encoding="utf-8").strip()
    require(bool(value), f"{label} file is empty")
    return value


def checkpoint(report: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def headline(page: Page, title: str, subtitle: str = "") -> None:
    page.evaluate(
        """({title, subtitle}) => {
          let box = document.getElementById('healthia-hero-headline');
          if (!box) {
            box = document.createElement('aside');
            box.id = 'healthia-hero-headline';
            box.style.cssText = [
              'position:fixed','left:28px','top:24px','z-index:2147483647',
              'max-width:min(720px,60vw)','background:rgba(5,14,27,.91)','color:white',
              'border:1px solid rgba(103,183,255,.52)','border-radius:16px','padding:13px 17px',
              'box-shadow:0 18px 50px rgba(0,0,0,.30)','font-family:Inter,system-ui,sans-serif',
              'pointer-events:none','backdrop-filter:blur(8px)'
            ].join(';');
            document.body.appendChild(box);
          }
          box.innerHTML = `<strong style="font-size:22px;display:block;line-height:1.15">${title}</strong>` +
            (subtitle ? `<span style="display:block;margin-top:5px;font-size:13px;line-height:1.4;color:#cfe3f8">${subtitle}</span>` : '');
        }""",
        {"title": title, "subtitle": subtitle},
    )


def clear_headline(page: Page) -> None:
    page.evaluate("document.getElementById('healthia-hero-headline')?.remove()")


def linger(page: Page, seconds: float) -> None:
    page.wait_for_timeout(int(seconds * 1000))


def api_post(page: Page, path: str) -> dict:
    return page.evaluate(
        """async path => {
          const r = await fetch(path, {method:'POST', credentials:'same-origin'});
          let body = {};
          try { body = await r.json(); } catch (_) {}
          if (!r.ok) throw new Error(`${path} HTTP ${r.status}: ${JSON.stringify(body)}`);
          return body;
        }""",
        path,
    )


def latest_assistant(page: Page) -> dict:
    state = api_json(page, "/api/bootstrap")
    messages = [item for item in state.get("messages", []) if item.get("role") == "assistant"]
    return messages[-1] if messages else {}


def send_chat(page: Page, text: str) -> None:
    page.locator("#chatInput").fill(text)
    page.locator("#sendButton").click()


def wait_new_assistant(page: Page, previous_id: str, timeout_s: float = 90.0) -> dict:
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        last = latest_assistant(page)
        if last.get("id") and str(last.get("id")) != previous_id:
            return last
        page.wait_for_timeout(400)
    raise RuntimeError(f"assistant did not answer: {last}")


def latest_result_state(page: Page, filename: str, timeout_s: float = 85.0) -> tuple[dict, dict, dict]:
    deadline = time.time() + timeout_s
    last_state: dict = {}
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        last_state = state
        candidates = [
            item for item in state.get("results", [])
            if item.get("filename") == filename or filename in json.dumps(item, ensure_ascii=False)
        ]
        if candidates:
            result = candidates[-1]
            result_id = str(result.get("id") or "")
            document = next(
                (item for item in state.get("documents", []) if item.get("related_result_id") == result_id),
                None,
            )
            if result.get("status") == "parsed" and result_id and document:
                return state, result, document
        page.wait_for_timeout(500)
    raise RuntimeError(f"clinical evidence did not become durable: {last_state.get('results', [])[-2:]}")


def wait_result_mission(page: Page, result_id: str, document_id: str, timeout_s: float = 60.0) -> dict:
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        matches = [
            mission for mission in state.get("missions", [])
            if mission.get("mission_type") == "result_explanation"
            and result_id in (mission.get("evidence_ids") or [])
        ]
        if matches:
            last = matches[-1]
            evidence_ids = set(last.get("evidence_ids") or [])
            if last.get("status") == "completed" and document_id in evidence_ids:
                return last
        page.wait_for_timeout(500)
    raise RuntimeError(f"evidence-backed result mission did not complete: {last}")


def living_human_boundary(page: Page, access_key: str, report: dict) -> None:
    page.goto(f"{BASE_URL}/living", wait_until="networkidle", timeout=60_000)
    page.wait_for_selector("#accessForm", timeout=20_000)
    locked = page.request.get(
        f"{BASE_URL}/api/evaluation/state",
        headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
    )
    require(locked.status == 403, f"Living evaluator did not fail closed: HTTP {locked.status}")
    page.locator("#accessKey").fill(access_key)
    page.locator("#accessForm button[type='submit']").click()
    page.wait_for_selector("#controlPanel:not([hidden])", timeout=20_000)
    page.locator("#accessKey").evaluate("element => { element.value = ''; }")
    page.locator("#activateButton").click()
    page.wait_for_function("document.querySelector('#eventCount')?.textContent === '10 / 14'", timeout=35_000)
    page.wait_for_function("document.querySelector('#systemStatus')?.textContent === 'WAITING FOR HUMAN'", timeout=15_000)
    headline(page, "10 / 14 · WAITING FOR HUMAN", "The next fact belongs to a person, not to the model.")
    linger(page, 9)
    clear_headline(page)

    page.locator("#humanForm button[type='submit']").click()
    page.wait_for_function("document.querySelector('#eventCount')?.textContent === '14 / 14'", timeout=35_000)
    page.wait_for_function("document.querySelector('#twinVersion')?.textContent === 'v3'", timeout=15_000)
    page.wait_for_function("document.querySelector('#systemStatus')?.textContent === 'VERIFIED'", timeout=15_000)
    headline(page, "14 / 14 · TWIN v3 · VERIFIED", "A human evidence receipt resumes the same mission. Zero model calls in this safety circuit.")
    linger(page, 9)
    clear_headline(page)
    report["checks"].extend([
        "living_fails_closed_without_capability",
        "living_waiting_human_10_of_14",
        "living_human_receipt_14_of_14_twin_v3",
    ])
    checkpoint(report)


def one_safety(page: Page, report: dict) -> None:
    proof = json.loads(ONE_SAFETY_FILE.read_text(encoding="utf-8"))
    require(proof.get("status") == "PASS", "ONE SAFETY proof is not PASS")
    cloud = proof["enhanced_cloud_proof"]
    corr = cloud["correlation"]
    hostile = cloud["application_adversarial_contract"]
    require(cloud.get("cloud_trace_exact_id_readback") is True, "exact Trace readback missing")
    require(hostile.get("model_called") is False, "hostile request reached model")
    require(hostile.get("new_health_action_tickets") == 0, "hostile request minted action ticket")
    require(hostile.get("patient_state_mutation") == 0, "hostile request mutated patient state")
    page.evaluate(
        """proof => {
          document.getElementById('healthia-safety-proof')?.remove();
          const p=document.createElement('section');
          p.id='healthia-safety-proof';
          p.style.cssText=['position:fixed','inset:52px 66px','z-index:2147483646',
            'background:linear-gradient(145deg,rgba(5,15,29,.985),rgba(8,28,46,.985))',
            'border:1px solid #2f5677','border-radius:24px','color:#edf7ff','padding:34px 38px',
            'box-shadow:0 30px 90px rgba(0,0,0,.58)','font-family:Inter,system-ui,sans-serif'].join(';');
          const c=proof.enhanced_cloud_proof.correlation;
          const a=proof.enhanced_cloud_proof.application_adversarial_contract;
          p.innerHTML=`<div style="font-size:13px;letter-spacing:.14em;color:#7dd3fc;font-weight:800">ONE SAFETY · FINAL MACHINE PROOF</div>
            <h2 style="font-size:38px;margin:10px 0 8px">The model cannot declare success.</h2>
            <p style="font-size:18px;color:#c8d9e9;max-width:980px;margin:0 0 22px">Authorization is not execution evidence. Completion requires a real connector outcome and independent cloud observability.</p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
              <div style="border:1px solid #294968;border-radius:16px;padding:20px;background:#071522;font-size:16px;line-height:1.85">
                <b style="color:#67e0a3">Guarded execution chain</b><br><br>
                Trace ${c.trace_id}<br>↓<br>Ticket ${c.health_action_ticket_id}<br>↓<br>${c.action}<br>↓<br>Receipt ${c.receipt_id}<br>↓<br><b>${c.outcome_status}</b>
              </div>
              <div style="border:1px solid #5b4e2b;border-radius:16px;padding:20px;background:#19160c;font-size:16px;line-height:2">
                <b style="color:#ffd37d">Hostile prompt · fail closed</b><br><br>
                HTTP <b>${a.http_status}</b> at ${a.security_boundary}<br>model_called = <b>${a.model_called}</b><br>new tickets = <b>${a.new_health_action_tickets}</b><br>patient mutation = <b>${a.patient_state_mutation}</b>
              </div>
            </div>
            <div style="position:absolute;bottom:20px;right:28px;font-size:12px;color:#7891a8">hackathon/evidence/one_safety_final_proof.json</div>`;
          document.body.appendChild(p);
        }""",
        proof,
    )
    linger(page, 22)
    page.evaluate("document.getElementById('healthia-safety-proof')?.remove()")
    report["one_safety"] = {
        "trace_id": corr["trace_id"],
        "ticket": corr["health_action_ticket_id"],
        "action": corr["action"],
        "receipt": corr["receipt_id"],
        "outcome": corr["outcome_status"],
    }
    report["checks"].append("one_safety_machine_proof_visible")
    checkpoint(report)


def run() -> dict:
    global IDENTITY_TOKEN, JUDGE_TOKEN
    require(BASE_URL.startswith("https://") and ".run.app" in BASE_URL, "private Cloud Run URL required")
    require(JUDGE_URL.startswith("https://") and ".run.app" in JUDGE_URL, "Judge Mode URL required")
    require(len(CANDIDATE_SHA) == 40, "exact candidate SHA required")
    require(ONE_SAFETY_FILE.exists(), "ONE SAFETY proof missing")
    IDENTITY_TOKEN = secret(IDENTITY_TOKEN_FILE, "Cloud Run token")
    JUDGE_TOKEN = secret(JUDGE_TOKEN_FILE, "Judge Mode token")
    access_key = secret(EVALUATION_KEY_FILE, "evaluation capability")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUTPUT / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = OUTPUT / "synthetic-hero-evidence.pdf"
    pdf = tiny_pdf()
    pdf_path.write_bytes(pdf)
    filename = pdf_path.name
    suffix = uuid4().hex[:10]
    email = f"hero-{suffix}@example.test"
    password = f"HealthIAHero!{suffix}Aa9"
    patient_name = "Synthetic Hero Patient"
    console_errors: list[str] = []
    page_errors: list[str] = []
    started = time.monotonic()
    report: dict = {
        "status": "running",
        "new_recording": True,
        "recycled_video_footage": False,
        "synthetic_only": True,
        "candidate_sha": CANDIDATE_SHA,
        "cloud_revision": CLOUD_REVISION,
        "checks": [],
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
    }
    checkpoint(report)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(locale="en-US", viewport={"width":1600,"height":900}, record_video_dir=str(video_dir), record_video_size={"width":1600,"height":900})
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        # ACT I: real promoted unattended BP continuity proof first.
        page.set_extra_http_headers({"Authorization": f"Bearer {JUDGE_TOKEN}"})
        proof_response = page.request.get(f"{JUDGE_URL}/api/proof", headers={"Authorization": f"Bearer {JUDGE_TOKEN}"})
        require(proof_response.ok, f"Judge proof HTTP {proof_response.status}")
        bp = proof_response.json()
        require(bp.get("boundary_count") == 5, f"unexpected BP proof: {bp}")
        require(bp.get("model_calls_for_trigger") == 0, "BP due trigger used a model call")
        page.goto(JUDGE_URL, wait_until="networkidle", timeout=60_000)
        require("HealthIA noticed the follow-up was overdue. Nobody prompted it." in page.locator("body").inner_text(), "unattended hero sentence missing")
        headline(page, "NOBODY PROMPTED IT.", "An opted-in blood-pressure follow-up became durable work on its own.")
        linger(page, 10)
        clear_headline(page)
        page.locator(".grid").scroll_into_view_if_needed()
        linger(page, 14)
        report["bp_proof"] = {k: bp.get(k) for k in ("boundary_count","model_calls_for_trigger","source_sha","live_proof_run")}
        report["checks"].append("unattended_bp_live_judge_proof")
        checkpoint(report)

        # ACT II: brand-new exact-candidate browser capture.
        page.set_extra_http_headers({"Authorization": f"Bearer {IDENTITY_TOKEN}"})
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)
        page.wait_for_function("document.documentElement.lang === 'en'")
        headline(page, "THE RUNNING SYSTEM", "A new capture of the exact branch deployed to Google Cloud.")
        linger(page, 5)
        clear_headline(page)
        page.locator("#registerTab").click()
        page.locator('#registerForm input[name="display_name"]').fill(patient_name)
        page.locator('#registerForm input[name="email"]').fill(email)
        page.locator('#registerForm input[name="password"]').fill(password)
        page.locator('#registerForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=30_000)
        page.wait_for_load_state("networkidle")
        session = api_json(page, "/api/auth/session")
        require(session.get("authenticated") is True, "registration failed")
        patient_id = str((session.get("account") or {}).get("patient_id") or "")
        readiness = api_json(page, "/api/readiness")
        require(readiness.get("model") == "gemini-3.5-flash", f"unexpected model {readiness.get('model')}")
        require(readiness.get("adk_ready") is True, "ADK not ready")
        require(readiness.get("store_backend") == "firestore", "Firestore not active")
        require(readiness.get("evidence_backend") == "gcs", "GCS evidence not active")
        report["patient_id"] = patient_id
        report["readiness"] = {k: readiness.get(k) for k in ("model","adk_ready","store_backend","evidence_backend","release_sha")}
        report["checks"].append("exact_candidate_google_cloud_runtime")
        checkpoint(report)
        headline(page, "GEMINI 3.5 FLASH + GOOGLE ADK", "Firestore is canonical state. Private GCS preserves original evidence.")
        linger(page, 9)
        clear_headline(page)

        # Signal reaches state before any chat request.
        sync = api_post(page, "/api/demo/device-sync")
        require(int(sync.get("accepted") or 0) >= 3, f"device sync failed: {sync}")
        page.reload(wait_until="networkidle", timeout=60_000)
        page.locator('.main-nav [data-open="devices"]').click()
        page.wait_for_selector("#view-devices.is-active #deviceRoot .device-stats", timeout=20_000)
        device_state = api_json(page, "/api/devices")
        require(int(device_state.get("record_count") or 0) >= 3, "device records did not persist")
        headline(page, "THE PATIENT STORY CHANGED BEFORE CHAT", "Authorized signals arrived with provenance and changed longitudinal state.")
        linger(page, 12)
        clear_headline(page)
        report["checks"].append("signal_before_prompt_visible")
        checkpoint(report)

        # Evidence first, then an explicit patient request creates/completes the result mission.
        page.locator('.main-nav [data-open="results"]').click()
        page.locator("#resultFile").set_input_files(str(pdf_path))
        _, result, document = latest_result_state(page, filename)
        result_id = str(result.get("id") or "")
        document_id = str(document.get("id") or "")
        require(result_id and document_id, "result provenance missing")
        headline(page, "EVIDENCE FIRST", "Original bytes are preserved before bounded Gemini interpretation.")
        linger(page, 8)
        clear_headline(page)

        page.locator('.main-nav [data-open="chat"]').click()
        before = latest_assistant(page)
        send_chat(page, f"Explain the result {filename} I just uploaded and confirm that it was saved with the original file.")
        wait_new_assistant(page, str(before.get("id") or ""), timeout_s=100.0)
        mission = wait_result_mission(page, result_id, document_id)
        headline(page, "EVIDENCE → DURABLE MISSION → PATIENT RECORD", "The explanation mission closes only after the persisted result and original document are correlated.")
        linger(page, 12)
        clear_headline(page)
        report["result"] = {"result_id":result_id,"document_id":document_id,"mission_id":mission.get("id"),"mission_status":mission.get("status")}
        report["checks"].append("clinical_evidence_completed_result_mission")
        checkpoint(report)

        page.locator('.main-nav [data-open="timeline"]').click()
        page.wait_for_selector("#view-timeline.is-active #timelineRoot .timeline-event", timeout=20_000)
        require(page.locator("#timelineRoot .timeline-event").count() >= 3, "timeline not populated")
        headline(page, "ONE LONGITUDINAL STORY", "Signals, evidence and completed work become one provenance-linked chronology.")
        linger(page, 8)
        clear_headline(page)

        # Show real bounded reasoning, not a fixed questionnaire.
        page.locator('.main-nav [data-open="chat"]').click()
        complaint = "Since yesterday I have burning pain when I urinate and I need to go very often. Help me understand what information is still missing."
        page.locator("#chatInput").fill(complaint)
        page.locator("#sendButton").click()
        _, status = wait_for_dynamic_or_orientation(page)
        require(status == "dynamic_clinical_questions", f"no dynamic block: {status}")
        page.wait_for_selector('.clinical-question-block[data-question-source="gemini_dynamic"]', timeout=15_000)
        block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
        require(block.locator(".clinical-question").count() == 5, "dynamic Gemini block is malformed")
        headline(page, "AI ASKS ONLY WHAT IS STILL MISSING", "A bounded five-question Gemini + ADK block. Unsafe or repetitive plans fail a deterministic gate.")
        linger(page, 14)
        clear_headline(page)
        report["checks"].append("live_dynamic_gemini_adk_interview")
        checkpoint(report)

        # Exact human authority boundary.
        living_human_boundary(page, access_key, report)

        # Session ends; state survives.
        page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=60_000)
        page.locator("#accountPill").click()
        page.locator("#logoutButton").click()
        page.wait_for_url(f"{BASE_URL}/login", timeout=20_000)
        page.locator('#loginForm input[name="email"]').fill(email)
        page.locator('#loginForm input[name="password"]').fill(password)
        page.locator('#loginForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=20_000)
        page.wait_for_load_state("networkidle")
        restored = api_json(page, "/api/bootstrap")
        require((restored.get("profile") or {}).get("id") == patient_id, "patient identity changed")
        require(any(item.get("id") == result_id for item in restored.get("results", [])), "result vanished")
        require(any(item.get("id") == document_id for item in restored.get("documents", [])), "document vanished")
        require(any(item.get("id") == mission.get("id") for item in restored.get("missions", [])), "mission vanished")
        page.locator('.main-nav [data-open="record"]').click()
        page.wait_for_selector("#view-record.is-active #recordGrid .record-card", timeout=20_000)
        headline(page, "THE SESSION ENDED. THE PATIENT STORY DID NOT.", "HealthIA reconstructs the patient from durable state, not a long chat prompt.")
        linger(page, 10)
        clear_headline(page)
        report["checks"].append("logout_login_restores_longitudinal_state")
        checkpoint(report)

        # Technological signature: machine-readable ONE SAFETY proof.
        page.locator('.main-nav [data-open="living"]').click()
        page.wait_for_selector("#view-living.is-active .living-surface", timeout=20_000)
        one_safety(page, report)

        headline(page, "HEALTHIA ONE", "Patient-owned continuity · bounded AI · human authority · verifiable action.")
        linger(page, 15)
        clear_headline(page)

        require(not page_errors, f"browser page errors: {page_errors}")
        require(not console_errors, f"browser console errors: {console_errors}")
        report["checks"].append("zero_browser_console_or_page_errors")
        report["status"] = "PASS"
        report["raw_elapsed_seconds"] = round(time.monotonic() - started, 2)
        checkpoint(report)
        context.close()
        browser.close()

    videos = sorted(video_dir.glob("*.webm"))
    require(bool(videos), "Playwright did not produce a new video")
    video = videos[0]
    report["video_file"] = str(video.relative_to(ROOT))
    report["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    checkpoint(report)
    print("HEALTHIA_HERO_RECORDING_PASS")
    print(json.dumps({"status":report["status"],"checks":len(report["checks"]),"video":report["video_file"],"sha256":report["video_sha256"]}))
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        failure: dict = {}
        if REPORT.exists():
            try:
                failure = json.loads(REPORT.read_text(encoding="utf-8"))
            except Exception:
                failure = {}
        failure.update({"status":"FAIL","error_type":type(exc).__name__,"error":str(exc)[:4000]})
        REPORT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_HERO_RECORDING_FAIL {type(exc).__name__}: {exc}")
        raise
