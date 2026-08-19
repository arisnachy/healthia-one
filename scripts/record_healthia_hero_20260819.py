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


def read_secret_file(path_value: str, label: str) -> str:
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
              'max-width:min(700px,58vw)','background:rgba(5,14,27,.90)','color:white',
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


def wait_ms(page: Page, ms: int) -> None:
    page.wait_for_timeout(ms)


def api_post_json(page: Page, path: str) -> dict:
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


def wait_for_result_mission(page: Page, result_id: str, timeout_s: float = 55.0) -> dict:
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
            if last.get("status") == "completed":
                return last
        page.wait_for_timeout(500)
    raise RuntimeError(f"result mission did not complete: {last}")


def run_living_human_boundary(page: Page, access_key: str, report: dict) -> None:
    page.goto(f"{BASE_URL}/living", wait_until="networkidle", timeout=60_000)
    page.wait_for_selector("#accessForm", timeout=20_000)
    locked = page.request.get(
        f"{BASE_URL}/api/evaluation/state",
        headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
    )
    require(locked.status == 403, f"Living evaluator did not fail closed: {locked.status}")
    page.locator("#accessKey").fill(access_key)
    page.locator("#accessForm button[type='submit']").click()
    page.wait_for_selector("#controlPanel:not([hidden])", timeout=20_000)
    page.locator("#accessKey").evaluate("element => { element.value = ''; }")
    page.locator("#activateButton").click()
    page.wait_for_function("document.querySelector('#eventCount')?.textContent === '10 / 14'", timeout=35_000)
    page.wait_for_function("document.querySelector('#systemStatus')?.textContent === 'WAITING FOR HUMAN'", timeout=15_000)
    headline(
        page,
        "10 / 14 · WAITING FOR HUMAN",
        "The mission stops because the next fact belongs to a person, not to the model.",
    )
    wait_ms(page, 10_000)
    clear_headline(page)

    page.locator("#humanForm button[type='submit']").click()
    page.wait_for_function("document.querySelector('#eventCount')?.textContent === '14 / 14'", timeout=35_000)
    page.wait_for_function("document.querySelector('#twinVersion')?.textContent === 'v3'", timeout=15_000)
    page.wait_for_function("document.querySelector('#systemStatus')?.textContent === 'VERIFIED'", timeout=15_000)
    headline(
        page,
        "14 / 14 · TWIN v3 · VERIFIED",
        "A human evidence receipt resumes the same mission. This safety circuit uses zero model calls.",
    )
    wait_ms(page, 10_000)
    clear_headline(page)
    report["checks"].extend([
        "living_fails_closed_without_capability",
        "living_waiting_human_10_of_14",
        "living_human_receipt_14_of_14_twin_v3",
    ])
    checkpoint(report)


def show_one_safety(page: Page, report: dict) -> None:
    proof = json.loads(ONE_SAFETY_FILE.read_text(encoding="utf-8"))
    require(proof.get("status") == "PASS", "ONE SAFETY proof is not PASS")
    cloud = proof["enhanced_cloud_proof"]
    corr = cloud["correlation"]
    adversarial = cloud["application_adversarial_contract"]
    require(cloud.get("cloud_trace_exact_id_readback") is True, "Cloud Trace exact-id readback missing")
    require(adversarial.get("model_called") is False, "adversarial proof unexpectedly called model")
    require(adversarial.get("new_health_action_tickets") == 0, "blocked prompt minted action ticket")
    require(adversarial.get("patient_state_mutation") == 0, "blocked prompt mutated patient state")

    page.evaluate(
        """proof => {
          const old = document.getElementById('healthia-one-safety-proof');
          if (old) old.remove();
          const panel = document.createElement('section');
          panel.id = 'healthia-one-safety-proof';
          panel.style.cssText = [
            'position:fixed','inset:54px 70px','z-index:2147483646',
            'background:linear-gradient(145deg,rgba(5,15,29,.98),rgba(8,28,46,.98))',
            'border:1px solid #2f5677','border-radius:24px','color:#edf7ff',
            'padding:34px 38px','box-shadow:0 30px 90px rgba(0,0,0,.55)',
            'font-family:Inter,system-ui,sans-serif','overflow:hidden'
          ].join(';');
          const c = proof.enhanced_cloud_proof.correlation;
          const a = proof.enhanced_cloud_proof.application_adversarial_contract;
          panel.innerHTML = `
            <div style="font-size:13px;letter-spacing:.14em;color:#7dd3fc;font-weight:800">ONE SAFETY · MACHINE-READABLE FINAL PROOF</div>
            <h2 style="font-size:38px;margin:10px 0 8px">The model cannot declare success.</h2>
            <p style="font-size:18px;color:#c8d9e9;max-width:980px;margin:0 0 24px">Authorization and execution evidence are separate facts. Completion requires a real connector outcome and independent Cloud observability.</p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
              <div style="border:1px solid #294968;border-radius:16px;padding:20px;background:#071522">
                <div style="font-weight:800;color:#67e0a3;margin-bottom:14px">Guarded execution chain</div>
                <div style="font-size:17px;line-height:1.9">
                  <b>Trace</b> ${c.trace_id}<br>
                  ↓<br><b>HealthActionTicket</b> ${c.health_action_ticket_id}<br>
                  ↓<br><b>Connector</b> ${c.action}<br>
                  ↓<br><b>Receipt</b> ${c.receipt_id}<br>
                  ↓<br><b>Outcome</b> ${c.outcome_status}
                </div>
              </div>
              <div style="border:1px solid #5b4e2b;border-radius:16px;padding:20px;background:#19160c">
                <div style="font-weight:800;color:#ffd37d;margin-bottom:14px">Hostile prompt: fail closed</div>
                <div style="font-size:17px;line-height:2">
                  HTTP <b>${a.http_status}</b> at <b>${a.security_boundary}</b><br>
                  model_called = <b>${a.model_called}</b><br>
                  new HealthActionTickets = <b>${a.new_health_action_tickets}</b><br>
                  patient_state_mutation = <b>${a.patient_state_mutation}</b>
                </div>
              </div>
            </div>
            <div style="position:absolute;bottom:24px;right:30px;color:#7891a8;font-size:12px">Source: hackathon/evidence/one_safety_final_proof.json</div>`;
          document.body.appendChild(panel);
        }""",
        proof,
    )
    wait_ms(page, 24_000)
    page.evaluate("document.getElementById('healthia-one-safety-proof')?.remove()")
    report["one_safety"] = {
        "trace_id": corr["trace_id"],
        "ticket": corr["health_action_ticket_id"],
        "receipt": corr["receipt_id"],
        "action": corr["action"],
        "outcome": corr["outcome_status"],
        "blocked_http": adversarial["http_status"],
    }
    report["checks"].append("one_safety_machine_proof_visible")
    checkpoint(report)


def run() -> dict:
    global IDENTITY_TOKEN, JUDGE_TOKEN
    require(BASE_URL.startswith("https://") and ".run.app" in BASE_URL, "Cloud Run URL required")
    require(JUDGE_URL.startswith("https://") and ".run.app" in JUDGE_URL, "Judge Mode URL required")
    require(len(CANDIDATE_SHA) == 40, "candidate SHA must be exact")
    IDENTITY_TOKEN = read_secret_file(IDENTITY_TOKEN_FILE, "Cloud Run identity token")
    JUDGE_TOKEN = read_secret_file(JUDGE_TOKEN_FILE, "Judge Mode identity token")
    access_key = read_secret_file(EVALUATION_KEY_FILE, "evaluation capability")
    require(ONE_SAFETY_FILE.exists(), "ONE SAFETY proof file missing")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUTPUT / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = OUTPUT / "synthetic-hero-evidence.pdf"
    pdf_bytes = tiny_pdf()
    pdf_path.write_bytes(pdf_bytes)

    suffix = uuid4().hex[:10]
    email = f"hero-video-{suffix}@example.test"
    password = f"HealthIAHero!{suffix}Aa9"
    patient_name = "Synthetic Hero Patient"
    filename = pdf_path.name
    console_errors: list[str] = []
    page_errors: list[str] = []

    report = {
        "status": "running",
        "new_recording": True,
        "recycled_video_footage": False,
        "synthetic_only": True,
        "candidate_sha": CANDIDATE_SHA,
        "cloud_revision": CLOUD_REVISION,
        "base_url": BASE_URL,
        "judge_url": JUDGE_URL,
        "checks": [],
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
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
        )
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        # ACT I — the strongest mission first: unattended BP continuity.
        page.set_extra_http_headers({"Authorization": f"Bearer {JUDGE_TOKEN}"})
        proof_response = page.request.get(
            f"{JUDGE_URL}/api/proof",
            headers={"Authorization": f"Bearer {JUDGE_TOKEN}"},
        )
        require(proof_response.ok, f"Judge proof unavailable: {proof_response.status}")
        bp_proof = proof_response.json()
        require(bp_proof.get("boundary_count") == 5, f"unexpected BP proof: {bp_proof}")
        require(bp_proof.get("model_calls_for_trigger") == 0, "BP due trigger used a model call")
        page.goto(JUDGE_URL, wait_until="networkidle", timeout=60_000)
        body = page.locator("body").inner_text()
        require("HealthIA noticed the follow-up was overdue. Nobody prompted it." in body, "hero autonomy sentence missing")
        headline(
            page,
            "NOBODY PROMPTED IT.",
            "Promoted mission: opted-in blood-pressure measurement continuity.",
        )
        wait_ms(page, 10_000)
        clear_headline(page)
        page.locator(".grid").scroll_into_view_if_needed()
        wait_ms(page, 15_000)
        report["bp_proof"] = {
            "boundary_count": bp_proof.get("boundary_count"),
            "model_calls_for_trigger": bp_proof.get("model_calls_for_trigger"),
            "live_proof_run": bp_proof.get("live_proof_run"),
            "source_sha": bp_proof.get("source_sha"),
        }
        report["checks"].append("unattended_bp_live_judge_proof")
        checkpoint(report)

        # ACT II — exact candidate, real patient state.
        page.set_extra_http_headers({"Authorization": f"Bearer {IDENTITY_TOKEN}"})
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)
        page.wait_for_function("document.documentElement.lang === 'en'")
        headline(page, "THE RUNNING SYSTEM", "Exact candidate on Google Cloud · real browser interactions.")
        wait_ms(page, 5_000)
        clear_headline(page)

        page.locator("#registerTab").click()
        page.locator('#registerForm input[name="display_name"]').fill(patient_name)
        page.locator('#registerForm input[name="email"]').fill(email)
        page.locator('#registerForm input[name="password"]').fill(password)
        page.locator('#registerForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=30_000)
        page.wait_for_load_state("networkidle")
        session = api_json(page, "/api/auth/session")
        require(session.get("authenticated") is True, "synthetic patient registration failed")
        patient_id = str((session.get("account") or {}).get("patient_id") or "")
        readiness = api_json(page, "/api/readiness")
        require(readiness.get("model") == "gemini-3.5-flash", f"unexpected model: {readiness.get('model')}")
        require(readiness.get("adk_ready") is True, "Google ADK not ready")
        require(readiness.get("store_backend") == "firestore", "Firestore not active")
        require(readiness.get("evidence_backend") == "gcs", "GCS evidence backend not active")
        report["patient_id"] = patient_id
        report["readiness"] = {
            key: readiness.get(key)
            for key in ("model", "adk_ready", "store_backend", "evidence_backend", "release_sha")
        }
        report["checks"].append("exact_candidate_google_cloud_runtime")
        checkpoint(report)
        headline(
            page,
            "Gemini 3.5 Flash + Google ADK",
            "Firestore is canonical state. Private GCS preserves original evidence.",
        )
        wait_ms(page, 9_000)
        clear_headline(page)

        # Signal before chat.
        device_sync = api_post_json(page, "/api/demo/device-sync")
        require(int(device_sync.get("accepted") or 0) >= 3, f"device demo sync failed: {device_sync}")
        page.reload(wait_until="networkidle", timeout=60_000)
        page.locator('.main-nav [data-open="devices"]').click()
        page.wait_for_selector("#view-devices.is-active #deviceRoot .device-stats", timeout=20_000)
        device_state = api_json(page, "/api/devices")
        require(int(device_state.get("record_count") or 0) >= 3, "device records did not persist")
        headline(
            page,
            "THE PATIENT STORY CHANGED BEFORE CHAT",
            "Authorized Health Connect-style signals arrived with provenance and changed longitudinal state.",
        )
        wait_ms(page, 13_000)
        clear_headline(page)
        report["device_sync"] = {
            "accepted": device_sync.get("accepted"),
            "record_count": device_state.get("record_count"),
            "granted_metrics": device_sync.get("granted_metrics"),
        }
        report["checks"].append("signal_before_prompt_visible")
        checkpoint(report)

        # Evidence -> durable result mission -> patient record.
        page.locator('.main-nav [data-open="results"]').click()
        page.locator("#resultFile").set_input_files(str(pdf_path))
        _, result, document = latest_result_state(page, filename)
        result_id = str(result.get("id") or "")
        document_id = str(document.get("id") or "")
        mission = wait_for_result_mission(page, result_id)
        require(mission.get("status") == "completed", "result mission not completed")
        headline(
            page,
            "EVIDENCE → MISSION → PATIENT TWIN",
            "Original bytes first. Bounded Gemini extraction second. Durable mission completion only after evidence exists.",
        )
        wait_ms(page, 14_000)
        clear_headline(page)
        report["result"] = {
            "result_id": result_id,
            "document_id": document_id,
            "mission_id": mission.get("id"),
            "mission_status": mission.get("status"),
        }
        report["checks"].append("clinical_evidence_completed_result_mission")
        checkpoint(report)

        page.locator('.main-nav [data-open="timeline"]').click()
        page.wait_for_selector("#view-timeline.is-active #timelineRoot .timeline-event", timeout=20_000)
        require(page.locator("#timelineRoot .timeline-event").count() >= 3, "timeline is not populated")
        headline(page, "ONE LONGITUDINAL STORY", "Signals, evidence and work become one provenance-linked chronology.")
        wait_ms(page, 9_000)
        clear_headline(page)

        # Bounded adaptive reasoning.
        page.locator('.main-nav [data-open="chat"]').click()
        complaint = (
            "Since yesterday I have burning pain when I urinate and I need to go very often. "
            "Help me understand what information is still missing."
        )
        page.locator("#chatInput").fill(complaint)
        page.locator("#sendButton").click()
        assistant_id, status = wait_for_dynamic_or_orientation(page)
        require(status == "dynamic_clinical_questions", f"dynamic interview not produced: {status}")
        page.wait_for_selector('.clinical-question-block[data-question-source="gemini_dynamic"]', timeout=15_000)
        block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
        require(block.locator(".clinical-question").count() == 5, "dynamic block is not five questions")
        headline(
            page,
            "AI ASKS ONLY WHAT IS STILL MISSING",
            "A bounded Gemini + ADK block. JUDGE Ω policy rejects unsafe or repetitive plans.",
        )
        wait_ms(page, 15_000)
        clear_headline(page)
        report["checks"].append("live_dynamic_gemini_adk_interview")
        checkpoint(report)

        # Human authority boundary on the exact candidate.
        run_living_human_boundary(page, access_key, report)

        # Durable continuity after session end.
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
        require((restored.get("profile") or {}).get("id") == patient_id, "patient identity changed after login")
        require(any(item.get("id") == result_id for item in restored.get("results", [])), "result vanished after login")
        require(any(item.get("id") == document_id for item in restored.get("documents", [])), "document vanished after login")
        page.locator('.main-nav [data-open="record"]').click()
        page.wait_for_selector("#view-record.is-active #recordGrid .record-card", timeout=20_000)
        headline(
            page,
            "THE SESSION ENDED. THE PATIENT STORY DID NOT.",
            "The record is reconstructed from durable patient state, not from a long prompt.",
        )
        wait_ms(page, 11_000)
        clear_headline(page)
        page.locator('.main-nav [data-open="living"]').click()
        page.wait_for_selector("#view-living.is-active .living-surface", timeout=20_000)
        report["checks"].append("logout_login_restores_longitudinal_state")
        checkpoint(report)

        # ONE SAFETY is the technological signature.
        show_one_safety(page, report)

        # Final product surface.
        page.locator('.main-nav [data-open="living"]').click()
        page.wait_for_selector("#view-living.is-active .living-surface", timeout=20_000)
        headline(
            page,
            "HEALTHIA ONE",
            "Patient-owned continuity · bounded AI reasoning · human authority · verifiable action.",
        )
        wait_ms(page, 16_000)
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
    require(bool(videos), "Playwright did not produce video")
    raw = videos[0]
    report["video_file"] = str(raw.relative_to(ROOT))
    report["video_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    checkpoint(report)
    print("HEALTHIA_HERO_RECORDING_PASS")
    print(json.dumps({
        "status": report["status"],
        "checks": len(report["checks"]),
        "video": report["video_file"],
        "sha256": report["video_sha256"],
    }))
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
                failure = {}
        failure.update({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:4000]})
        REPORT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_HERO_RECORDING_FAIL {type(exc).__name__}: {exc}")
        raise
