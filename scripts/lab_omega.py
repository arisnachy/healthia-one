from __future__ import annotations

import json
import os
import re
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
MAIN_VIEWS = ("chat", "today", "measurements", "results", "record", "missions")
ACCOUNT_VIEWS = ("profile", "control", "devices")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def checkpoint(label: str) -> None:
    print(f"LAB_OMEGA_CHECKPOINT:{label}", flush=True)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_server(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url}/healthz", timeout=1.5) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"LAB Ω server did not become ready: {last_error}")


def configure_page(page: Page, report: dict) -> None:
    page.set_default_timeout(8_000)
    page.set_default_navigation_timeout(15_000)
    page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
    page.on(
        "response",
        lambda response: report["http_errors"].append({"status": response.status, "url": response.url})
        if response.status >= 400 else None,
    )


def screenshot(page: Page, name: str) -> None:
    page.screenshot(path=str(OUTPUT / f"{name}.png"), full_page=False, animations="disabled", timeout=8_000)


def login_language_probe(browser: Browser, base_url: str, locale: str, expected_lang: str, hero_fragment: str, report: dict) -> None:
    checkpoint(f"login_{expected_lang}_start")
    context = browser.new_context(locale=locale, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    configure_page(page, report)
    page.goto(f"{base_url}/login", wait_until="networkidle")
    require(page.locator("html").get_attribute("lang") == expected_lang, f"{locale} html lang mismatch")
    require(hero_fragment.lower() in page.locator(".auth-brand h1").inner_text().lower(), f"{locale} login copy mismatch")
    report["checks"][f"login_locale_{expected_lang}"] = "pass"
    screenshot(page, f"login-{expected_lang}")
    context.close()
    checkpoint(f"login_{expected_lang}_pass")


def register_and_authenticate(browser: Browser, base_url: str, report: dict) -> BrowserContext:
    checkpoint("register_start")
    context = browser.new_context(
        base_url=base_url,
        locale="en-US",
        viewport={"width": 1600, "height": 1000},
        record_video_dir=str(VIDEO_DIR),
        record_video_size={"width": 1280, "height": 800},
    )
    page = context.new_page()
    configure_page(page, report)
    page.goto("/login", wait_until="networkidle")
    page.locator("#registerTab").click()
    page.locator("#registerForm [name='display_name']").fill("LAB Omega Patient")
    page.locator("#registerForm [name='email']").fill("lab.omega@example.test")
    page.locator("#registerForm [name='password']").fill("LabOmega-2026-safe")
    with page.expect_response("**/api/auth/register") as info:
        page.locator("#registerForm button[type='submit']").click()
    response = info.value
    require(response.status == 201, f"registration returned {response.status}")
    require("healthia_session=" in (response.header_value("set-cookie") or ""), "registration did not emit session cookie")
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/?$"), timeout=15_000)
    cookies = context.cookies(base_url)
    session_cookie = next((item for item in cookies if item.get("name") == "healthia_session"), None)
    require(session_cookie is not None and session_cookie.get("secure") is False, "browser registration cookie invalid for local HTTP")
    session = context.request.get("/api/auth/session", headers={"Accept-Language": "en-US"})
    require(session.status == 200 and session.json().get("authenticated") is True, "registered browser session failed verification")
    report["functions"]["register_and_authenticate"] = "pass"
    report["outputs"]["registration_http_status"] = 201
    report["outputs"]["registration_set_cookie_present"] = True
    report["outputs"]["browser_session_cookie_after_register"] = {
        "present": True,
        "secure": False,
        "sameSite": session_cookie.get("sameSite"),
        "path": session_cookie.get("path"),
    }
    screenshot(page, "registered-browser-session")
    page.close()
    checkpoint("register_pass")
    return context


def open_authenticated_app(context: BrowserContext, report: dict) -> Page:
    checkpoint("functional_session_start")
    session = context.request.get("/api/auth/session", headers={"Accept-Language": "en-US"})
    require(session.status == 200 and session.json().get("authenticated") is True, "preserved browser session is not authenticated")
    page = context.new_page()
    configure_page(page, report)
    page.goto("/", wait_until="domcontentloaded")
    report["outputs"]["functional_page_url"] = page.url
    composer = page.locator("#chatInput")
    composer.wait_for(state="visible", timeout=8_000)
    composer.fill("LAB Omega readiness probe")
    require(composer.input_value() == "LAB Omega readiness probe", "authenticated composer rejected text")
    composer.fill("")
    require(page.locator("html").get_attribute("lang") == "en", "authenticated shell did not follow en-US")
    report["checks"]["authenticated_shell_interactive"] = "pass"
    report["outputs"]["post_register_session_authenticated"] = True
    screenshot(page, "home-authenticated-en")
    checkpoint("functional_session_pass")
    return page


def api_json(context: BrowserContext, path: str) -> dict:
    response = context.request.get(path, headers={"Accept-Language": "en-US"})
    require(response.ok, f"{path} returned {response.status}")
    return response.json()


def exercise_registered_views(page: Page, report: dict) -> None:
    checkpoint("views_start")
    for index, view in enumerate(MAIN_VIEWS, start=1):
        checkpoint(f"view_{view}_start")
        page.locator(f".main-nav [data-open='{view}']").click()
        page.locator(f"#view-{view}").wait_for(state="visible")
        report["windows"][view] = "pass"
        screenshot(page, f"view-{index:02d}-{view}")
        checkpoint(f"view_{view}_pass")
    checkpoint("views_pass")


def fill_and_save(page: Page, dialog_type: str, values: dict[str, str], report: dict) -> None:
    checkpoint(f"save_{dialog_type}_start")
    page.locator(f"[data-dialog='{dialog_type}']").first.click()
    page.locator("#dataDialog").wait_for(state="visible")
    for name, value in values.items():
        page.locator(f"#dataForm [name='{name}']").fill(value)
    page.locator("#saveData").click()
    page.locator("#dataDialog").wait_for(state="hidden")
    report["functions"][f"save_{dialog_type}"] = "pass"
    checkpoint(f"save_{dialog_type}_pass")


def verify_measurements(context: BrowserContext, page: Page, report: dict) -> None:
    checkpoint("measurements_start")
    page.locator(".main-nav [data-open='measurements']").click()
    fill_and_save(page, "vital", {"systolic": "126", "diastolic": "78", "pulse": "72", "oxygen_saturation": "98"}, report)
    fill_and_save(page, "weight", {"weight_kg": "74.2", "note": "LAB Omega synthetic"}, report)
    fill_and_save(page, "activity", {"steps": "6842", "active_minutes": "42", "note": "LAB Omega synthetic"}, report)
    state = api_json(context, "/api/bootstrap")
    require(state["vitals"][-1]["systolic"] == 126 and state["vitals"][-1]["diastolic"] == 78, "blood pressure did not persist")
    require(abs(float(state["weights"][-1]["weight_kg"]) - 74.2) < 0.001, "weight did not persist")
    require(state["activity"][-1]["steps"] == 6842, "activity did not persist")
    report["outputs"]["measurement_state_roundtrip"] = "pass"
    screenshot(page, "measurements-after-save")
    checkpoint("measurements_pass")


def verify_structured_result(context: BrowserContext, page: Page, report: dict) -> None:
    checkpoint("result_start")
    page.locator(".main-nav [data-open='results']").click()
    payload = json.dumps({
        "panel": "LAB Omega metabolic panel",
        "results": [
            {"name": "Creatinine", "value": 0.9, "unit": "mg/dL", "reference": "0.6-1.2"},
            {"name": "Hemoglobin", "value": 13.4, "unit": "g/dL", "reference": "12-16"},
        ],
    }).encode("utf-8")
    page.locator("#resultFilePage").set_input_files(files=[{"name": "lab-omega-result.json", "mime_type": "application/json", "buffer": payload}])
    card = page.locator("#resultList [data-result-id]").first
    card.wait_for(state="visible")
    card_text = card.inner_text()
    require("LAB Omega metabolic panel" in card_text, "structured result panel missing")
    require("educational explanation" in card_text.lower(), "English result explanation missing")
    require("View original file" in card_text, "original-evidence link missing")
    state = api_json(context, "/api/bootstrap")
    result = state["results"][-1]
    require(result["status"] == "parsed" and len(result["items"]) == 2, "structured result did not persist")
    require(state["documents"][-1]["related_result_id"] == result["id"], "original document not linked to result")
    report["functions"]["structured_result_upload"] = "pass"
    report["outputs"]["english_result_explanation"] = "pass"
    report["outputs"]["result_original_provenance"] = "pass"
    screenshot(page, "results-structured-upload")
    checkpoint("result_pass")


def verify_input_language_headers(page: Page, report: dict) -> None:
    checkpoint("language_start")
    observed: list[str] = []
    page.on(
        "request",
        lambda request: observed.append(request.headers.get("accept-language", ""))
        if request.url.endswith("/api/chat") and request.method == "POST" else None,
    )
    page.locator(".main-nav [data-open='chat']").click()
    page.locator("#chatInput").fill("Please show my latest results and help me understand them")
    page.locator("#sendButton").click()
    page.wait_for_timeout(700)
    page.locator("#chatInput").fill("Quiero ver mis resultados y entender qué significan")
    page.locator("#sendButton").click()
    page.wait_for_timeout(700)
    require(any(value.startswith("en") for value in observed), f"English input locale missing: {observed}")
    require(any(value.startswith("es") for value in observed), f"Spanish input override missing: {observed}")
    report["outputs"]["input_language_to_backend_en"] = "pass"
    report["outputs"]["input_language_to_backend_es"] = "pass"
    checkpoint("language_pass")


def verify_account_views_and_logout(page: Page, report: dict) -> None:
    checkpoint("account_start")
    page.locator("#accountPill").click()
    dialog = page.locator("#accountDialog")
    dialog.wait_for(state="visible")
    account_text = dialog.inner_text()
    require("Account & settings" in account_text and "lab.omega" in account_text.lower(), "account identity/localization missing")
    report["windows"]["account_dialog"] = "pass"
    screenshot(page, "account-dialog")
    for target in ACCOUNT_VIEWS:
        checkpoint(f"account_{target}_start")
        if not dialog.is_visible():
            page.locator("#accountPill").click()
            dialog.wait_for(state="visible")
        page.locator(f"[data-account-view='{target}']").click()
        page.locator(f"#view-{target}").wait_for(state="visible")
        report["windows"][f"account_{target}"] = "pass"
        screenshot(page, f"account-view-{target}")
        checkpoint(f"account_{target}_pass")
    if not dialog.is_visible():
        page.locator("#accountPill").click()
        dialog.wait_for(state="visible")
    page.locator("#logoutButton").click()
    page.wait_for_url(re.compile(r".*/login$"), timeout=15_000)
    page.locator("#loginForm").wait_for(state="visible")
    report["functions"]["logout"] = "pass"
    checkpoint("account_pass")


def run() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "RUNNING",
        "lab": "LAB OMEGA",
        "mode": "real_local_browser_zero_ai_spend",
        "console_errors": [],
        "page_errors": [],
        "http_errors": [],
        "checks": {},
        "windows": {},
        "functions": {},
        "outputs": {},
    }
    with tempfile.TemporaryDirectory(prefix="healthia-lab-") as temp_dir:
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({
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
        })
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
                context = register_and_authenticate(browser, base_url, report)
                page = open_authenticated_app(context, report)
                exercise_registered_views(page, report)
                checkpoint("collapse_start")
                page.locator("#collapseLeft").click()
                page.locator("#expandLeft").wait_for(state="visible")
                page.locator("#expandLeft").click()
                page.locator("#collapseLeft").wait_for(state="visible")
                report["functions"]["left_navigation_collapse_expand"] = "pass"
                page.locator("#collapseRight").click()
                page.locator("#collapseRight").click()
                report["functions"]["context_collapse_expand"] = "pass"
                checkpoint("collapse_pass")
                verify_measurements(context, page, report)
                verify_structured_result(context, page, report)
                verify_input_language_headers(page, report)
                verify_account_views_and_logout(page, report)
                require(not report["console_errors"], f"browser console errors: {report['console_errors']}")
                require(not report["page_errors"], f"browser page errors: {report['page_errors']}")
                require(not report["http_errors"], f"browser HTTP errors: {report['http_errors']}")
                context.close()
                browser.close()
                report["status"] = "PASS"
                checkpoint("lab_core_pass")
        except Exception as exc:
            report["status"] = "FAIL"
            report["error"] = f"{type(exc).__name__}: {exc}"
            checkpoint(f"lab_core_fail_{type(exc).__name__}")
            raise
        finally:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)
            if report["status"] != "PASS" and server.stdout:
                report["server_tail"] = server.stdout.read()[-4000:]
            (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False, indent=2))
    except Exception:
        path = OUTPUT / "report.json"
        if path.exists():
            print(path.read_text(encoding="utf-8"))
        raise