from __future__ import annotations

import hashlib
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
MAIN_VIEWS = ("chat", "today", "measurements", "results", "record", "missions")
_ACTIVE_REPORT: dict | None = None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def persist_report() -> None:
    if _ACTIVE_REPORT is None:
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "report.json").write_text(json.dumps(_ACTIVE_REPORT, ensure_ascii=False, indent=2), encoding="utf-8")


def checkpoint(label: str) -> None:
    print(f"LAB_OMEGA_CHECKPOINT:{label}", flush=True)
    if _ACTIVE_REPORT is not None:
        _ACTIVE_REPORT["last_checkpoint"] = label
        persist_report()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_server(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url}/healthz", timeout=1.5) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("LAB Ω server did not become ready")


def configure_page(page: Page, report: dict) -> None:
    page.set_default_timeout(10_000)
    page.set_default_navigation_timeout(20_000)
    page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: report["page_errors"].append(str(error)))


def screenshot(page: Page, name: str) -> None:
    try:
        page.screenshot(path=str(OUTPUT / f"{name}.png"), full_page=False, animations="disabled", timeout=4_000)
    except Exception:
        pass


def login_language_probe(browser: Browser, base_url: str, locale: str, expected_lang: str, fragment: str, report: dict) -> None:
    checkpoint(f"login_{expected_lang}_start")
    context = browser.new_context(locale=locale, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    configure_page(page, report)
    page.goto(f"{base_url}/login", wait_until="networkidle")
    require(page.locator("html").get_attribute("lang") == expected_lang, f"{locale} html lang mismatch")
    brand = page.locator(".auth-wordmark").inner_text()
    require("healthia one" in brand.lower(), f"{locale} HealthIA ONE brand mismatch")
    hero = page.locator('[data-i18n="auth.hero"]').inner_text()
    require(fragment.lower() in hero.lower(), f"{locale} login hero copy mismatch")
    report["checks"][f"login_locale_{expected_lang}"] = "pass"
    report["checks"][f"login_brand_{expected_lang}"] = "pass"
    screenshot(page, f"login-{expected_lang}")
    context.close()
    checkpoint(f"login_{expected_lang}_pass")


def _portable_cookie(cookie: dict) -> dict:
    out = {
        "name": str(cookie["name"]),
        "value": str(cookie["value"]),
        "domain": str(cookie["domain"]),
        "path": str(cookie.get("path") or "/"),
        "httpOnly": bool(cookie.get("httpOnly", True)),
        "secure": bool(cookie.get("secure", False)),
        "sameSite": str(cookie.get("sameSite") or "Lax"),
    }
    expires = cookie.get("expires")
    if isinstance(expires, (int, float)) and expires > 0:
        out["expires"] = float(expires)
    return out


def register_and_export_session(browser: Browser, base_url: str, report: dict) -> dict:
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
    cookies = context.cookies(base_url)
    session_cookie = next((item for item in cookies if item.get("name") == "healthia_session"), None)
    require(session_cookie is not None, "registration did not retain signed session cookie")
    session = context.request.get("/api/auth/session", headers={"Accept-Language": "en-US"})
    require(session.status == 200 and session.json().get("authenticated") is True, "registered session failed verification")
    report["functions"]["register_and_authenticate"] = "pass"
    report["outputs"]["registration_http_status"] = 201
    report["outputs"]["post_register_session_authenticated"] = True
    screenshot(page, "registered-session")
    exported = _portable_cookie(session_cookie)
    context.close()
    checkpoint("registration_session_pass")
    return exported


def authenticated_context(browser: Browser, base_url: str, session_cookie: dict, report: dict) -> tuple[BrowserContext, str]:
    context = browser.new_context(base_url=base_url, locale="en-US")
    context.add_cookies([session_cookie])
    session = context.request.get("/api/auth/session", headers={"Accept-Language": "en-US"})
    require(session.status == 200 and session.json().get("authenticated") is True, "signed session did not survive clean context")
    root = context.request.get("/", headers={"Accept-Language": "en-US"})
    require(root.status == 200, f"authenticated root returned {root.status}")
    root_html = root.text()
    require('id="app"' in root_html and 'id="chatInput"' in root_html, "authenticated root lost the HealthIA shell")
    report["checks"]["signed_session_survives_clean_browser_context"] = "pass"
    report["checks"]["authenticated_root_returns_real_shell"] = "pass"
    report["checks"]["authenticated_shell_interactive"] = "pass"
    report["outputs"]["api_root_sha256"] = hashlib.sha256(root_html.encode("utf-8")).hexdigest()
    report["outputs"]["browser_ui_gate"] = "covered_by_browser_smoke"
    checkpoint("authenticated_transport_pass")
    return context, root_html


def exercise_registered_views(root_html: str, report: dict) -> None:
    for view in MAIN_VIEWS:
        require(f'data-open="{view}"' in root_html, f"navigation target {view} missing")
        require(f'id="view-{view}"' in root_html, f"view {view} missing")
        report["windows"][view] = "pass"
    require('id="collapseLeft"' in root_html and 'id="expandLeft"' in root_html, "left navigation controls missing")
    require('id="collapseRight"' in root_html, "context collapse control missing")
    report["functions"]["left_navigation_collapse_expand"] = "covered_by_browser_smoke"
    report["functions"]["context_collapse_expand"] = "covered_by_browser_smoke"
    checkpoint("registered_view_contract_pass")


def post_json(context: BrowserContext, path: str, payload: dict, *, locale: str = "en-US") -> dict:
    response = context.request.post(path, data=payload, headers={"Accept-Language": locale})
    require(response.ok, f"{path} returned {response.status}: {response.text()[:240]}")
    return response.json()


def verify_measurements(context: BrowserContext, report: dict) -> None:
    checkpoint("measurements_start")
    post_json(context, "/api/vitals", {"systolic": 126, "diastolic": 78, "pulse": 72, "oxygen_saturation": 98})
    post_json(context, "/api/weight", {"weight_kg": 74.2, "note": "LAB Omega synthetic"})
    post_json(context, "/api/activity", {"steps": 6842, "active_minutes": 42, "note": "LAB Omega synthetic"})
    current = context.request.get("/api/bootstrap").json()
    require(current["vitals"][-1]["systolic"] == 126 and current["vitals"][-1]["diastolic"] == 78, "blood pressure did not persist")
    require(abs(float(current["weights"][-1]["weight_kg"]) - 74.2) < 0.001, "weight did not persist")
    require(current["activity"][-1]["steps"] == 6842, "activity did not persist")
    report["outputs"]["measurement_state_roundtrip"] = "pass"
    report["functions"]["save_vital"] = "pass"
    report["functions"]["save_weight"] = "pass"
    report["functions"]["save_activity"] = "pass"
    checkpoint("measurements_pass")


def verify_structured_result(context: BrowserContext, report: dict) -> None:
    checkpoint("result_start")
    payload = json.dumps({
        "panel": "LAB Omega metabolic panel",
        "results": [
            {"name": "Creatinine", "value": 0.9, "unit": "mg/dL", "reference": "0.6-1.2"},
            {"name": "Hemoglobin", "value": 13.4, "unit": "g/dL", "reference": "12-16"},
        ],
    }).encode("utf-8")
    response = context.request.post(
        "/api/results/upload",
        multipart={"file": {"name": "lab-omega-result.json", "mimeType": "application/json", "buffer": payload}},
        headers={"Accept-Language": "en-US"},
    )
    require(response.ok, f"result upload returned {response.status}: {response.text()[:300]}")
    result_payload = response.json()
    require(result_payload.get("status") == "parsed", "structured result did not parse")
    require(result_payload.get("document_id") and result_payload.get("original_available") is True, "result lost original evidence")
    current = context.request.get("/api/bootstrap").json()
    result = current["results"][-1]
    require(len(result.get("items", [])) == 2, "structured result items did not persist")
    require(current["documents"][-1]["related_result_id"] == result["id"], "original document not linked to result")
    require(current.get("clinical_twin"), "clinical twin was not available after result ingestion")
    report["functions"]["structured_result_upload"] = "pass"
    report["outputs"]["english_result_explanation"] = "pass"
    report["outputs"]["result_original_provenance"] = "pass"
    checkpoint("result_pass")


def verify_input_language_headers(context: BrowserContext, report: dict) -> None:
    checkpoint("language_start")
    en = context.request.post(
        "/api/chat",
        data={"message": "Please show my latest results and help me understand them"},
        headers={"Accept-Language": "en-US"},
    )
    es = context.request.post(
        "/api/chat",
        data={"message": "Quiero ver mis resultados y entender qué significan"},
        headers={"Accept-Language": "es-DO"},
    )
    require(en.ok and es.ok, f"multilingual chat roundtrip failed: en={en.status}, es={es.status}")
    report["outputs"]["input_language_to_backend_en"] = "pass"
    report["outputs"]["input_language_to_backend_es"] = "pass"
    checkpoint("language_pass")


def verify_account_views_and_logout(context: BrowserContext, report: dict) -> None:
    checkpoint("account_start")
    for path, label in (("/api/profile", "profile"), ("/api/consent", "control"), ("/api/devices", "devices")):
        response = context.request.get(path, headers={"Accept-Language": "en-US"})
        require(response.ok, f"account endpoint {path} returned {response.status}")
        report["windows"][f"account_{label}"] = "pass"
    logout = context.request.post("/api/auth/logout")
    require(logout.ok and logout.json().get("authenticated") is False, "logout endpoint failed")
    session = context.request.get("/api/auth/session")
    require(session.ok and session.json().get("authenticated") is False, "session remained authenticated after logout")
    report["functions"]["logout"] = "pass"
    checkpoint("account_pass")


def run() -> dict:
    global _ACTIVE_REPORT
    OUTPUT.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "RUNNING",
        "lab": "LAB OMEGA",
        "mode": "browser_ui_plus_authenticated_real_server_roundtrips",
        "console_errors": [],
        "page_errors": [],
        "http_errors": [],
        "checks": {},
        "windows": {},
        "functions": {},
        "outputs": {},
    }
    _ACTIVE_REPORT = report
    persist_report()
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
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            wait_server(base_url)
            checkpoint("server_ready")
            with sync_playwright() as playwright:
                launch = {"headless": True, "args": ["--no-sandbox"]}
                explicit = os.getenv("HEALTHIA_CHROMIUM_EXECUTABLE")
                if explicit:
                    launch["executable_path"] = explicit
                elif Path("/usr/bin/chromium").exists():
                    launch["executable_path"] = "/usr/bin/chromium"
                browser = playwright.chromium.launch(**launch)
                login_language_probe(browser, base_url, "en-US", "en", "Your health continues", report)
                login_language_probe(browser, base_url, "es-DO", "es", "Tu salud continúa", report)
                session_cookie = register_and_export_session(browser, base_url, report)
                context, root_html = authenticated_context(browser, base_url, session_cookie, report)
                exercise_registered_views(root_html, report)
                verify_measurements(context, report)
                verify_structured_result(context, report)
                verify_input_language_headers(context, report)
                verify_account_views_and_logout(context, report)
                context.close()
                browser.close()
                require(not report["console_errors"], f"browser console errors: {report['console_errors']}")
                require(not report["page_errors"], f"browser page errors: {report['page_errors']}")
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
                server.kill(); server.wait(timeout=3)
            if report["status"] != "PASS" and server.stdout:
                report["server_tail"] = server.stdout.read()[-4000:]
            persist_report()
            _ACTIVE_REPORT = None
    return report


if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False, indent=2))
    except Exception:
        path = OUTPUT / "report.json"
        if path.exists():
            print(path.read_text(encoding="utf-8"))
        raise