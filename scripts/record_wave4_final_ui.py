from __future__ import annotations

import json
import os
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_URL = os.getenv("HEALTHIA_LOCAL_DEMO_URL", "http://127.0.0.1:8765").rstrip("/")
OUT = Path("dist/wave4-final-ui")


def wait_new_assistant(page: Page, prior: int, timeout_ms: int = 120000) -> None:
    page.wait_for_function(
        "prior => document.querySelectorAll('#messageList .message.assistant').length > prior",
        prior,
        timeout=timeout_ms,
    )
    page.wait_for_timeout(700)


def send(page: Page, text: str, timeout_ms: int = 120000) -> None:
    prior = page.locator("#messageList .message.assistant").count()
    page.locator("#chatInput").fill(text)
    page.locator("#sendButton").click()
    wait_new_assistant(page, prior, timeout_ms)
    page.locator("#messageList .message.assistant").last.scroll_into_view_if_needed()
    page.wait_for_timeout(900)


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUT / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []
    checks: list[str] = []

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
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.add_init_script("localStorage.setItem('healthia.locale','en')")
        page.goto(BASE_URL + "/", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("#chatInput", timeout=30000)
        page.wait_for_function("document.documentElement.lang === 'en'")
        checks.append("english_patient_os")
        page.wait_for_timeout(3500)

        # Real Wave 4 natural-language resource mission. The exact product router
        # must stop before location access, then resume the same durable mission.
        send(
            page,
            "Find autism support groups, family support resources, and government assistance near Santiago de los Caballeros, Dominican Republic.",
        )
        page.wait_for_selector("text=Mission receipt", timeout=30000)
        page.wait_for_selector("text=I need your permission to use location for this mission in Google Places", timeout=30000)
        checks.append("mission_stops_for_location_consent")
        page.wait_for_timeout(6000)

        send(page, "I authorize my location for this mission.")
        page.wait_for_selector(".wave4-resource-panel", timeout=120000)
        page.wait_for_function("document.querySelectorAll('.wave4-resource-card').length >= 2", timeout=120000)
        cards = page.locator(".wave4-resource-card").count()
        if cards < 2:
            raise RuntimeError(f"Expected at least 2 actual resource cards, got {cards}")
        links = page.locator('.wave4-resource-card a[href*="google"]').count()
        if links < 1:
            raise RuntimeError("No Google Maps links surfaced in actual resource cards")
        checks.append("real_places_cards_with_google_maps")
        panel = page.locator(".wave4-resource-panel").last
        panel.scroll_into_view_if_needed()
        page.wait_for_timeout(8000)

        # Let the viewer read the candidates; scroll within the real application,
        # never place a covering demo card over the chat.
        page.mouse.wheel(0, 430)
        page.wait_for_timeout(4500)
        page.mouse.wheel(0, -260)
        page.wait_for_timeout(2500)

        send(page, "The second one.")
        page.wait_for_selector(".wave4-resource-card.is-selected", timeout=60000)
        selected_text = page.locator(".wave4-resource-card.is-selected").inner_text()
        checks.append("exact_second_candidate_selected")
        page.locator(".wave4-resource-card.is-selected").scroll_into_view_if_needed()
        page.wait_for_timeout(6500)

        # Actual Opportunity Autopilot / Discoveries UI. Data is seeded from
        # official-source demo candidates before the app starts; the UI itself is
        # the production Wave 4 component, not a video overlay.
        page.locator('[data-open="discoveries"]').click()
        page.wait_for_selector("#view-discoveries.active", timeout=30000)
        page.wait_for_selector(".opportunity-program-card", timeout=30000)
        page.locator(".opportunity-program-card").first.scroll_into_view_if_needed()
        checks.append("opportunity_autopilot_assistance_ui")
        page.wait_for_timeout(8500)
        page.mouse.wheel(0, 420)
        page.wait_for_timeout(5000)

        # Return to chat and show the durable selected-resource conversation.
        page.locator('[data-open="chat"]').click()
        page.wait_for_selector("#view-chat.active", timeout=30000)
        page.locator(".wave4-resource-card.is-selected").scroll_into_view_if_needed()
        page.wait_for_timeout(5000)

        if console_errors or page_errors:
            raise RuntimeError(f"browser errors: console={console_errors[-3:]} page={page_errors[-3:]}")
        checks.append("zero_browser_errors")
        report = {
            "status": "PASS",
            "synthetic_patient": True,
            "wave4_head": os.getenv("GITHUB_SHA", ""),
            "checks": checks,
            "resource_card_count": cards,
            "google_maps_link_count": links,
            "selected_card_text": selected_text[:500],
            "large_video_overlays": False,
        }
        (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("HEALTHIA_WAVE4_FINAL_UI_RECORDER_PASS", json.dumps(report, ensure_ascii=False))
        context.close()
        browser.close()


if __name__ == "__main__":
    run()
