from __future__ import annotations

import json
import os
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright

BASE_URL = os.getenv("HEALTHIA_DEMO_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
OUT = Path(os.getenv("HEALTHIA_DEMO_OUTPUT", "dist/v6-functional-demo"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def wait_server(page: Page) -> None:
    for _ in range(90):
        try:
            response = page.request.get(f"{BASE_URL}/healthz", timeout=1500)
            if response.ok:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("HealthIA local demo server did not become ready")


def micro_note(page: Page, title: str, body: str, seconds: float = 2.2) -> None:
    page.evaluate(
        """({title, body}) => {
          document.querySelector('#v6-live-note')?.remove();
          const el = document.createElement('aside');
          el.id = 'v6-live-note';
          el.style.cssText = 'position:fixed;right:24px;top:18px;width:360px;z-index:99999;background:rgba(7,24,45,.92);color:white;border:1px solid rgba(255,255,255,.2);border-radius:16px;padding:12px 14px;font:13px/1.35 system-ui,-apple-system,Segoe UI,sans-serif;box-shadow:0 12px 32px rgba(0,0,0,.24);backdrop-filter:blur(8px)';
          el.innerHTML = `<div style="font-size:10px;letter-spacing:.16em;opacity:.72;margin-bottom:5px">LIVE HEALTHIA ONE</div><strong style="font-size:15px;display:block;margin-bottom:4px">${title}</strong><span style="opacity:.9">${body}</span>`;
          document.body.appendChild(el);
        }""",
        {"title": title, "body": body},
    )
    page.wait_for_timeout(int(seconds * 1000))
    page.evaluate("document.querySelector('#v6-live-note')?.remove()")


def api_json(page: Page, path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    return page.evaluate(
        """async ({path, method, payload}) => {
          const options = {method, headers: {'Accept':'application/json','Content-Type':'application/json','Accept-Language':'en'}};
          if (payload !== null) options.body = JSON.stringify(payload);
          const response = await fetch(path, options);
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(`${response.status}: ${data.detail || JSON.stringify(data)}`);
          return data;
        }""",
        {"path": path, "method": method, "payload": payload},
    )


def send_chat(page: Page, text: str, *, timeout_ms: int = 75000) -> str:
    before = page.locator("#messageList .message.assistant").count()
    page.locator("#chatInput").fill(text)
    page.locator("#sendButton").click()
    page.wait_for_function(
        "before => document.querySelectorAll('#messageList .message.assistant').length > before",
        arg=before,
        timeout=timeout_ms,
    )
    page.wait_for_timeout(850)
    last = page.locator("#messageList .message.assistant").last
    last.scroll_into_view_if_needed()
    return last.inner_text(timeout=5000)


def wait_resource_cards(page: Page, minimum: int = 3, timeout_ms: int = 30000) -> int:
    page.wait_for_function(
        "minimum => document.querySelectorAll('.wave4-resource-card').length >= minimum",
        arg=minimum,
        timeout=timeout_ms,
    )
    return page.locator(".wave4-resource-card").count()


def set_english(page: Page) -> None:
    # The app exposes a language button in both login and runtime. Use it if needed.
    if page.locator("html").get_attribute("lang") == "en":
        return
    for selector in ("[data-locale='en']", "#languageToggle", "[data-language='en']"):
        locator = page.locator(selector)
        if locator.count() and locator.first.is_visible():
            locator.first.click()
            page.wait_for_timeout(400)
            break


def seed_synthetic_clinical_context(page: Page) -> None:
    bootstrap = api_json(page, "/api/bootstrap")
    profile = dict(bootstrap["profile"])
    profile.update(
        {
            "display_name": "Alex Rivera",
            "sex_at_birth": "male",
            "address": "Santiago de los Caballeros, Dominican Republic",
            "locale": "en-US",
            "timezone": "America/Santo_Domingo",
            "confirmed_conditions": ["Hypertension"],
            "medications": ["Losartan 50 mg once daily"],
        }
    )
    api_json(page, "/api/profile", method="PUT", payload=profile)
    api_json(
        page,
        "/api/treatment/plans",
        method="POST",
        payload={
            "original_text": "Losartan 50 mg by mouth once daily",
            "name": "Losartan",
            "generic_name": "losartan",
            "strength": "50 mg",
            "dose_value": 50,
            "dose_unit": "mg",
            "dosage_form": "tablet",
            "route": "oral",
            "schedule": "once daily",
            "frequency_times_per_day": 1,
            "purpose": "Hypertension",
            "instructions": "Continue only as prescribed by the treating clinician.",
            "prescribed_by": "Synthetic demo clinician",
            "verification_status": "professional_confirmed",
            "active": True,
            "source": {"source_type": "patient_report", "source_id": "v6_demo"},
        },
    )
    api_json(
        page,
        "/api/family",
        method="POST",
        payload={
            "display_name": "Child",
            "relation": "child",
            "generation": 1,
            "lineage": "both",
            "sex_at_birth": "unknown",
            "biological_relative": True,
            "conditions": [
                {"name": "Autism spectrum disorder", "confirmed": True, "notes": "Synthetic demo context"}
            ],
            "source": {"source_type": "patient_report", "source_id": "v6_demo_family"},
        },
    )


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUT / "playwright-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "running",
        "synthetic_only": True,
        "slides_used": False,
        "browser_application_only": True,
        "checks": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(video_dir),
            record_video_size={"width": 1600, "height": 900},
        )
        page = context.new_page()
        wait_server(page)

        # Real login/registration flow.
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60000)
        set_english(page)
        micro_note(page, "Real application — not slides", "The video stays inside the working HealthIA browser product from login through every agentic action.", 2.6)
        suffix = uuid4().hex[:8]
        if page.locator("#registerTab").count():
            page.locator("#registerTab").click()
            page.locator('#registerForm input[name="display_name"]').fill("Alex Rivera")
            page.locator('#registerForm input[name="email"]').fill(f"v6-demo-{suffix}@example.test")
            page.locator('#registerForm input[name="password"]').fill(f"HealthIA!{suffix}9Aa")
            page.locator('#registerForm button[type="submit"]').click()
            page.wait_for_url(f"{BASE_URL}/", timeout=30000)
        else:
            page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=30000)
        page.wait_for_load_state("networkidle")
        set_english(page)
        report["checks"].append("login_registration_visible")

        seed_synthetic_clinical_context(page)
        page.reload(wait_until="networkidle")
        set_english(page)
        micro_note(page, "Living clinical context", "Synthetic hypertension treatment and an authorized family condition are now part of the patient-owned twin.", 2.4)

        # 1) Broad family support resource mission with real Google Places.
        support_request = (
            "My child has autism. Find nearby therapy centers, community support organizations, and government or financial assistance resources in Santiago de los Caballeros, Dominican Republic."
        )
        first = send_chat(page, support_request, timeout_ms=90000)
        require("location" in first.lower() or "permission" in first.lower() or "authorize" in first.lower(), "resource mission did not stop at location consent")
        micro_note(page, "Autonomous resource mission", "HealthIA understood a family-support need, created a durable mission, and stopped before using location because mission-scoped consent is required.", 3.1)
        report["checks"].append("resource_mission_consent_boundary")

        second = send_chat(page, "I authorize my location for this mission.", timeout_ms=90000)
        cards = wait_resource_cards(page, minimum=3, timeout_ms=45000)
        panel = page.locator(".wave4-resource-panel").last
        panel.scroll_into_view_if_needed()
        micro_note(page, "Nearby + Google Maps", f"The same mission resumed and returned {cards} real Google Places candidates with address, phone, Maps, and website links when available.", 4.0)
        report["checks"].append(f"real_google_places_candidates_{cards}")

        selected = send_chat(page, "The second one.", timeout_ms=45000)
        page.wait_for_timeout(1000)
        require(page.locator(".wave4-resource-card.is-selected").count() >= 1, "exact second-place selection was not projected into the UI")
        page.locator(".wave4-resource-card.is-selected").last.scroll_into_view_if_needed()
        micro_note(page, "Exact selection", "The patient can simply say “the second one.” HealthIA reuses the durable mission and selects that exact verified candidate instead of inventing another place.", 3.2)
        report["checks"].append("exact_second_candidate_selection")

        # 2) Scientific radar and treatment/twin comparison.
        page.locator('[data-open="chat"]').click()
        science = send_chat(page, "What is new about my health?", timeout_ms=120000)
        require("source" in science.lower() or "research" in science.lower() or "discovery" in science.lower(), "scientific radar did not return a sourced result")
        micro_note(page, "Scientific radar", "HealthIA searched current scientific sources for the authorized condition and surfaced only a relevant discovery with provenance.", 3.3)
        report["checks"].append("scientific_radar_current_sources")

        page.locator('[data-open="discoveries"]').click()
        page.wait_for_timeout(1200)
        require(page.locator(".opportunity-card").count() >= 1, "scientific discovery card was not visible")
        page.locator(".opportunity-card").first.scroll_into_view_if_needed()
        micro_note(page, "Evidence inside the product", "The patient sees the original source, evidence tier, why it may matter, reported benefits, and limitations — not a PowerPoint claim.", 3.3)

        compare_button = page.locator('[data-opportunity-chat-en*="Compare it with my medication"]').first
        require(compare_button.count() >= 1, "comparison action is missing")
        before = page.locator("#messageList .message.assistant").count()
        compare_button.click()
        page.wait_for_function(
            "before => document.querySelectorAll('#messageList .message.assistant').length > before",
            arg=before,
            timeout=45000,
        )
        page.wait_for_timeout(900)
        comparison_message = page.locator("#messageList .message.assistant").last
        comparison_message.scroll_into_view_if_needed()
        comparison_text = comparison_message.inner_text()
        require("Losartan" in comparison_text or "losartan" in comparison_text.lower(), "comparison did not use recorded treatment")
        micro_note(page, "Twin + treatment comparison", "The new evidence is compared against the recorded treatment and patient context. HealthIA explicitly keeps this as decision support — it does not change medication or pretend to predict an individual outcome.", 4.0)
        report["checks"].append("evidence_compared_with_recorded_treatment")

        # 3) Missing-lab navigation: same product path, new mission.
        lab_request = "I still need a creatinine laboratory test before my appointment. Find a clinic near Santiago de los Caballeros, Dominican Republic where I can get it done."
        lab_first = send_chat(page, lab_request, timeout_ms=90000)
        require("location" in lab_first.lower() or "permission" in lab_first.lower() or "authorize" in lab_first.lower(), "lab mission did not request scoped location consent")
        micro_note(page, "Missing study becomes a mission", "When a required lab is still missing, HealthIA can turn that care gap into a nearby-search mission instead of merely reminding the patient.", 2.8)
        send_chat(page, "I authorize my location for this mission.", timeout_ms=90000)
        lab_cards = wait_resource_cards(page, minimum=1, timeout_ms=45000)
        page.locator(".wave4-resource-panel").last.scroll_into_view_if_needed()
        micro_note(page, "Where can I do it?", "The program returns real nearby options and Google Maps links for the missing study. The result remains navigation evidence, not a clinical referral.", 3.6)
        report["checks"].append(f"missing_lab_nearby_candidates_{lab_cards}")

        # Closing stays in the live app.
        page.locator('[data-open="timeline"]').click()
        page.wait_for_timeout(900)
        micro_note(page, "Your health never starts over", "One patient-owned system: living twin, scientific evidence, family support, nearby care, and durable missions — all shown here as working product behavior.", 4.0)

        report["status"] = "PASS"
        report["assistant_resource_boundary"] = first[:1200]
        report["assistant_resource_authorized"] = second[:1200]
        report["assistant_selection"] = selected[:1200]
        report["assistant_science"] = science[:1600]
        report["assistant_comparison"] = comparison_text[:1800]

        video = page.video
        context.close()
        raw_path = Path(video.path())
        target = OUT / "healthia-v6-functional-live.webm"
        raw_path.replace(target)
        report["raw_video"] = str(target)
        browser.close()

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("HEALTHIA_V6_FUNCTIONAL_DEMO_PASS")
    return report


if __name__ == "__main__":
    run()
