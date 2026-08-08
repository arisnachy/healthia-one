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

import httpx
from playwright.sync_api import Browser, Page, sync_playwright


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


def screenshot(page: Page, name: str) -> None:
    page.screenshot(
        path=str(OUTPUT / f"{name}.png"),
        full_page=False,
        animations="disabled",
        timeout=8_000,
    )


def attach_diagnostics(page: Page, report: dict) -> None:
    page.on(
        "console",
        lambda message: report["console_errors"].append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
    page.on(
        "response",
        lambda response: report["http_errors"].append(
            {"status": response.status, "url": response.url}
        )
        if response.status >= 400
        else None,
    )


def configure_page(page: Page, report: dict) -> None:
    page.set_default_timeout(8_000)
    page.set_default_navigation_timeout(15_000)
    attach_diagnostics(page, report)


def login_language_probe(
    browser: Browser,
    base_url: str,
    locale: str,
    expected_lang: str,
    expected_hero: str,
    report: dict,
) -> None:
    checkpoint(f"login_probe_{expected_lang}_start")
    context = browser.new_context(locale=locale, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    configure_page(page, report)
    page.goto(f"{base_url}/login", wait_until="networkidle")
    require(page.locator("html").get_attribute("lang") == expected_lang, f"{locale} html lang mismatch")
    hero = page.locator(".auth-brand h1").inner_text().strip()
    require(expected_hero.lower() in hero.lower(), f"{locale} login did not localize: {hero!r}")
    report["checks"][f"login_locale_{expected_lang}"] = "pass"
    screenshot(page, f"login-{expected_lang}")
    context.close()
    checkpoint(f"login_probe_{expected_lang}_pass")


def register_through_real_browser(browser: Browser, base_url: str, report: dict) -> None:
    checkpoint("browser_registration_start")
    context = browser.new_context(locale="en-US", viewport={"width": 1440, "height": 900})
    page = context.new_page()
    configure_page(page, report)
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.locator("#registerTab").click()
    page.locator("#registerForm [name='display_name']").fill("LAB Omega Patient")
    page.locator("#registerForm [name='email']").fill("lab.omega@example.test")
    page.locator("#registerForm [name='password']").fill("LabOmega-2026-safe")
    with page.expect_response("**/api/auth/register") as registration_info:
        page.locator("#registerForm button[type='submit']").click()
    response = registration_info.value
    require(response.status == 201, f"registration returned {response.status}")
    set_cookie = response.header_value("set-cookie") or ""
    require("healthia_session=" in set_cookie, "registration did not emit session cookie")
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/?$"), timeout=15_000)
    cookies = context.cookies(base_url)
    session_cookie = next((cookie for cookie in cookies if cookie.get("name") == "healthia_session"), None)
    require(session_cookie is not None, "Chromium did not retain registration cookie")
    require(session_cookie.get("secure") is False, "local registration cookie is Secure-only")
    report["outputs"]["registration_http_status"] = response.status
    report["outputs"]["registration_set_cookie_present"] = True
    report["outputs"]["browser_session_cookie_after_register"] = {
        "present": True,
        "secure": bool(session_cookie.get("secure")),
        "sameSite": session_cookie.get("sameSite"),
        "path": session_cookie.get("path"),
    }
    report["functions"]["register_and_authenticate"] = "pass"
    context.close()
    checkpoint("browser_registration_pass")


def login_cookie(base_url: str) -> str:
    with httpx.Client(base_url=base_url, timeout=8.0) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "lab.omega@example.test", "password": "LabOmega-2026-safe"},
        )
        require(response.status_code == 200, f"direct session login returned {response.status_code}")
        value = client.cookies.get("healthia_session")
        require(bool(value), "direct session login did not return healthia_session")
        session = client.get("/api/auth/session")
        require(session.status_code == 200 and session.json().get("authenticated") is True, "direct session verification failed")
        return str(value)


def open_authenticated_app(browser: Browser, base_url: str, report: dict):
    checkpoint("clean_authenticated_context_start")
    token = login_cookie(base_url)
    context = browser.new_context(
        locale="en-US",
        viewport={"width": 1600, "height": 1000},
        record_video_dir=str(VIDEO_DIR),
        record_video_size={"width": 1280, "height": 800},
    )
    context.add_cookies([{"name": "healthia_session", "value": token, "url": base_url}])
    page = context.new_page()
    configure_page(page, report)
    page.goto(f"{base_url}/", wait_until="domcontentloaded")
    page.wait_for_timeout(900)
    composer = page.locator("#chatInput")
    composer.fill("LAB Omega readiness probe", timeout=8_000)
    require(composer.input_value() == "LAB Omega readiness probe", "authenticated composer rejected text")
    composer.fill("")
    require(page.locator("html").get_attribute("lang") == "en", "authenticated shell did not follow en-US")
    report["checks"]["authenticated_shell_interactive"] = "pass"
    report["outputs"]["post_register_session_authenticated"] = True
    screenshot(page, "home-authenticated-en")
    checkpoint("clean_authenticated_context_pass")
    return context, page


def bootstrap(page: Page) -> dict:
    response = page.request.get("/api/bootstrap")
    require(response.ok, f"bootstrap returned {response.status}")
    return response.json()


def exercise_registered_views(page: Page, report: dict) -> None:
    checkpoint("registered_views_start")
    for index, view in enumerate(MAIN_VIEWS, start=1):
        checkpoint(f"view_{view}_start")
        page.locator(f".main-nav [data-open='{view}']").click(timeout=8_000)
        target = page.locator(f"#view-{view}")
        target.wait_for(state="visible", timeout=8_000)
        report["windows"][view] = "pass"
        screenshot(page, f"view-{index:02d}-{view}")
        checkpoint(f"view_{view}_pass")
    checkpoint("registered_views_pass")


def fill_and_save(page: Page, dialog_type: str, values: dict[str, str], report: dict) -> None:
    checkpoint(f"save_{dialog_type}_start")
    page.locator(f"[data-dialog='{dialog_type}']").first.click(timeout=8_000)
    page.locator("#dataDialog").wait_for(state="visible", timeout=8_000)
    for name, value in values.items():
        page.locator(f"#dataForm [name='{name}']").fill(value, timeout=8_000)
    page.locator("#saveData").click(timeout=8_000)
    page.locator("#dataDialog").wait_for(state="hidden", timeout=8_000)
    report["functions"][f"save_{dialog_type}"] = "pass"
    checkpoint(f"save_{dialog_type}_pass")


def verify_measurements(page: Page, report: dict) -> None:
    checkpoint("measurements_start")
    page.locator(".main-nav [data-open='measurements']").click(timeout=8_000)
    fill_and_save(
        page,
        "vital",
        {"systolic": "126", "diastolic": "78", "pulse": "72", "oxygen_saturation": "98"},
        report,
    )
    fill_and_save(page, "weight", {"weight_kg": "74.2", "note": "LAB Omega synthetic"}, report)
    fill_and_save(
        page,
        "activity",
        {"steps": "6842", "active_minutes": "42", "note": "LAB Omega synthetic"},
        report,
    )
    state = bootstrap(page)
    require(state["vitals"][-1]["systolic"] == 126, "blood pressure did not persist")
    require(state["vitals"][-1]["diastolic"] == 78, "diastolic pressure did not persist")
    require(abs(float(state["weights"][-1]["weight_kg"]) - 74.2) < 0.001, "weight did not persist")
    require(state["activity"][-1]["steps"] == 6842, "activity did not persist")
    report["outputs"]["measurement_state_roundtrip"] = "pass"
    screenshot(page, "measurements-after-save")
    checkpoint("measurements_pass")


def verify_structured_result(page: Page, report: dict) -> None:
    checkpoint("structured_result_start")
    page.locator(".main-nav [data-open='results']").click(timeout=8_000)
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
        files=[{"name": "lab-omega-result.json", "mime_type": "application/json", "buffer": payload}],
        timeout=8_000,
    )
    card = page.locator("#resultList [data-result-id]").first
    card.wait_for(state="visible", timeout=8_000)
    card_text = card.inner_text()
    require("LAB Omega metabolic panel" in card_text, "structured result panel not rendered")
    require("educational explanation" in card_text.lower(), "English result explanation missing")
    require("View original file" in card_text, "original-evidence link missing")
    state = bootstrap(page)
    result = state["results"][-1]
    require(result["status"] == "parsed" and len(result["items"]) == 2, "structured result did not persist")
    require(state["documents"][-1]["related_result_id"] == result["id"], "original document not linked to result")
    report["functions"]["structured_result_upload"] = "pass"
    report["outputs"]["english_result_explanation"] = "pass"
    report["outputs"]["result_original_provenance"] = "pass"
    screenshot(page, "results-structured-upload")
    checkpoint("structured_result_pass")


def verify_input_language_headers(page: Page, report: dict) -> None:
    checkpoint("input_language_headers_start")
    observed: list[str] = []

    def capture(request) -> None:
        if request.url.endswith("/api/chat") and request.method == "POST":
            observed.append(request.headers.get("accept-language", ""))

    page.on("request", capture)
    page.locator(".main-nav [data-open='chat']").click(timeout=8_000)
    page.locator("#chatInput").fill("Please show my latest results and help me understand them", timeout=8_000)
    page.locator("#sendButton").click(timeout=8_000)
    page.wait_for_timeout(700)
    page.locator("#chatInput").fill("Quiero ver mis resultados y entender qué significan", timeout=8_000)
    page.locator("#sendButton").click(timeout=8_000)
    page.wait_for_timeout(700)
    require(any(value.startswith("en") for value in observed), f"English input did not send English locale: {observed}")
    require(any(value.startswith("es") for value in observed), f"Spanish input did not override OS locale: {observed}")
    report["outputs"]["input_language_to_backend_en"] = "pass"
    report["outputs"]["input_language_to_backend_es"] = "pass"
    checkpoint("input_language_headers_pass")


def verify_account_views_and_logout(page: Page, report: dict) -> None:
    checkpoint("account_views_start")
    page.locator("#accountPill").click(timeout=8_000)
    dialog = page.locator("#accountDialog")
    dialog.wait_for(state="visible", timeout=8_000)
    account_text = dialog.inner_text()
    require("Account & settings" in account_text, "account dialog did not follow English locale")
    require("lab.omega" in account_text.lower(), "authenticated account identity missing")
    report["windows"]["account_dialog"] = "pass"
    screenshot(page, "account-dialog")

    for target in ACCOUNT_VIEWS:
        checkpoint(f"account_view_{target}_start")
        if not dialog.is_visible():
            page.locator("#accountPill").click(timeout=8_000)
            dialog.wait_for(state="visible", timeout=8_000)
        page.locator(f"[data-account-view='{target}']").click(timeout=8_000)
        page.locator(f"#view-{target}").wait_for(state="visible", timeout=8_000)
        report["windows"][f"account_{target}"] = "pass"
        screenshot(page, f"account-view-{target}")
        checkpoint(f"account_view_{target}_pass")

    if not dialog.is_visible():
        page.locator("#accountPill").click(timeout=8_000)
        dialog.wait_for(state="visible", timeout=8_000)
    page.locator("#logoutButton").click(timeout=8_000)
    page.wait_for_url(re.compile(r".*/login$"), timeout=15_000)
    page.locator("#loginForm").wait_for(state="visible", timeout=8_000)
    report["functions"]["logout"] = "pass"
    checkpoint("account_views_logout_pass")


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
            checkpoint("server_wait_start")
            wait_server(base_url)
            checkpoint("server_ready")
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
                register_through_real_browser(browser, base_url, report)

                context, page = open_authenticated_app(browser, base_url, report)
                exercise_registered_views(page, report)

                checkpoint("panel_collapse_start")
                page.locator("#collapseLeft").click(timeout=8_000)
                page.locator("#expandLeft").wait_for(state="visible", timeout=8_000)
                page.locator("#expandLeft").click(timeout=8_000)
                page.locator("#collapseLeft").wait_for(state="visible", timeout=8_000)
                report["functions"]["left_navigation_collapse_expand"] = "pass"
                page.locator("#collapseRight").click(timeout=8_000)
                page.locator("#collapseRight").click(timeout=8_000)
                report["functions"]["context_collapse_expand"] = "pass"
                checkpoint("panel_collapse_pass")

                verify_measurements(page, report)
                verify_structured_result(page, report)
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
            (OUTPUT / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    return report


if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False, indent=2))
    except Exception:
        path = OUTPUT / "report.json"
        if path.exists():
            print(path.read_text(encoding="utf-8"))
        raise