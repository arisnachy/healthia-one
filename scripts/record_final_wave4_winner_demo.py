from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright

from cloud_browser_judge_proof import api_json, require, tiny_pdf


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "final-live-english-demo"
REPORT = OUTPUT / "report.json"
BASE_URL = os.getenv("HEALTHIA_CLOUD_URL", "").rstrip("/")
IDENTITY_TOKEN = ""
CANDIDATE_SHA = os.getenv("HEALTHIA_CANDIDATE_SHA", "")
CLOUD_REVISION = os.getenv("HEALTHIA_CLOUD_REVISION", "")
CLOUD_IMAGE = os.getenv("HEALTHIA_CLOUD_IMAGE", "")
CLOUD_PROJECT = os.getenv("HEALTHIA_CLOUD_PROJECT", "")
CLOUD_REGION = os.getenv("HEALTHIA_CLOUD_REGION", "")
JUDGE_URL = os.getenv("HEALTHIA_JUDGE_URL", "").rstrip("/")
JUDGE_TOKEN = ""
IDENTITY_TOKEN_FILE = os.getenv("HEALTHIA_CLOUD_ID_TOKEN_FILE", "")
JUDGE_TOKEN_FILE = os.getenv("HEALTHIA_JUDGE_ID_TOKEN_FILE", "")
EVALUATION_ACCESS_KEY_FILE = os.getenv("HEALTHIA_EVALUATION_ACCESS_KEY_FILE", "")


def evaluation_access_key() -> str:
    """Read the evaluator capability without putting it in argv/report/video."""
    if EVALUATION_ACCESS_KEY_FILE:
        path = Path(EVALUATION_ACCESS_KEY_FILE)
        return path.read_text(encoding="utf-8").strip()
    return ""


def token_from_file(path_value: str, label: str) -> str:
    if not path_value:
        raise RuntimeError(f"{label} token file is required")
    value = Path(path_value).read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"{label} token file is empty")
    return value


def evaluation_json(page: Page, path: str, access_key: str, *, method: str = "GET", body: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {IDENTITY_TOKEN}",
        "X-HealthIA-Evaluation-Key": access_key,
    }
    response = page.request.fetch(
        f"{BASE_URL}{path}",
        method=method,
        headers=headers,
        data=json.dumps(body) if body is not None else None,
    )
    payload: dict = {}
    try:
        payload = response.json()
    except Exception:
        payload = {}
    require(response.ok, f"Living System request failed: {path} HTTP {response.status}")
    return payload


def record_living_system(page: Page, report: dict, access_key: str) -> None:
    """Record the real bounded Living System path before the broader product story."""
    require(access_key, "Living System evaluator capability is required")
    page.goto(f"{BASE_URL}/living", wait_until="networkidle", timeout=60_000)
    page.wait_for_selector("#accessForm", timeout=20_000)

    # The endpoint must fail closed before the capability is entered.
    locked = page.request.get(
        f"{BASE_URL}/api/evaluation/state",
        headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
    )
    require(locked.status == 403, f"Living System did not fail closed without capability: HTTP {locked.status}")
    report["living_system"] = {
        "access_control": "403_without_capability",
        "capability_transport": "password_input_then_in_memory_only",
        "synthetic_namespace": "patient_eval_living",
    }
    report["checks"].append("living_system_locked_without_capability")
    checkpoint(report)
    overlay(page, "A living system, safely locked", "The evaluator surface is present, but its synthetic patient remains unreachable until the capability is entered. No key is displayed or recorded.", 6)
    clear_overlay(page)

    page.locator("#accessKey").fill(access_key)
    page.locator("#accessForm button[type='submit']").click()
    page.wait_for_selector("#controlPanel:not([hidden])", timeout=20_000)
    # Keep the capability only in the page's closure; it is not left in the DOM or browser storage.
    # Unlock hides the access panel. Clear its DOM value without waiting for a
    # hidden element to become actionable; the page closure retains the key.
    page.locator("#accessKey").evaluate("element => { element.value = ''; }")
    storage = page.evaluate("({local: Object.keys(localStorage), session: Object.keys(sessionStorage)})")
    require(not any("evaluation" in str(item).lower() for item in storage["local"] + storage["session"]), "evaluation capability entered browser storage")
    report["checks"].append("living_system_capability_not_persisted_in_browser")
    checkpoint(report)
    overlay(page, "Capability granted — synthetic patient only", "The capability is held in memory for this page and unlocks no real patient record. The server still enforces the isolated evaluation namespace.", 6)
    clear_overlay(page)

    page.locator("#activateButton").click()
    page.wait_for_function("document.querySelector('#eventCount')?.textContent === '10 / 14'", timeout=30_000)
    page.wait_for_function("document.querySelector('#systemStatus')?.textContent === 'WAITING FOR HUMAN'", timeout=10_000)
    waiting = evaluation_json(page, "/api/evaluation/state", access_key)
    waiting_session = waiting.get("session") or {}
    waiting_twin = waiting.get("twin") or {}
    require(waiting_session.get("status") == "waiting_human", f"Living System did not stop for a human: {waiting_session}")
    require(len(waiting.get("events") or []) == 10, "Living System did not reach the 10/14 human boundary")
    require(waiting_twin.get("version") == 2, "Living Twin did not version to v2 at the human boundary")
    report["living_system"].update({"waiting_event_count": 10, "waiting_status": waiting_session.get("status"), "waiting_twin_version": waiting_twin.get("version")})
    report["checks"].extend(["living_system_arm_run_waiting_human", "living_system_waiting_boundary_visible_10_of_14"])
    checkpoint(report)
    overlay(page, "10 / 14 · WAITING FOR HUMAN", "Signals changed the canonical Twin and opened a governed mission. HealthIA stopped exactly where authority changes hands; it did not diagnose or prescribe.", 9)
    clear_overlay(page)

    page.locator("#humanForm").locator("button[type='submit']").click()
    page.wait_for_function("document.querySelector('#eventCount')?.textContent === '14 / 14'", timeout=30_000)
    page.wait_for_function("document.querySelector('#twinVersion')?.textContent === 'v3'", timeout=10_000)
    page.wait_for_function("document.querySelector('#systemStatus')?.textContent === 'VERIFIED'", timeout=10_000)
    completed = evaluation_json(page, "/api/evaluation/state", access_key)
    completed_session = completed.get("session") or {}
    completed_twin = completed.get("twin") or {}
    event_types = completed.get("event_types") or [item.get("event_type") for item in completed.get("events") or []]
    require(completed_session.get("status") == "completed", f"Living System did not complete: {completed_session}")
    require(len(event_types) == 14 and completed_twin.get("version") == 3, "Living System did not reach 14/14 Twin v3")
    require(completed.get("model_calls") == 0, "Living System consumed a model call")
    require(completed_session.get("release_sha") == CANDIDATE_SHA, "Living System is not bound to exact candidate SHA")
    report["living_system"].update({"completed_event_count": 14, "completed_status": completed_session.get("status"), "completed_twin_version": completed_twin.get("version"), "model_calls": completed.get("model_calls"), "release_sha": completed_session.get("release_sha"), "runtime_revision": completed_session.get("runtime_revision")})
    report["checks"].extend(["living_system_human_receipt_reaches_14_of_14", "living_system_twin_v3_visible", "living_system_zero_model_calls", "living_system_exact_sha_binding"])
    checkpoint(report)
    overlay(page, "14 / 14 · TWIN v3 VERIFIED", "A synthetic human-entered measurement became a persisted receipt. The Twin learned from evidence, the mission closed, and the full replay remains visible.", 10)
    clear_overlay(page)
    page.locator("#replayButton").click()
    page.wait_for_function("document.querySelector('#eventCount')?.textContent === '14 / 14'", timeout=15_000)
    report["checks"].append("living_system_durable_replay_visible")
    checkpoint(report)
    overlay(page, "Living means continuity", "Event, policy, mission, human boundary, receipt and verification are one durable chain — not a scripted chatbot response.", 8)
    clear_overlay(page)

    # Leave the evaluator page so the same continuous real-app recording continues.
    page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)


def checkpoint(report: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def overlay(page: Page, title: str, body: str, seconds: float = 4.0) -> None:
    page.evaluate(
        """({title, body}) => {
          let box = document.getElementById('healthia-winner-caption');
          if (!box) {
            box = document.createElement('aside');
            box.id = 'healthia-winner-caption';
            box.style.cssText = [
              'position:fixed','right:28px','bottom:28px','z-index:2147483647',
              'width:min(520px,36vw)','background:rgba(12,22,39,.92)','color:white',
              'border:1px solid rgba(147,197,253,.45)','border-radius:18px','padding:14px 16px',
              'box-shadow:0 18px 54px rgba(0,0,0,.28)','font-family:Inter,system-ui,sans-serif',
              'pointer-events:none'
            ].join(';');
            document.body.appendChild(box);
          }
          box.innerHTML = `<strong style="font-size:19px;display:block;margin-bottom:6px">${title}</strong><span style="font-size:14px;line-height:1.48;color:#e5edf8">${body}</span>`;
        }""",
        {"title": title, "body": body},
    )
    page.wait_for_timeout(int(seconds * 1000))


def clear_overlay(page: Page) -> None:
    page.evaluate("document.getElementById('healthia-winner-caption')?.remove()")


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


def latest_assistant(page: Page) -> dict:
    state = api_json(page, "/api/bootstrap")
    messages = [item for item in state.get("messages", []) if item.get("role") == "assistant"]
    return messages[-1] if messages else {}


def wait_for_assistant_after(page: Page, previous_id: str = "", timeout_s: float = 90.0) -> dict:
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        last = latest_assistant(page)
        if last.get("id") and last.get("id") != previous_id:
            return last
        page.wait_for_timeout(350)
    raise RuntimeError(f"assistant did not produce a new response in time: {last}")


def send_chat(page: Page, text: str) -> None:
    page.locator("#chatInput").fill(text)
    page.locator("#sendButton").click()


def mission_json(page: Page, mission_id: str) -> dict:
    return api_json(page, f"/api/google-constellation/missions/{mission_id}")


def wait_for_mission(
    page: Page,
    mission_id: str,
    *,
    state: str | None = None,
    min_candidates: int = 0,
    selected_id: str = "",
    timeout_s: float = 45.0,
) -> dict:
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        last = mission_json(page, mission_id)
        state_ok = state is None or str(last.get("state") or "") == state
        candidates = list((last.get("tool_outputs") or {}).get("place_candidates") or [])
        selected = dict(last.get("selected_place") or {})
        candidates_ok = len(candidates) >= min_candidates
        selected_ok = not selected_id or str(selected.get("id") or "") == selected_id
        if state_ok and candidates_ok and selected_ok:
            return last
        page.wait_for_timeout(400)
    raise RuntimeError(f"mission did not reach expected durable state: {last}")


def wait_for_resource_cards(page: Page, minimum: int = 2, timeout_s: float = 20.0) -> int:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        page.evaluate("window.HealthIAIcons?.hydrateResources?.()")
        count = page.locator(".wave4-resource-card").count()
        if count >= minimum:
            return count
        page.wait_for_timeout(350)
    raise RuntimeError("real Google Places candidate cards did not render")


def latest_result_state(page: Page, filename: str, timeout_s: float = 80.0) -> tuple[dict, dict, dict]:
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
    raise RuntimeError(f"multimodal evidence did not become durable: {last_state.get('results', [])[-2:]}")


def run() -> dict:
    global IDENTITY_TOKEN, JUDGE_TOKEN
    require(BASE_URL.startswith("https://") and ".run.app" in BASE_URL, "exact-candidate Cloud Run URL is required")
    IDENTITY_TOKEN = token_from_file(IDENTITY_TOKEN_FILE, "Cloud Run identity")
    JUDGE_TOKEN = token_from_file(JUDGE_TOKEN_FILE, "Judge Mode")
    require(bool(IDENTITY_TOKEN), "Cloud Run identity token is required")
    require(bool(CANDIDATE_SHA), "candidate SHA is required")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUTPUT / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = OUTPUT / "synthetic-winner-evidence.pdf"
    pdf = tiny_pdf()
    pdf_path.write_bytes(pdf)

    suffix = uuid4().hex[:10]
    email = f"winner-demo-{suffix}@example.test"
    password = f"WinnerDemo!{suffix}Aa9"
    display_name = "HealthIA Judge Patient"
    filename = pdf_path.name
    page_errors: list[str] = []
    console_errors: list[str] = []
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
        "judge_url": JUDGE_URL,
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "checks": [],
    }
    checkpoint(report)
    started = time.monotonic()
    access_key = evaluation_access_key()
    require(access_key, "HealthIA evaluation capability is required for the Living System recording")

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

        # 1. Exact-candidate Living System: real UI, bounded capability and durable replay.
        record_living_system(page, report, access_key)

        # 2. Exact-candidate live application.
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)
        page.wait_for_function("document.documentElement.lang === 'en'")
        require(page.locator("#registerTab").is_visible(), "registration UI missing")
        overlay(page, "HealthIA ONE", "Exact candidate running live on Google Cloud. The entire journey is the real application — no slide deck and no mock screens.", 5)
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
        require(readiness.get("store_backend") == "firestore", "Cloud runtime is not using Firestore")
        require(readiness.get("evidence_backend") == "gcs", "Cloud runtime is not using GCS")
        report["patient_id"] = patient_id
        report["readiness"] = {
            key: readiness.get(key)
            for key in ("ready", "model", "adk_ready", "ai_ready", "store_backend", "evidence_backend", "auth_required")
        }
        report["checks"].append("exact_candidate_live_google_runtime")
        checkpoint(report)
        overlay(page, "Bounded intelligence", "Gemini 3.5 Flash + Google ADK reason when useful. Firestore holds durable patient state and private Cloud Storage preserves original evidence.", 5)
        clear_overlay(page)

        # 3. A real product event reaches the longitudinal record before any chat prompt.
        device_sync = api_post_json(page, "/api/demo/device-sync")
        require(int(device_sync.get("accepted") or 0) >= 3, f"synthetic Health Connect event did not persist: {device_sync}")
        require(
            {"steps", "heart_rate", "weight"}.issubset(set(device_sync.get("granted_metrics") or [])),
            f"authorized Health Connect metric contract missing: {device_sync}",
        )
        page.reload(wait_until="networkidle", timeout=60_000)
        page.wait_for_selector('.main-nav [data-open="devices"]', timeout=20_000)
        page.locator('.main-nav [data-open="devices"]').click()
        page.wait_for_selector("#view-devices.is-active #deviceRoot .device-stats", timeout=20_000)
        device_state = api_json(page, "/api/devices")
        require(int(device_state.get("record_count") or 0) >= 3, f"device records are not durable: {device_state}")
        require(page.locator("#deviceRoot .device-metric").count() >= 3, "authorized device metrics are not visible")
        report["device_sync"] = {
            "accepted": device_sync.get("accepted"),
            "granted_metrics": device_sync.get("granted_metrics"),
            "record_count": device_state.get("record_count"),
            "synthetic": True,
        }
        report["checks"].append("synthetic_health_connect_event_visible_with_provenance")
        checkpoint(report)
        overlay(page, "The system is already listening", "A synthetic Health Connect event entered the real Cloud application before any chat request. HealthIA preserved source, time and patient-authorized metrics, updated the longitudinal record, and kept the sensor truth boundary visible.", 8)
        clear_overlay(page)
        page.locator('.main-nav [data-open="chat"]').click()

        # 4. Flagship Taskmaster mission: real navigation must stop at consent.
        before = latest_assistant(page)
        send_chat(page, "Find a center for autism support near Santiago de los Caballeros.")
        blocked_reply = wait_for_assistant_after(page, str(before.get("id") or ""), timeout_s=100.0)
        blocked_meta = blocked_reply.get("metadata") or {}
        mission_id = str(blocked_meta.get("google_mission_id") or "")
        require(mission_id, f"navigation response did not create a durable Google mission: {blocked_meta}")
        require(blocked_meta.get("requires_human_authorization") is True, f"navigation did not stop at human boundary: {blocked_meta}")
        require(blocked_meta.get("authorization_kind") == "maps_location_for_mission", f"wrong authorization boundary: {blocked_meta}")
        require(blocked_meta.get("external_action_executed") is not True, "external action was reported before location consent")
        blocked_mission = mission_json(page, mission_id)
        boundary = dict((blocked_mission.get("tool_outputs") or {}).get("authorization_boundary") or {})
        pre_candidates = list((blocked_mission.get("tool_outputs") or {}).get("place_candidates") or [])
        require(boundary.get("kind") == "maps_location_for_mission", "durable mission boundary missing")
        require(boundary.get("external_action_performed") is False, "mission boundary falsely reports external execution")
        require(not pre_candidates, "Places candidates exist before mission-scoped location consent")
        report["mission_id"] = mission_id
        report["checks"].append("zero_places_before_mission_scoped_consent")
        checkpoint(report)
        overlay(page, "The human boundary", "HealthIA created a durable mission, then stopped. Location belongs to the patient. No Google Places result exists before mission-scoped consent.", 7)
        clear_overlay(page)

        # 5. Exact consent resumes the SAME mission and executes real Google Places.
        before_consent = latest_assistant(page)
        send_chat(page, "I authorize my location for this mission.")
        consent_reply = wait_for_assistant_after(page, str(before_consent.get("id") or ""), timeout_s=100.0)
        consent_meta = consent_reply.get("metadata") or {}
        require(str(consent_meta.get("google_mission_id") or "") == mission_id, "consent resumed a different mission")
        require(consent_meta.get("google_mission_state") == "awaiting_selection", f"authorized search did not reach candidate selection: {consent_meta}")
        require(consent_meta.get("external_action_executed") is True, "authorized Google Places search was not reported as executed")
        require(consent_meta.get("external_mutation_performed") is False, "Places discovery must remain read-only")
        require(consent_meta.get("policy_executed_tool") == "discover_care_options", f"wrong policy tool after consent: {consent_meta}")

        resumed = wait_for_mission(page, mission_id, state="awaiting_selection", min_candidates=2, timeout_s=25.0)
        candidates = list((resumed.get("tool_outputs") or {}).get("place_candidates") or [])
        require(len(candidates) >= 2, "real Google Places search returned fewer than two candidates for winner demo")
        candidate_ids = [str(item.get("id") or "") for item in candidates]
        require(all(candidate_ids[:2]), "candidate IDs missing")
        report["candidate_count"] = len(candidates)
        report["google_maps_uri_count"] = sum(bool(str(item.get("googleMapsUri") or "").strip()) for item in candidates)
        require(report["google_maps_uri_count"] >= 2, "real candidates lack Google Maps URIs")
        card_count = wait_for_resource_cards(page, minimum=2, timeout_s=20.0)
        require(page.locator('.wave4-resource-card .wave4-resource-links a:has-text("Google Maps")').count() >= 2, "visible cards lack Google Maps links")
        report["visible_candidate_cards"] = card_count
        report["checks"].extend([
            "same_durable_mission_resumed_after_consent",
            "real_google_places_candidates_visible",
        ])
        checkpoint(report)
        overlay(page, "Same mission, real Google Places", f"Consent resumed mission {mission_id[:12]}… and surfaced {len(candidates)} verifiable candidates with Google Maps links. This is a real read-only Google action.", 8)
        clear_overlay(page)

        # 6. "The second one" is deterministic intent, not another LLM problem.
        expected_second_id = candidate_ids[1]
        before_choice = latest_assistant(page)
        send_chat(page, "The second one.")
        choice_reply = wait_for_assistant_after(page, str(before_choice.get("id") or ""), timeout_s=30.0)
        choice_meta = choice_reply.get("metadata") or {}
        require(str(choice_meta.get("google_mission_id") or "") == mission_id, "ordinal choice targeted another mission")
        require(choice_meta.get("deterministic_candidate_index") == 1, f"second choice was not deterministically resolved: {choice_meta}")
        require(choice_meta.get("policy_executed_tool") == "select_discovered_candidate", f"selection did not use bounded deterministic policy: {choice_meta}")
        require(choice_meta.get("external_action_executed") is False, "candidate selection falsely claims an external action")
        selected = wait_for_mission(page, mission_id, selected_id=expected_second_id, timeout_s=15.0)
        require(str((selected.get("selected_place") or {}).get("id") or "") == expected_second_id, "exact second candidate did not persist")
        page.evaluate("window.HealthIAIcons?.hydrateResources?.()")
        page.wait_for_timeout(700)
        selected_cards = page.locator(".wave4-resource-card.is-selected")
        require(selected_cards.count() >= 1, "selected candidate is not visibly marked")
        require(selected_cards.last.inner_text().lstrip().startswith("Selected") or "2." in selected_cards.last.inner_text(), "visible selection does not correspond to second candidate")
        report["selected_candidate_id"] = expected_second_id
        report["checks"].append("exact_second_candidate_selected_without_model_interpretation")
        checkpoint(report)
        overlay(page, "Exact human choice", "“The second one” bypasses Gemini. Deterministic policy selects exactly candidate #2 from the already-discovered list and preserves it in the same mission.", 8)
        clear_overlay(page)

        # 7. Evidence first: preserve original bytes before AI interpretation.
        page.locator('.main-nav [data-open="results"]').click()
        page.wait_for_timeout(500)
        page.locator("#resultFile").set_input_files(str(pdf_path))
        _, result, document = latest_result_state(page, filename)
        result_id = str(result.get("id") or "")
        document_id = str(document.get("id") or "")
        require(result_id and document_id, "result/document provenance missing")
        require(str(result.get("explanation") or "").strip(), "multimodal result has no bounded patient explanation")
        report["result_id"] = result_id
        report["document_id"] = document_id
        report["checks"].append("multimodal_original_result_and_provenance")
        checkpoint(report)
        overlay(page, "Evidence before interpretation", "The synthetic original is preserved in private Cloud Storage before Gemini extraction. Firestore keeps the derived result linked back to the source document.", 8)
        clear_overlay(page)

        # 8. Durable continuity survives logout/login.
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
        restored_mission = wait_for_mission(page, mission_id, selected_id=expected_second_id, timeout_s=15.0)
        require(str((restored_mission.get("selected_place") or {}).get("id") or "") == expected_second_id, "selected Google Places candidate disappeared after relogin")
        report["checks"].append("logout_login_restores_evidence_and_selected_google_mission")
        checkpoint(report)
        page.locator('.main-nav [data-open="record"]').click()
        page.wait_for_selector("#view-record.is-active #recordGrid .record-card", timeout=20_000)
        overlay(page, "One patient record, assembled while life happens", "The device event, preserved clinical result and mission now live together in the patient-controlled record. HealthIA is not a collection of disconnected chats.", 6)
        clear_overlay(page)
        page.wait_for_selector('.main-nav [data-open="timeline"]', timeout=20_000)
        page.locator('.main-nav [data-open="timeline"]').click()
        page.wait_for_selector("#view-timeline.is-active #timelineRoot .timeline-event", timeout=20_000)
        require(page.locator("#timelineRoot .timeline-event").count() >= 3, "unified longitudinal timeline is not visibly populated")
        overlay(page, "A living longitudinal timeline", "Measurements, evidence and missions become one provenance-linked chronology. After logout and login, the same patient state is still here.", 6)
        clear_overlay(page)
        report["checks"].append("unified_record_and_timeline_visible_after_relogin")

        # The Living System is part of the main patient workspace, not a detached demo.
        page.locator('.main-nav [data-open="living"]').click()
        page.wait_for_selector("#view-living.is-active .living-surface", timeout=20_000)
        page.wait_for_function("Number(document.querySelector('#livingMissionCount')?.textContent || 0) >= 1", timeout=20_000)
        page.wait_for_function("Number(document.querySelector('#livingEvidenceCount')?.textContent || 0) >= 1", timeout=20_000)
        page.wait_for_function("Number(document.querySelector('#livingDecisionCount')?.textContent || 0) >= 1", timeout=20_000)
        native_living = {
            "twin_version": page.locator("#livingTwinVersion").inner_text().strip(),
            "evidence_count": int(page.locator("#livingEvidenceCount").inner_text().strip()),
            "active_missions": int(page.locator("#livingMissionCount").inner_text().strip()),
            "human_decisions": int(page.locator("#livingDecisionCount").inner_text().strip()),
            "recorded_steps": page.locator("#livingActivityList li").count(),
        }
        require(native_living["twin_version"].startswith("v"), f"native Patient Twin is not visible: {native_living}")
        require(native_living["recorded_steps"] >= 1, f"native autonomous activity is empty: {native_living}")
        report["native_living_surface"] = native_living
        report["checks"].append("native_patient_workspace_unifies_twin_missions_activity_and_human_decisions")
        checkpoint(report)
        overlay(page, "The Living System is the product", "Inside the main patient workspace, the real Patient Twin, persisted evidence, active Google mission, autonomous receipts and the decision waiting for the human now appear together. This is not a detached demo screen.", 8)
        clear_overlay(page)

        # 9. Final exact-candidate proof.
        readiness = api_json(page, "/api/readiness")
        page.locator('.main-nav [data-open="chat"]').click()
        cloud_summary = (
            f"SHA {CANDIDATE_SHA[:12]} · Cloud Run {CLOUD_REVISION or 'verified'} · "
            f"Gemini {readiness.get('model')} · ADK ready: {readiness.get('adk_ready')} · "
            f"State: {readiness.get('store_backend')} · Evidence: {readiness.get('evidence_backend')}"
        )
        overlay(page, "Real action requires real evidence", cloud_summary, 8)
        report["checks"].append("visible_exact_candidate_cloud_proof")
        clear_overlay(page)

        # 10. Exact-head autonomous continuity proof stays public, read-only and synthetic.
        require(JUDGE_URL.startswith("https://") and ".run.app" in JUDGE_URL, "exact-head Judge Mode URL is required")
        require(bool(JUDGE_TOKEN), "private exact-head Judge Mode identity token is required")
        page.set_extra_http_headers({"Authorization": f"Bearer {JUDGE_TOKEN}"})
        health_response = page.request.get(f"{JUDGE_URL}/judge-health", headers={"Authorization": f"Bearer {JUDGE_TOKEN}"})
        require(health_response.ok, f"Judge Mode health failed: {health_response.status}")
        judge_health = health_response.json()
        proof_response = page.request.get(f"{JUDGE_URL}/api/proof", headers={"Authorization": f"Bearer {JUDGE_TOKEN}"})
        require(proof_response.ok, f"Judge Mode proof failed: {proof_response.status}")
        autonomous_proof = proof_response.json()
        require(judge_health.get("source_sha") == CANDIDATE_SHA, f"Judge Mode source mismatch: {judge_health}")
        require(judge_health.get("mode") == "judge_read_only_synthetic", f"unexpected Judge Mode: {judge_health}")
        require(judge_health.get("mutations") is False and judge_health.get("secrets") is False, "Judge Mode must be inert")
        require(autonomous_proof.get("boundary_count") == 5, f"unexpected autonomy proof: {autonomous_proof}")
        require(autonomous_proof.get("model_calls_for_trigger") == 0, "overdue detection must use zero model calls")
        page.goto(JUDGE_URL, wait_until="networkidle", timeout=60_000)
        body = page.locator("body").inner_text()
        require("HealthIA noticed the follow-up was overdue. Nobody prompted it." in body, "autonomous judge sentence is not visible")
        require("JUDGE MODE · READ ONLY · SYNTHETIC" in body, "public truth boundary is not visible")
        page.wait_for_timeout(11_000)
        page.locator(".grid").scroll_into_view_if_needed()
        page.wait_for_timeout(10_000)
        report["judge_health"] = judge_health
        report["autonomous_proof"] = {key: autonomous_proof.get(key) for key in ("boundary_count", "model_calls_for_trigger", "source_sha", "live_proof_run", "judge_mode")}
        report["checks"].append("exact_head_autonomous_continuity_judge_mode")
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
    print("HEALTHIA_FINAL_WAVE4_WINNER_DEMO_PASS")
    print(json.dumps({
        "status": report["status"],
        "candidate_sha": CANDIDATE_SHA,
        "mission_id": report.get("mission_id"),
        "candidate_count": report.get("candidate_count"),
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
        try:
            failure = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
        except Exception:
            failure = {}
        failure.update({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:3000]})
        REPORT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_FINAL_WAVE4_WINNER_DEMO_FAIL {type(exc).__name__}: {exc}")
        raise
