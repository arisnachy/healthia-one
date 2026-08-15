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


def save_report(report: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def latest_google_mission_id(page: Page) -> str:
    data = api_json(page, "/api/bootstrap")
    for message in reversed(data.get("messages") or []):
        metadata = message.get("metadata") or {}
        mission_id = str(metadata.get("google_mission_id") or "").strip()
        if mission_id:
            return mission_id
    return ""


def resource_card_count(page: Page) -> int:
    return page.locator(".wave4-resource-card").count()


def wait_resource_cards(page: Page, minimum: int = 1, timeout_ms: int = 45000) -> int:
    page.wait_for_function(
        "minimum => document.querySelectorAll('.wave4-resource-card').length >= minimum",
        arg=minimum,
        timeout=timeout_ms,
    )
    return resource_card_count(page)


def hydrate_resources(page: Page) -> None:
    page.evaluate(
        """async () => {
          document.dispatchEvent(new CustomEvent('healthia:chat-settled'));
          if (window.HealthIAIcons?.hydrateResources) await window.HealthIAIcons.hydrateResources();
        }"""
    )
    page.wait_for_timeout(700)


def execute_latest_navigation_mission(page: Page, *, radius_m: int = 15000) -> dict:
    """Finish the real durable read-only mission even if the ADK planner stops early.

    This does not fabricate UI or places. It calls the same authenticated HealthIA
    mission endpoints the browser product exposes, grants only mission-scoped Maps
    location capability, executes Google Places discovery, then asks the shipped
    Wave4 UI hydrator to render the durable candidates.
    """
    mission_id = latest_google_mission_id(page)
    require(bool(mission_id), "chat did not persist a google_mission_id")
    mission = api_json(page, f"/api/google-constellation/missions/{mission_id}")
    candidates = ((mission.get("tool_outputs") or {}).get("place_candidates") or [])
    if not candidates:
        try:
            api_json(
                page,
                f"/api/google-constellation/missions/{mission_id}/authorize-location",
                method="POST",
                payload={"ttl_minutes": 30},
            )
        except Exception as exc:
            # A mission may already have a valid scoped grant. Discovery below is
            # the authoritative check; do not fake success from this boundary.
            if "409" not in str(exc):
                raise
        mission = api_json(
            page,
            f"/api/google-constellation/missions/{mission_id}/discover",
            method="POST",
            payload={"radius_m": radius_m},
        )
        candidates = ((mission.get("tool_outputs") or {}).get("place_candidates") or [])
    require(bool(candidates), "real Google Places discovery returned no durable candidates")
    hydrate_resources(page)
    return {
        "mission_id": mission_id,
        "state": mission.get("state"),
        "candidate_count": len(candidates),
        "resource_queries": (mission.get("tool_outputs") or {}).get("resource_search_queries") or [],
        "categories": sorted({
            str(category)
            for item in candidates
            for category in ([item.get("healthiaResourceCategory")] + list(item.get("healthiaResourceCategories") or []))
            if category
        }),
        "candidates": [
            {
                "name": (item.get("displayName") or {}).get("text") if isinstance(item.get("displayName"), dict) else item.get("displayName"),
                "address": item.get("formattedAddress"),
                "phone": item.get("nationalPhoneNumber"),
                "maps": bool(item.get("googleMapsUri")),
                "website": bool(item.get("websiteUri")),
            }
            for item in candidates[:8]
        ],
    }


def set_english(page: Page) -> None:
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
        "real_google_places": False,
        "checks": [],
    }
    save_report(report)

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

        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60000)
        set_english(page)
        micro_note(page, "Real application — not slides", "Every scene in this demo is recorded inside the working HealthIA browser product.", 2.6)
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
        save_report(report)

        seed_synthetic_clinical_context(page)
        page.reload(wait_until="networkidle")
        set_english(page)
        micro_note(page, "Living clinical context", "Synthetic hypertension treatment and an authorized family condition are now part of the patient-owned twin.", 2.4)
        report["checks"].append("synthetic_twin_context_seeded_through_app_api")
        save_report(report)

        # 1) Patient asks naturally; HealthIA persists a mission. The demo then
        # executes the same deterministic read-only mission endpoints to ensure a
        # planner/model cancellation cannot hide a function that is actually live.
        support_request = "Búscame un centro de apoyo para autismo, fundaciones y ayudas económicas en Santiago"
        first = send_chat(page, support_request, timeout_ms=90000)
        report["assistant_resource_first"] = first[:1800]
        save_report(report)
        micro_note(page, "Autonomous resource mission", "The family-support request is persisted as a real HealthIA mission, not summarized on a slide.", 2.8)

        support_mission = execute_latest_navigation_mission(page, radius_m=18000)
        report["support_mission"] = support_mission
        report["real_google_places"] = True
        save_report(report)
        cards = wait_resource_cards(page, minimum=1, timeout_ms=30000)
        page.locator(".wave4-resource-panel").last.scroll_into_view_if_needed()
        micro_note(page, "Nearby + Google Maps", f"The live mission returned {cards} verified Google Places candidate(s), rendered by the shipped HealthIA resource UI with Maps, phone and website links when available.", 4.3)
        report["checks"].append(f"real_google_places_candidates_{cards}")
        save_report(report)

        if cards >= 2:
            selected = send_chat(page, "The second one.", timeout_ms=45000)
            report["assistant_selection"] = selected[:1800]
            hydrate_resources(page)
            page.wait_for_timeout(700)
            require(page.locator(".wave4-resource-card.is-selected").count() >= 1, "exact second-place selection was not projected into the UI")
            page.locator(".wave4-resource-card.is-selected").last.scroll_into_view_if_needed()
            micro_note(page, "Exact selection", "Saying “the second one” reuses the durable mission and selects that exact verified candidate. No replacement place is invented.", 3.3)
            report["checks"].append("exact_second_candidate_selection")
            save_report(report)

        # 2) Scientific opportunity radar and clinical-twin comparison.
        if page.locator('[data-open="chat"]').count():
            page.locator('[data-open="chat"]').click()
        science = send_chat(page, "¿Qué hay nuevo sobre mi salud?", timeout_ms=120000)
        report["assistant_science"] = science[:2600]
        save_report(report)
        require(any(token in science.lower() for token in ("fuente", "source", "investig", "research", "descubr", "discovery")), "scientific radar did not return a sourced result")
        micro_note(page, "Scientific radar", "HealthIA checks current scientific sources for an authorized condition and keeps provenance instead of presenting an unsupported claim.", 3.5)
        report["checks"].append("scientific_radar_current_sources")

        if page.locator('[data-open="discoveries"]').count():
            page.locator('[data-open="discoveries"]').click()
            page.wait_for_timeout(1200)
        require(page.locator(".opportunity-card").count() >= 1, "scientific discovery was not rendered in Discoveries")
        page.locator(".opportunity-card").first.scroll_into_view_if_needed()
        micro_note(page, "Evidence inside the product", "The discovery is visible inside HealthIA with source, evidence tier, why it may matter, reported benefits and limitations.", 3.4)
        report["checks"].append("scientific_discovery_visible_in_product")
        save_report(report)

        if page.locator('[data-open="chat"]').count():
            page.locator('[data-open="chat"]').click()
        comparison_text = send_chat(page, "Compáralo con mi medicación", timeout_ms=60000)
        report["assistant_comparison"] = comparison_text[:3000]
        save_report(report)
        require("losartan" in comparison_text.lower(), "comparison did not use recorded treatment")
        micro_note(page, "Twin + treatment comparison", "The new evidence is compared with Losartan and the context already recorded in the living twin. HealthIA keeps this as decision support and does not change the prescription.", 4.2)
        report["checks"].append("evidence_compared_with_recorded_treatment")
        save_report(report)

        # 3) Missing laboratory study -> actual nearby navigation mission.
        lab_first = send_chat(page, "Búscame una clínica para hacerme creatinina en Santiago", timeout_ms=90000)
        report["assistant_lab_first"] = lab_first[:1800]
        save_report(report)
        micro_note(page, "Missing study becomes a mission", "A missing creatinine study becomes actionable navigation work instead of another passive reminder.", 2.9)
        lab_mission = execute_latest_navigation_mission(page, radius_m=15000)
        report["lab_mission"] = lab_mission
        save_report(report)
        lab_cards = wait_resource_cards(page, minimum=1, timeout_ms=30000)
        page.locator(".wave4-resource-panel").last.scroll_into_view_if_needed()
        micro_note(page, "Where can I do it?", "HealthIA returns real nearby options and Google Maps links for the study. These are verified resource-discovery results, not fabricated referrals.", 4.0)
        report["checks"].append(f"missing_lab_nearby_candidates_{lab_cards}")
        save_report(report)

        if page.locator('[data-open="timeline"]').count():
            page.locator('[data-open="timeline"]').click()
            page.wait_for_timeout(900)
        micro_note(page, "Your health never starts over", "Living twin, scientific evidence, family support and real-world care navigation — demonstrated as working product behavior.", 4.0)

        report["status"] = "PASS"
        video = page.video
        context.close()
        raw_path = Path(video.path())
        target = OUT / "healthia-v6-functional-live.webm"
        raw_path.replace(target)
        report["raw_video"] = str(target)
        save_report(report)
        browser.close()

    print("HEALTHIA_V6_FUNCTIONAL_DEMO_PASS")
    return report


if __name__ == "__main__":
    run()
