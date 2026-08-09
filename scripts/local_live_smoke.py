from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    base_url = os.getenv("HEALTHIA_SMOKE_URL", "http://127.0.0.1:8000").rstrip("/")
    email = os.environ["HEALTHIA_SMOKE_EMAIL"]
    password = os.environ["HEALTHIA_SMOKE_PASSWORD"]
    report = {"status": "PASS", "views": [], "console_errors": [], "page_errors": []}
    evidence_dir = Path(__file__).resolve().parents[1] / "dist" / "local-live-smoke"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        print("launch", flush=True)
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
        print(f"opened {page.url}", flush=True)
        if "/login" in page.url:
            page.locator('#loginForm input[name="email"]').fill(email)
            page.locator('#loginForm input[name="password"]').fill(password)
            page.locator('#loginForm button[type="submit"]').click()
            page.wait_for_url(base_url + "/", timeout=30_000)
            print("authenticated", flush=True)

        page.locator("#chatInput").wait_for(state="visible", timeout=30_000)
        print("composer visible", flush=True)
        page.locator("#chatInput").fill("abc++def")
        if page.locator("#chatInput").input_value() != "abc++def":
            raise RuntimeError("El compositor no conserva exactamente abc++def")

        if page.locator(".message.assistant").count() and page.locator(".message.assistant .healthia-avatar").count() < 1:
            raise RuntimeError("El avatar vectorial de HealthIA no aparece en el chat")
        before_results = page.locator("#resultList [data-result-id]").count()
        with page.expect_response(lambda response: response.url.endswith("/api/consultations/new") and response.ok, timeout=10_000):
            page.locator("#newConsultation").click()
        page.wait_for_timeout(500)
        visible_messages = page.locator("#messageList .message").count()
        if visible_messages != 0 or not page.locator("#chatScroll").evaluate("node => node.classList.contains('entry-mode')"):
            raise RuntimeError(f"La consulta nueva debe volver al estado de entrada limpio; hay {visible_messages} mensajes")

        views = ["chat", "today", "measurements", "results", "record", "missions", "devices"]
        for view in views:
            print(f"view {view}", flush=True)
            trigger = page.locator(f'[data-open="{view}"]').first
            trigger.click(timeout=5_000)
            page.locator(f"#view-{view}.is-active").wait_for(state="visible", timeout=5_000)
            report["views"].append(view)
            page.wait_for_timeout(150)

        if page.locator("#resultList [data-result-id]").count() != before_results:
            raise RuntimeError("Nueva consulta alteró los resultados longitudinales")
        page.screenshot(path=str(evidence_dir / "results.png"), full_page=True)
        preview_button = page.locator("#resultList [data-open-original]").first
        if preview_button.count():
            preview_button.click()
            page.locator("#originalPreviewDialog[open]").wait_for(state="visible", timeout=5_000)
            if page.locator("#originalPreviewBody img, #originalPreviewBody iframe").count() != 1:
                raise RuntimeError("El original no se abrió inline en el diálogo")
            page.screenshot(path=str(evidence_dir / "original-modal.png"), full_page=True)
            page.locator("#closeOriginalPreview").click()

        page.wait_for_timeout(500)
        if report["page_errors"] or report["console_errors"]:
            report["status"] = "FAIL"
            raise RuntimeError(json.dumps(report, ensure_ascii=False))
        browser.close()

    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
