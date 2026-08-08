from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "lab-omega"
VIDEO_DIR = OUTPUT / "video"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_server(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(f"{url}/healthz", timeout=1.5) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"LAB Ω server did not become ready: {last_error}")


def screenshot(page: Page, name: str) -> str:
    target = OUTPUT / f"{name}.png"
    page.screenshot(path=str(target), full_page=True)
    return str(target.relative_to(ROOT))


def page_errors(page: Page, report: dict) -> None:
    page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: report["page_errors"].append(str(error)))


def login_language_probe(browser: Browser, base_url: str, locale: str, expected_lang: str, expected_hero: str, report: dict) -> None:
    context = browser.new_context(locale=locale, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page_errors(page, report)
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.wait_for_function(f"document.documentElement.lang === '{expected_lang}'")
    hero = page.locator(".auth-brand h1").inner_text().strip()
    require(expected_hero.lower() in hero.lower(), f"{locale} login did not localize: {hero!r}")
    report["checks"][f"login_locale_{expected_lang}"] = "pass"
    screenshot(page, f"login-{expected_lang}")
    context.close()


def bootstrap(page: Page) -> dict:
    return page.evaluate("async () => await (await fetch('/api/bootstrap')).json()")


def assert_visible_view(page: Page, view: str) -> None:
    locator = page.locator(f"#view-{view}")
    require(locator.count() == 1, f"view {view!r} has no matching #view-{view}")
    require(locator.is_visible(), f"view {view!r} did not become visible")


def exercise_registered_views(page: Page, report: dict) -> None:
    views = page.eval_on_selector_all(
        "[data-open]",
        "nodes => [...new Set(nodes.map(node => node.dataset.open).filter(Boolean))]",
    )
    require("chat" in views, "chat view missing from data-open registry")
    for index, view in enumerate(views, start=1):
        button = page.locator(f"[data-open='{view}']").first
        require(button.count() == 1, f"no control for registered view {view}")
        button.click()
        page.wait_for_timeout(120)
        assert_visible_view(page, view)
        report["windows"][view] = "pass"
        screenshot(page, f"view-{index:02d}-{view}")


def fill_and_save(page: Page, dialog_type: str, values: dict[str, str], report: dict) -> None:
    page.locator(f"[data-dialog='{dialog_type}']").first.click()
    dialog = page.locator("#dataDialog")
    require(dialog.is_visible(), f"{dialog_type} dialog did not open")
    for name, value in values.items():
        page.locator(f"#dataForm [name='{name}']").fill(value)
    page.locator("#saveData").click()
    page.wait_for_function("!document.querySelector('#dataDialog').open")
    report["functions"][f"save_{dialog_type}"] = "pass"


def verify_measurements(page: Page, report: dict) -> None:
    page.locator(".main-nav [data-open='measurements']").click()
    fill_and_save(page, "vital", {"systolic": "126", "diastolic": "78", "pulse": "72", "oxygen_saturation": "98"}, report)
    fill_and_save(page, "weight", {"weight_kg": "74.2", "note": "LAB Omega synthetic"}, report)
    fill_and_save(page, "activity", {"steps": "6842", "active_minutes": "42", "note": "LAB Omega synthetic"}, report)
    state = bootstrap(page)
    require(state["vitals"][-1]["systolic"] == 126 and state["vitals"][-1]["diastolic"] == 78, "blood pressure did not persist")
    require(abs(float(state["weights"][-1]["weight_kg"]) - 74.2) < 0.001, "weight did not persist")
    require(state["activity"][-1]["steps"] == 6842, "activity did not persist")
    report["outputs"]["measurement_state_roundtrip"] = "pass"
    screenshot(page, "measurements-after-save")


def verify_structured_result(page: Page, report: dict) -> None:
    page.locator(".main-nav [data-open='results']").click()
    payload = json.dumps(
        {
            "panel": "LAB Omega metabolic panel",
            "results": [
                {"name": "Creatinine", "value": 0.9, "unit": "mg/dL", "reference": "0.6-1.2"},
                {"name": "Hemoglobin", "value": 13.4, "unit": "g/dL", "reference": "12-16"},
            ],
        }
    ).encode("utf-8")
    page.locator("#resultFilePage").set_input_files(
        files=[{"name": "lab-omega-result.json", "mime_type": "application/json", "buffer": payload}]
    )
    page.wait_for_function("document.querySelectorAll('#resultList [data-result-id]').length > 0")
    card_text = page.locator("#resultList [data-result-id]").first.inner_text()
    require("LAB Omega metabolic panel" in card_text, "structured result panel not rendered")
    require("educational explanation" in card_text.lower(), "English structured explanation not rendered under en-US OS locale")
    require("View original file" in card_text, "original-evidence link missing")
    state = bootstrap(page)
    result = state["results"][-1]
    require(result["status"] == "parsed" and len(result["items"]) == 2, "structured result did not persist correctly")
    require(state["documents"][-1]["related_result_id"] == result["id"], "original document was not correlated to result")
    report["functions"]["structured_result_upload"] = "pass"
    report["outputs"]["english_result_explanation"] = "pass"
    report["outputs"]["result_original_provenance"] = "pass"
    screenshot(page, "results-structured-upload")


def verify_input_language_headers(page: Page, report: dict) -> None:
    observed: list[str] = []

    def capture(request) -> None:
        if request.url.endswith("/api/chat") and request.method == "POST":
            observed.append(request.headers.get("accept-language", ""))

    page.on("request", capture)
    page.locator(".main-nav [data-open='chat']").click()
    page.locator("#chatInput").fill("Please show my latest results and help me understand them")
    page.locator("#sendButton").click()
    page.wait_for_timeout(500)
    page.locator("#chatInput").fill("Quiero ver mis resultados y entender qué significan")
    page.locator("#sendButton").click()
    page.wait_for_timeout(500)
    require(any(value.startswith("en") for value in observed), f"English input did not send English locale: {observed}")
    require(any(value.startswith("es") for value in observed), f"Spanish input did not override OS language: {observed}")
    report["outputs"]["input_language_to_backend_en"] = "pass"
    report["outputs"]["input_language_to_backend_es"] = "pass"


def verify_account_views_and_logout(page: Page, report: dict) -> None:
    page.locator("#accountPill").click()
    dialog = page.locator("#accountDialog")
    require(dialog.is_visible(), "account dialog did not open")
    account_text = dialog.inner_text()
    require("Account & settings" in account_text, "account dialog did not follow English OS locale")
    require("lab.omega" in account_text, "authenticated account identity missing")
    report["windows"]["account_dialog"] = "pass"
    screenshot(page, "account-dialog")

    targets = page.eval_on_selector_all("[data-account-view]", "nodes => nodes.map(node => node.dataset.accountView)")
    for target in targets:
        if not dialog.is_visible():
            page.locator("#accountPill").click()
        page.locator(f"[data-account-view='{target}']").click()
        page.wait_for_timeout(150)
        assert_visible_view(page, target)
        report["windows"][f"account_{target}"] = "pass"
        screenshot(page, f"account-view-{target}")

    page.locator("#accountPill").click()
    page.locator("#logoutButton").click()
    page.wait_for_url("**/login")
    require(page.locator("#loginForm").is_visible(), "logout did not return to login")
    report["functions"]["logout"] = "pass"


def run() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "RUNNING",
        "lab": "LAB OMEGA",
        "mode": "real_local_browser_zero_ai_spend",
        "console_errors": [],
        "page_errors": [],
        "checks": {},
        "windows": {},
        "functions": {},
        "outputs": {},
    }

    with tempfile.TemporaryDirectory(prefix="healthia-lab-") as temp_dir:
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(
            {
                "HEALTHIA_ENV": "local",
                "HEALTHIA_AUTH_REQUIRED": "true",
                "HEALTHIA_ALLOW_REGISTRATION": "true",
                "HEALTHIA_STORE_BACKEND": "memory",
                "HEALTHIA_LLM_BACKEND": "mock",
                "HEALTHIA_COST_MODE": "local",
                "HEALTHIA_AI_REQUEST_LIMIT": "0",
                "HEALTHIA_PROACTIVE_ENABLED": "false",
                "HEALTHIA_ACCOUNTS_PATH": str(Path(temp_dir) / "accounts.json"),
                "HEALTHIA_DATA_PATH": str(Path(temp_dir) / "state.json"),
                "PYTHONPATH": str(ROOT),
            }
        )
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_server(base_url)
            with sync_playwright() as playwright:
                launch: dict = {"headless": True, "args": ["--no-sandbox"]}
                explicit = os.getenv("HEALTHIA_CHROMIUM_EXECUTABLE")
                if explicit:
                    launch["executable_path"] = explicit
                elif Path("/usr/bin/chromium").exists():
                    launch["executable_path"] = "/usr/bin/chromium"
                browser = playwright.chromium.launch(**launch)

                login_language_probe(browser, base_url, "en-US", "en", "Your health should remember you", report)
                login_language_probe(browser, base_url, "es-DO", "es", "Tu salud debería recordarte", report)

                context: BrowserContext = browser.new_context(
                    locale="en-US",
                    viewport={"width": 1600, "height": 1000},
                    record_video_dir=str(VIDEO_DIR),
                    record_video_size={"width": 1280, "height": 800},
                )
                page = context.new_page()
                page_errors(page, report)
                page.goto(f"{base_url}/login", wait_until="networkidle")
                page.locator("#registerTab").click()
                page.locator("#registerForm [name='display_name']").fill("LAB Omega Patient")
                page.locator("#registerForm [name='email']").fill("lab.omega@example.test")
                page.locator("#registerForm [name='password']").fill("LabOmega-2026-safe")
                page.locator("#registerForm button[type='submit']").click()
                page.wait_for_url(f"{base_url}/")
                page.wait_for_selector("#chatInput")
                page.wait_for_function("document.documentElement.lang === 'en'")
                report["functions"]["register_and_authenticate"] = "pass"
                screenshot(page, "home-authenticated-en")

                exercise_registered_views(page, report)

                page.locator("#collapseLeft").click()
                require(page.locator("#app").evaluate("node => node.classList.contains('left-collapsed')"), "left rail did not collapse")
                page.locator("#expandLeft").click()
                require(not page.locator("#app").evaluate("node => node.classList.contains('left-collapsed')"), "left rail did not reopen")
                report["functions"]["left_navigation_collapse_expand"] = "pass"

                page.locator("#collapseRight").click()
                require(page.locator("#app").evaluate("node => node.classList.contains('right-collapsed')"), "context panel did not collapse")
                page.locator("#collapseRight").click()
                require(not page.locator("#app").evaluate("node => node.classList.contains('right-collapsed')"), "context panel did not reopen")
                report["functions"]["context_collapse_expand"] = "pass"

                verify_measurements(page, report)
                verify_structured_result(page, report)
                verify_input_language_headers(page, report)
                verify_account_views_and_logout(page, report)

                require(not report["console_errors"], f"browser console errors: {report['console_errors']}")
                require(not report["page_errors"], f"browser page errors: {report['page_errors']}")
                context.close()
                browser.close()
        except Exception as exc:
            report["status"] = "FAIL"
            report["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:  # pragma: no cover
                server.kill()
                server.wait(timeout=3)
            if report["status"] != "PASS" and server.stdout:
                report["server_tail"] = server.stdout.read()[-4000:]
            report_path = OUTPUT / "report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    report["status"] = "PASS"
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False, indent=2))
    except Exception:
        report_path = OUTPUT / "report.json"
        if report_path.exists():
            print(report_path.read_text(encoding="utf-8"))
        raise
