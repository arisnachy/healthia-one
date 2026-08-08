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
        except Exception as exc:  # pragma: no cover - diagnostics only
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
    page.set_default_timeout(8_000)
    page.set_default_navigation_timeout(15_000)
    attach_diagnostics(page, report)
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.wait_for_function(f"document.documentElement.lang === '{expected_lang}'")
    hero = page.locator(".auth-brand h1").inner_text().strip()
    require(expected_hero.lower() in hero.lower(), f"{locale} login did not localize: {hero!r}")
    report["checks"][f"login_locale_{expected_lang}"] = "pass"
    screenshot(page, f"login-{expected_lang}")
    context.close()
    checkpoint(f"login_probe_{expected_lang}_pass")


def wait_for_authenticated_shell(page: Page, report: dict) -> None:
    checkpoint("authenticated_shell_probe_start")
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass
    deadline = time.time() + 15.0
    last_probe: dict = {}
    while time.time() < deadline:
        app = page.locator("#app")
        composer = page.locator("#chatInput")
        last_probe = {
            "url": page.url,
            "app_count": app.count(),
            "chat_input_count": composer.count(),
        }
        if last_probe["app_count"] and last_probe["chat_input_count"]:
            try:
                geometry = composer.evaluate(
                    """node => {
                      const rect=node.getBoundingClientRect();
                      const style=getComputedStyle(node);
                      return {width:rect.width,height:rect.height,display:style.display,
                              visibility:style.visibility,opacity:style.opacity};
                    }"""
                )
                editable = composer.is_editable()
                last_probe["geometry"] = geometry
                last_probe["editable"] = editable
                report["outputs"]["chat_input_geometry"] = geometry
                report["outputs"]["chat_input_editable"] = editable
                if float(geometry["width"]) > 0 and float(geometry["height"]) > 0 and editable:
                    composer.fill("LAB Omega readiness probe", timeout=5_000)
                    if composer.input_value() == "LAB Omega readiness probe":
                        composer.fill("")
                        report["checks"]["authenticated_shell_interactive"] = "pass"
                        report["outputs"]["shell_readiness_probe"] = last_probe
                        checkpoint("authenticated_shell_probe_pass")
                        return
            except Exception as exc:
                last_probe["interaction_error"] = f"{type(exc).__name__}: {exc}"
        page.wait_for_timeout(200)
    report["outputs"]["shell_readiness_probe"] = last_probe
    raise RuntimeError(f"authenticated shell never became patient-interactive: {last_probe}")


def bootstrap(page: Page) -> dict:
    return page.evaluate(
        "async () => await (await fetch('/api/bootstrap', {credentials:'same-origin'})).json()"
    )


def assert_visible_view(page: Page, view: str) -> None:
    locator = page.locator(f"#view-{view}")
    require(locator.count() == 1, f"view {view!r} has no #view-{view}")
    require(locator.is_visible(), f"view {view!r} did not become visible")


def exercise_registered_views(page: Page, report: dict) -> None:
    checkpoint("registered_views_start")
    page.wait_for_timeout(350)
    views = page.evaluate(
        """() => [...new Set([...document.querySelectorAll('[data-open]')]
          .map(node => node.dataset.open)
          .filter(view => view && document.querySelector('#view-' + view)))]"""
    )
    require("chat" in views, "chat view missing from navigation registry")
    for index, view in enumerate(views, start=1):
        checkpoint(f"view_{view}_start")
        candidates = page.locator(f"[data-open='{view}']")
        target = None
        for offset in range(candidates.count()):
            candidate = candidates.nth(offset)
            if candidate.is_visible():
                target = candidate
                break
        require(target is not None, f"registered view {view!r} has no visible control")
        target.click(timeout=8_000)
        page.wait_for_timeout(100)
        assert_visible_view(page, view)
        report["windows"][view] = "pass"
        screenshot(page, f"view-{index:02d}-{view}")
        checkpoint(f"view_{view}_pass")
    checkpoint("registered_views_pass")


def fill_and_save(page: Page, dialog_type: str, values: dict[str, str], report: dict) -> None:
    checkpoint(f"save_{dialog_type}_start")
    trigger = page.locator(f"[data-dialog='{dialog_type}']:visible").first
    if trigger.count() == 0:
        trigger = page.locator(f"[data-dialog='{dialog_type}']").first
    trigger.click(timeout=8_000)
    dialog = page.locator("#dataDialog")
    require(dialog.is_visible(), f"{dialog_type} dialog did not open")
    for name, value in values.items():
        field = page.locator(f"#dataForm [name='{name}']")
        require(field.count() == 1, f"{dialog_type} missing field {name}")
        field.fill(value, timeout=8_000)
    page.locator("#saveData").click(timeout=8_000)
    page.wait_for_function("!document.querySelector('#dataDialog').open", timeout=8_000)
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
    page.wait_for_function("document.querySelectorAll('#resultList [data-result-id]').length > 0", timeout=8_000)
    card_text = page.locator("#resultList [data-result-id]").first.inner_text()
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
    page.wait_for_timeout(650)
    page.locator("#chatInput").fill("Quiero ver mis resultados y entender qué significan", timeout=8_000)
    page.locator("#sendButton").click(timeout=8_000)
    page.wait_for_timeout(650)
    require(any(value.startswith("en") for value in observed), f"English input did not send English locale: {observed}")
    require(any(value.startswith("es") for value in observed), f"Spanish input did not override OS locale: {observed}")
    report["outputs"]["input_language_to_backend_en"] = "pass"
    report["outputs"]["input_language_to_backend_es"] = "pass"
    checkpoint("input_language_headers_pass")


def verify_account_views_and_logout(page: Page, report: dict) -> None:
    checkpoint("account_views_start")
    page.locator("#accountPill").click(timeout=8_000)
    dialog = page.locator("#accountDialog")
    require(dialog.is_visible(), "account dialog did not open")
    account_text = dialog.inner_text()
    require("Account & settings" in account_text, "account dialog did not follow English locale")
    require("lab.omega" in account_text.lower(), "authenticated account identity missing")
    report["windows"]["account_dialog"] = "pass"
    screenshot(page, "account-dialog")

    targets = page.eval_on_selector_all(
        "[data-account-view]", "nodes => [...new Set(nodes.map(node => node.dataset.accountView))]"
    )
    for target in targets:
        checkpoint(f"account_view_{target}_start")
        if not dialog.is_visible():
            page.locator("#accountPill").click(timeout=8_000)
        control = page.locator(f"[data-account-view='{target}']")
        require(control.count() > 0, f"account view {target} missing control")
        control.first.click(timeout=8_000)
        page.wait_for_timeout(120)
        assert_visible_view(page, target)
        report["windows"][f"account_{target}"] = "pass"
        screenshot(page, f"account-view-{target}")
        checkpoint(f"account_view_{target}_pass")

    if not dialog.is_visible():
        page.locator("#accountPill").click(timeout=8_000)
    page.locator("#logoutButton").click(timeout=8_000)
    page.wait_for_url(re.compile(r".*/login$"), timeout=15_000)
    require(page.locator("#loginForm").is_visible(), "logout did not return to login")
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

                checkpoint("registration_start")
                context: BrowserContext = browser.new_context(
                    locale="en-US",
                    viewport={"width": 1600, "height": 1000},
                    record_video_dir=str(VIDEO_DIR),
                    record_video_size={"width": 1280, "height": 800},
                )
                page = context.new_page()
                page.set_default_timeout(8_000)
                page.set_default_navigation_timeout(15_000)
                attach_diagnostics(page, report)
                page.goto(f"{base_url}/login", wait_until="networkidle")
                page.locator("#registerTab").click()
                page.locator("#registerForm [name='display_name']").fill("LAB Omega Patient")
                page.locator("#registerForm [name='email']").fill("lab.omega@example.test")
                page.locator("#registerForm [name='password']").fill("LabOmega-2026-safe")
                with page.expect_response("**/api/auth/register") as registration_info:
                    page.locator("#registerForm button[type='submit']").click()
                registration_response = registration_info.value
                set_cookie = registration_response.header_value("set-cookie") or ""
                report["outputs"]["registration_http_status"] = registration_response.status
                report["outputs"]["registration_set_cookie_present"] = "healthia_session=" in set_cookie
                require(registration_response.status == 201, f"registration status was {registration_response.status}")
                require("healthia_session=" in set_cookie, "registration did not emit session cookie")
                page.wait_for_timeout(150)
                cookies = context.cookies(base_url)
                session_cookie = next((item for item in cookies if item.get("name") == "healthia_session"), None)
                report["outputs"]["browser_session_cookie_after_register"] = (
                    {"present": True, "secure": bool(session_cookie.get("secure")), "sameSite": session_cookie.get("sameSite"), "path": session_cookie.get("path")}
                    if session_cookie
                    else {"present": False}
                )
                require(session_cookie is not None, "Chromium did not retain registration session cookie")
                require(session_cookie.get("secure") is False, "local HTTP session cookie is Secure-only")

                page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/?$"), timeout=15_000)
                report["outputs"]["post_register_url"] = page.url
                wait_for_authenticated_shell(page, report)
                page.wait_for_function("document.documentElement.lang === 'en'", timeout=8_000)
                session = page.evaluate(
                    "async () => await (await fetch('/api/auth/session', {credentials:'same-origin', cache:'no-store'})).json()"
                )
                report["outputs"]["post_register_session_authenticated"] = bool(session.get("authenticated"))
                report["outputs"]["post_register_session_patient_id"] = str((session.get("account") or {}).get("patient_id") or "")
                require(session.get("authenticated") is True, "browser session verification failed after registration")
                report["functions"]["register_and_authenticate"] = "pass"
                screenshot(page, "home-authenticated-en")
                checkpoint("registration_and_shell_pass")

                exercise_registered_views(page, report)

                checkpoint("panel_collapse_start")
                page.locator("#collapseLeft").click(timeout=8_000)
                require(page.locator("#app").evaluate("node => node.classList.contains('left-collapsed')"), "left rail did not collapse")
                page.locator("#expandLeft").click(timeout=8_000)
                require(not page.locator("#app").evaluate("node => node.classList.contains('left-collapsed')"), "left rail did not reopen")
                report["functions"]["left_navigation_collapse_expand"] = "pass"

                page.locator("#collapseRight").click(timeout=8_000)
                require(page.locator("#app").evaluate("node => node.classList.contains('right-collapsed')"), "context panel did not collapse")
                page.locator("#collapseRight").click(timeout=8_000)
                require(not page.locator("#app").evaluate("node => node.classList.contains('right-collapsed')"), "context panel did not reopen")
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
            except subprocess.TimeoutExpired:  # pragma: no cover
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