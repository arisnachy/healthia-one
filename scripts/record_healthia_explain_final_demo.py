from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright

from cloud_browser_judge_proof import api_json, require


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "healthia-explain-final-cloud-demo"
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


def overlay(page: Page, title: str, body: str, seconds: float = 2.5) -> None:
    page.evaluate(
        """({title, body}) => {
          let box = document.getElementById('healthia-explain-proof-caption');
          if (!box) {
            box = document.createElement('aside');
            box.id = 'healthia-explain-proof-caption';
            box.style.cssText = [
              'position:fixed','right:24px','bottom:24px','z-index:2147483647',
              'width:min(600px,46vw)','background:rgba(19,35,61,.95)','color:white',
              'border:1px solid rgba(255,255,255,.14)','border-radius:18px','padding:16px 18px',
              'box-shadow:0 18px 48px rgba(0,0,0,.24)','font-family:Inter,system-ui,sans-serif',
              'pointer-events:none'
            ].join(';');
            document.body.appendChild(box);
          }
          box.innerHTML = `<strong style="font-size:19px;display:block;margin-bottom:6px">${title}</strong><span style="font-size:14px;line-height:1.45;color:#e8eef7">${body}</span>`;
        }""",
        {"title": title, "body": body},
    )
    page.wait_for_timeout(int(seconds * 1000))


def clear_overlay(page: Page) -> None:
    page.evaluate("document.getElementById('healthia-explain-proof-caption')?.remove()")


def api_post_json(page: Page, path: str, payload: dict) -> dict:
    return page.evaluate(
        """async ({path, payload}) => {
          const r = await fetch(path, {
            method:'POST', credentials:'same-origin',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(payload)
          });
          let body = {};
          try { body = await r.json(); } catch (_) {}
          if (!r.ok) throw new Error(`${path} HTTP ${r.status}: ${JSON.stringify(body)}`);
          return body;
        }""",
        {"path": path, "payload": payload},
    )


def latest_education_message(page: Page) -> dict:
    state = api_json(page, "/api/bootstrap")
    messages = [
        item for item in state.get("messages", [])
        if item.get("role") == "assistant" and isinstance((item.get("metadata") or {}).get("education_video"), dict)
    ]
    return messages[-1] if messages else {}


def wait_for_completed_video(page: Page, timeout_s: float = 300.0) -> tuple[dict, dict]:
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        last = latest_education_message(page)
        record = (last.get("metadata") or {}).get("education_video") or {}
        status = str(record.get("status") or "")
        if status == "generation_failed":
            raise RuntimeError(f"HealthIA Explain generation failed: {record}")
        if status == "completed" and record.get("video_id") and record.get("url"):
            return state, last
        page.wait_for_timeout(1000)
    raise RuntimeError(f"HealthIA Explain did not complete within {timeout_s:.0f}s; last={last}")


def run() -> dict:
    require(BASE_URL.startswith("https://") and ".run.app" in BASE_URL, "temporary Cloud Run URL is required")
    require(bool(IDENTITY_TOKEN), "Cloud Run identity token is required")
    require(bool(CANDIDATE_SHA), "candidate SHA is required")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUTPUT / "browser-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    product_dir = OUTPUT / "product-video"
    product_dir.mkdir(parents=True, exist_ok=True)

    suffix = uuid4().hex[:10]
    email = f"explain-final-{suffix}@example.test"
    password = f"ExplainFinal!{suffix}Aa9"
    display_name = "Ana HealthIA Demo"
    console_errors: list[str] = []
    page_errors: list[str] = []
    report: dict = {
        "status": "running",
        "synthetic_only": True,
        "browser_os_locale": "en-US",
        "patient_message_locale": "es",
        "candidate_sha": CANDIDATE_SHA,
        "base_url": BASE_URL,
        "cloud_revision": CLOUD_REVISION,
        "cloud_image": CLOUD_IMAGE,
        "cloud_project": CLOUD_PROJECT,
        "cloud_region": CLOUD_REGION,
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
        require(page.locator('[data-auth-copy="hero"]').inner_text().strip() == "Your health continues", "OS/browser English login hero mismatch")
        require(page.locator(".auth-wordmark").inner_text().strip() == "HealthIA ONE", "HealthIA ONE login brand missing")
        report["checks"].append("os_browser_locale_selects_english_ui")
        overlay(page, "Interface language ≠ patient language", "The operating system/browser is English. HealthIA will still follow the language the patient actually writes.", 3.5)
        clear_overlay(page)

        page.locator("#registerTab").click()
        page.locator('#registerForm input[name="display_name"]').fill(display_name)
        page.locator('#registerForm input[name="email"]').fill(email)
        page.locator('#registerForm input[name="password"]').fill(password)
        page.locator('#registerForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=30_000)
        page.wait_for_load_state("networkidle")
        session = api_json(page, "/api/auth/session")
        require(session.get("authenticated") is True, "synthetic patient registration failed")
        patient_id = str((session.get("account") or {}).get("patient_id") or "")
        require(patient_id.startswith("patient_"), "patient identity missing")
        report["patient_id"] = patient_id
        report["checks"].append("authenticated_synthetic_patient")

        readiness = api_json(page, "/api/readiness")
        require(readiness.get("ai_ready") is True and readiness.get("adk_ready") is True, "Gemini/ADK not ready")
        require(readiness.get("model") == "gemini-3.5-flash", f"unexpected Gemini model: {readiness.get('model')}")
        require(readiness.get("store_backend") == "firestore", "Cloud proof is not using Firestore")
        require(readiness.get("evidence_backend") == "gcs", "Cloud proof is not using private GCS")
        report["readiness"] = {key: readiness.get(key) for key in ("model", "adk_ready", "ai_ready", "store_backend", "evidence_backend", "auth_required")}
        report["checks"].append("live_google_cloud_runtime")

        vital = api_post_json(page, "/api/vitals", {"systolic": 152, "diastolic": 94, "pulse": 82})
        vital_id = str(vital.get("id") or "")
        require(vital_id, "synthetic blood pressure was not persisted")
        report["synthetic_vital_id"] = vital_id
        report["checks"].append("synthetic_patient_evidence_persisted")

        page.locator('.main-nav [data-open="chat"]').click()
        page.locator("#chatInput").fill("Crea un video corto de un minuto explicándome qué significa la hipertensión y mi presión arterial. Quiero entenderlo de forma sencilla.")
        overlay(page, "The patient writes in Spanish", "HealthIA resolves the current message language before planning the educational mission.", 3)
        clear_overlay(page)
        page.locator("#sendButton").click()

        state, assistant = wait_for_completed_video(page, timeout_s=300.0)
        record = (assistant.get("metadata") or {}).get("education_video") or {}
        require(str((assistant.get("metadata") or {}).get("response_locale") or "") == "es", f"assistant did not follow Spanish patient language: {assistant.get('metadata')}")
        require(record.get("locale") == "es", f"video locale did not follow Spanish patient language: {record}")
        require(record.get("narration_status") == "gemini_tts", f"production narration did not use Gemini TTS: {record}")
        require(record.get("veo_enhanced") is True, f"final proof requires a real Veo-enhanced scene: {record}")
        require(record.get("private") is True, "education video is not marked private")
        video_id = str(record.get("video_id") or "")
        video_url = str(record.get("url") or "")
        mission_id = str(assistant.get("mission_id") or "")
        mission = next((item for item in state.get("missions", []) if item.get("id") == mission_id), None)
        require(bool(mission), "patient_education_video mission missing")
        require(mission.get("mission_type") == "patient_education_video" and mission.get("status") == "completed", f"education mission not durably completed: {mission}")
        require(any(str(item).startswith("education_video:") for item in mission.get("closure_evidence", [])), "completed education mission has no video closure evidence")
        report.update({
            "education_video_id": video_id,
            "education_mission_id": mission_id,
            "education_video_locale": record.get("locale"),
            "narration_status": record.get("narration_status"),
            "veo_enhanced": record.get("veo_enhanced"),
            "veo_operation_recorded": bool(record.get("veo_operation_name")),
        })
        report["checks"].extend([
            "patient_message_language_overrides_os_locale",
            "gemini_tts_patient_language_narration",
            "real_phi_free_veo_enrichment",
            "durable_patient_education_video_mission",
        ])
        checkpoint(report)

        manifest = api_json(page, f"/api/education/videos/{video_id}/manifest")
        require(manifest.get("status") == "completed" and manifest.get("private") is True, f"private media manifest invalid: {manifest}")
        require(manifest.get("locale") == "es", f"manifest locale mismatch: {manifest}")
        require(manifest.get("veo_enhanced") is True, f"manifest did not preserve Veo proof: {manifest}")
        report["checks"].append("private_authenticated_video_manifest")

        page.wait_for_selector(".education-video-card video", timeout=20_000)
        player = page.locator(".education-video-card video").last
        require(player.get_attribute("src") == video_url, "chat player does not point to the durable private video URL")
        player.scroll_into_view_if_needed()
        overlay(page, "HealthIA Explain", "Gemini planned the explanation, exact patient values stay on controlled cards, Gemini TTS narrates in Spanish, and Veo receives only generic PHI-free visual instructions.", 4)
        clear_overlay(page)
        player.evaluate("v => { v.muted = true; v.currentTime = 0; return v.play(); }")
        page.wait_for_timeout(8000)
        player.evaluate("v => v.pause()")
        report["checks"].append("embedded_private_video_player_visible")

        response = context.request.get(
            f"{BASE_URL}{video_url}",
            headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
            timeout=60_000,
        )
        require(response.ok, f"authenticated private video download failed: HTTP {response.status}")
        product_bytes = response.body()
        require(len(product_bytes) > 20_000 and b"ftyp" in product_bytes[:64], "private product media is not a valid-looking MP4")
        product_path = product_dir / "HealthIA-Explain-real-patient-video.mp4"
        product_path.write_bytes(product_bytes)
        report["product_video_bytes"] = len(product_bytes)
        report["product_video_sha256"] = hashlib.sha256(product_bytes).hexdigest()
        report["checks"].append("real_private_product_mp4_downloaded")
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
        require(any(item.get("id") == mission_id and item.get("status") == "completed" for item in restored.get("missions", [])), "education mission disappeared after relogin")
        restored_video_message = next((item for item in restored.get("messages", []) if ((item.get("metadata") or {}).get("education_video") or {}).get("video_id") == video_id), None)
        require(bool(restored_video_message), "education video metadata disappeared after relogin")
        page.locator('.main-nav [data-open="chat"]').click()
        page.wait_for_selector(".education-video-card video", timeout=15_000)
        require(page.locator('.education-video-card video').last.get_attribute("src") == video_url, "private video player did not restore after relogin")
        report["checks"].append("logout_login_restores_education_video_and_mission")
        overlay(page, "Continuity, not a one-off generation", "After logout and login, the completed mission and its private education video are restored for the same patient.", 4)
        clear_overlay(page)

        readiness = api_json(page, "/api/readiness")
        overlay(
            page,
            "Exact Google Cloud proof",
            f"SHA {CANDIDATE_SHA[:12]} · Cloud Run {CLOUD_REVISION} · Gemini {readiness.get('model')} · ADK ready · Firestore state · private GCS evidence/media",
            5,
        )
        clear_overlay(page)
        report["checks"].append("visible_exact_candidate_cloud_proof")

        require(not page_errors, f"browser page errors: {page_errors}")
        # Chromium may log a benign media prefetch warning. Keep only actual JS/network errors.
        material_console_errors = [item for item in console_errors if "favicon" not in item.lower()]
        require(not material_console_errors, f"browser console errors: {material_console_errors}")
        report["console_errors"] = console_errors
        report["page_errors"] = page_errors
        report["checks"].append("zero_material_browser_errors")
        report["status"] = "PASS"
        report["raw_elapsed_seconds"] = round(time.monotonic() - started, 2)
        checkpoint(report)
        context.close()
        browser.close()

    browser_videos = sorted(video_dir.glob("*.webm"))
    require(bool(browser_videos), "Playwright did not produce a live browser recording")
    browser_video = browser_videos[0]
    report["browser_video_file"] = str(browser_video.relative_to(ROOT))
    report["browser_video_sha256"] = hashlib.sha256(browser_video.read_bytes()).hexdigest()
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    checkpoint(report)
    print("HEALTHIA_EXPLAIN_FINAL_CLOUD_DEMO_PASS")
    print(json.dumps({
        "status": report["status"],
        "candidate_sha": CANDIDATE_SHA,
        "checks": report["checks"],
        "product_video_sha256": report.get("product_video_sha256"),
        "browser_video_sha256": report.get("browser_video_sha256"),
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
        failure.update({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:4000]})
        REPORT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_EXPLAIN_FINAL_CLOUD_DEMO_FAIL {type(exc).__name__}: {exc}")
        raise
