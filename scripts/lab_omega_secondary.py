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

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "lab-omega-secondary"
VIDEO_DIR = OUTPUT / "video"
STYLES = ("styles.css", "interactions.css", "clinical-council.css", "cost-control.css")
SCRIPTS = (
    "i18n.js", "app.js", "clinical-council.js", "patient-record.js",
    "family-documents.js", "continuity.js", "privacy-controls.js",
    "profile-devices.js", "account.js", "runtime-integrations.js",
    "provider-integrations.js", "cost-control.js", "icons.js",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_server(base_url: str, timeout: float = 20) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url}/healthz", timeout=1.5) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("LAB Ω Secondary server did not become ready")


def state(page: Page) -> dict:
    return page.evaluate("async () => await (await fetch('/api/bootstrap')).json()")


def screenshot(page: Page, name: str) -> None:
    page.screenshot(path=str(OUTPUT / f"{name}.png"), full_page=True)


def hydrate_shell(page: Page, base_url: str, root_html: str) -> None:
    shell_html = re.sub(r'<link[^>]+href="/assets/[^"]+"[^>]*>', "", root_html)
    shell_html = re.sub(r'<script[^>]+src="/assets/[^"]+"[^>]*></script>', "", shell_html)
    page.set_content(shell_html, wait_until="domcontentloaded", timeout=20_000)
    require(page.locator("#app").count() == 1, "secondary shell DOM missing before asset hydration")
    for stylesheet in STYLES:
        page.add_style_tag(url=f"{base_url}/assets/{stylesheet}")
    for script in SCRIPTS:
        page.add_script_tag(url=f"{base_url}/assets/{script}")
    page.locator("#chatInput").wait_for(state="visible", timeout=15_000)


def wait_view_registry(page: Page) -> None:
    expected = ["family", "documents", "timeline", "treatment", "appointments", "control", "profile", "devices"]
    page.wait_for_function(
        "expected => expected.every(view => document.querySelector(`[data-open='${view}']`) && document.querySelector(`#view-${view}`))",
        arg=expected,
        timeout=15_000,
    )


def open_view(page: Page, view: str, heading: str, report: dict) -> None:
    page.locator(f".main-nav [data-open='{view}']").click()
    page.wait_for_timeout(150)
    section = page.locator(f"#view-{view}")
    require(section.is_visible(), f"secondary view {view} did not become visible")
    body = section.inner_text()
    require(heading.lower() in body.lower(), f"{view} did not render expected English heading {heading!r}: {body[:280]!r}")
    report["windows"][view] = "pass"
    screenshot(page, f"secondary-{view}")


def test_family(page: Page, report: dict) -> None:
    open_view(page, "family", "Pathological genogram", report)
    page.locator("#addFamilyButton").click()
    page.locator("#familyForm [name='display_name']").fill("LAB Omega Mother")
    page.locator("#familyForm [name='relation']").fill("mother")
    page.locator("#familyForm [name='generation']").select_option("-1")
    page.locator("#familyForm [name='lineage']").select_option("maternal")
    page.locator("#familyForm [name='sex_at_birth']").select_option("female")
    page.locator("#familyForm [name='condition']").fill("Hypertension")
    page.locator("#familyForm button[type='submit']").click()
    page.wait_for_function("!document.querySelector('#familyDialog').open")
    current = state(page)
    require(any(item.get("display_name") == "LAB Omega Mother" for item in current.get("family_members", [])), "family member did not persist")
    report["functions"]["family_create"] = "pass"


def test_documents(page: Page, report: dict) -> None:
    open_view(page, "documents", "Patient documents", report)
    page.locator("#addDocumentButton").click()
    page.locator("#documentForm [name='file']").set_input_files(
        files=[{"name": "lab-secondary-note.txt", "mime_type": "text/plain", "buffer": b"Synthetic LAB Omega secondary note"}]
    )
    page.locator("#documentForm [name='title']").fill("LAB Omega secondary document")
    page.locator("#documentForm [name='category']").select_option("consultation")
    page.locator("#documentForm button[type='submit']").click()
    page.wait_for_function("!document.querySelector('#documentDialog').open")
    current = state(page)
    require(any(item.get("title") == "LAB Omega secondary document" for item in current.get("documents", [])), "document did not persist")
    report["functions"]["document_upload"] = "pass"


def test_appointment(page: Page, report: dict) -> None:
    open_view(page, "appointments", "Appointments & visit", report)
    page.locator("#addAppointmentButton").click()
    page.locator("#appointmentForm [name='title']").fill("LAB Omega follow-up")
    page.locator("#appointmentForm [name='specialty']").fill("Family medicine")
    page.locator("#appointmentForm [name='scheduled_at']").fill("2026-08-20T10:30")
    page.locator("#appointmentForm [name='location']").fill("Synthetic clinic")
    page.locator("#appointmentForm [name='required_documents']").fill("LAB report, medication list")
    page.locator("#appointmentForm [name='questions']").fill("What changed?, What should I monitor?")
    page.locator("#appointmentForm button[type='submit']").click()
    page.wait_for_function("!document.querySelector('#appointmentDialog').open")
    current = state(page)
    require(any(item.get("title") == "LAB Omega follow-up" for item in current.get("appointments", [])), "appointment did not persist")
    report["functions"]["appointment_create"] = "pass"


def test_privacy(page: Page, report: dict) -> None:
    open_view(page, "control", "Permissions & privacy", report)
    current = state(page)
    before = bool(current["consent"]["proactive_enabled"])
    toggle = page.locator("#proactiveEnabled")
    if toggle.is_checked() == before:
        toggle.click()
    page.locator("#saveConsent").click()
    page.wait_for_timeout(350)
    after = bool(state(page)["consent"]["proactive_enabled"])
    require(after != before, "privacy proactive toggle did not persist")
    report["functions"]["privacy_consent_update"] = "pass"


def test_profile(page: Page, report: dict) -> None:
    open_view(page, "profile", "Complete profile", report)
    page.locator("#editProfileButton").click()
    page.locator("#profileForm [name='phone']").fill("+1 555 010 2026")
    page.locator("#profileForm [name='occupation']").fill("LAB Omega synthetic")
    page.locator("#profileForm button[type='submit']").click()
    page.wait_for_function("!document.querySelector('#profileDialog').open")
    profile = state(page)["profile_summary"]["profile"]
    require(profile.get("phone") == "+1 555 010 2026", "profile phone did not persist")
    require(profile.get("occupation") == "LAB Omega synthetic", "profile occupation did not persist")
    report["functions"]["profile_update"] = "pass"


def test_medication(page: Page, report: dict) -> None:
    page.locator(".main-nav [data-open='profile']").click()
    page.locator("#normalizeMedicationButton").click()
    page.locator("#medicationNormalizeForm [name='text']").fill("Losartan 50 mg by mouth every 24 hours")
    page.locator("#medicationNormalizeForm button[type='submit']").click()
    page.wait_for_selector("#confirmMedication")
    page.locator("#confirmMedication").click()
    page.wait_for_function("!document.querySelector('#medicationNormalizeDialog').open")
    current = state(page)
    require(any("losartan" in str(item.get("name", "")).lower() for item in current.get("medication_plans", [])), "normalized medication plan did not persist")
    report["functions"]["medication_normalize_confirm"] = "pass"


def test_devices(page: Page, report: dict) -> None:
    open_view(page, "devices", "Devices & Health Connect", report)
    before = int(state(page).get("device_summary", {}).get("record_count", 0))
    page.locator("#demoDeviceSync").click()
    deadline = time.time() + 5
    after = before
    while time.time() < deadline:
        after = int(state(page).get("device_summary", {}).get("record_count", 0))
        if after > before:
            break
        page.wait_for_timeout(200)
    require(after > before, "synthetic device sync did not add records")
    report["functions"]["device_synthetic_sync"] = "pass"


def test_timeline_treatment_and_cost(page: Page, report: dict) -> None:
    open_view(page, "timeline", "Health timeline", report)
    require(page.locator("#timelineRoot").is_visible(), "timeline root missing")
    report["functions"]["timeline_render"] = "pass"
    open_view(page, "treatment", "Treatment & check-ins", report)
    require(page.locator("#treatmentRoot").is_visible(), "treatment root missing")
    report["functions"]["treatment_render"] = "pass"
    button = page.locator("#costGuardButton")
    require(button.count() == 1 and button.is_visible(), "cost guard control missing")
    button.click()
    dialog = page.locator("#costGuardDialog")
    require(dialog.is_visible(), "cost guard dialog did not open")
    require("Google AI under a hard guard" in dialog.inner_text(), "cost guard dialog did not localize to English")
    dialog.locator(".cost-close").click()
    report["windows"]["cost_guard"] = "pass"


def run() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    report = {"status":"RUNNING","lab":"LAB OMEGA SECONDARY","locale":"en-US","windows":{},"functions":{},"console_errors":[],"page_errors":[],"outputs":{}}
    with tempfile.TemporaryDirectory(prefix="healthia-lab-secondary-") as temp_dir:
        port = free_port(); base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy(); env.update({"HEALTHIA_ENV":"local","HEALTHIA_AUTH_REQUIRED":"true","HEALTHIA_ALLOW_REGISTRATION":"true","HEALTHIA_STORE_BACKEND":"memory","HEALTHIA_LLM_BACKEND":"mock","HEALTHIA_COST_MODE":"local","HEALTHIA_AI_REQUEST_LIMIT":"0","HEALTHIA_PROACTIVE_ENABLED":"false","HEALTHIA_ACCOUNTS_PATH":str(Path(temp_dir)/"accounts.json"),"HEALTHIA_DATA_PATH":str(Path(temp_dir)/"state.json"),"PYTHONPATH":str(ROOT)})
        server = subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port",str(port),"--log-level","warning"],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        try:
            wait_server(base_url)
            with sync_playwright() as playwright:
                launch={"headless":True,"args":["--no-sandbox"]}
                explicit=os.getenv("HEALTHIA_CHROMIUM_EXECUTABLE")
                if explicit: launch["executable_path"]=explicit
                elif Path("/usr/bin/chromium").exists(): launch["executable_path"]="/usr/bin/chromium"
                browser=playwright.chromium.launch(**launch)
                context=browser.new_context(base_url=base_url,locale="en-US",viewport={"width":1600,"height":1000},record_video_dir=str(VIDEO_DIR),record_video_size={"width":1280,"height":800})
                registration=context.request.post("/api/auth/register",data={"display_name":"LAB Omega Secondary","email":"lab.secondary@example.test","password":"LabOmega-Secondary-2026"},headers={"Accept-Language":"en-US"})
                require(registration.status==201,f"secondary auth setup returned {registration.status}")
                session=context.request.get("/api/auth/session",headers={"Accept-Language":"en-US"})
                require(session.status==200 and session.json().get("authenticated") is True,"secondary browser context is not authenticated")
                report["functions"]["authenticated_setup"]="pass"
                root_probe=context.request.get("/",headers={"Accept-Language":"en-US"})
                require(root_probe.status==200,f"secondary authenticated root returned {root_probe.status}")
                root_html=root_probe.text()
                require('id="app"' in root_html and 'id="chatInput"' in root_html,"secondary authenticated root did not contain HealthIA shell")
                page=context.new_page()
                page.on("console",lambda message: report["console_errors"].append(message.text) if message.type=="error" else None)
                page.on("pageerror",lambda error: report["page_errors"].append(str(error)))
                origin_probe=page.goto("/healthz",wait_until="domcontentloaded",timeout=20_000)
                require(origin_probe is not None and origin_probe.status==200,"secondary same-origin harness did not load")
                hydrate_shell(page,base_url,root_html)
                report["outputs"]["functional_dom_source"]="authenticated_root_dom_plus_ordered_real_assets"
                wait_view_registry(page)
                test_family(page,report); test_documents(page,report); test_appointment(page,report); test_privacy(page,report); test_profile(page,report); test_medication(page,report); test_devices(page,report); test_timeline_treatment_and_cost(page,report)
                require(not report["console_errors"],f"console errors: {report['console_errors']}"); require(not report["page_errors"],f"page errors: {report['page_errors']}")
                report["status"]="PASS"; screenshot(page,"secondary-final"); context.close(); browser.close()
        except Exception as exc:
            report["status"]="FAIL"; report["error"]=f"{type(exc).__name__}: {exc}"; raise
        finally:
            server.terminate()
            try: server.wait(timeout=8)
            except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=3)
            if report["status"]!="PASS" and server.stdout: report["server_tail"]=server.stdout.read()[-5000:]
            (OUTPUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


if __name__ == "__main__":
    try: print(json.dumps(run(),ensure_ascii=False,indent=2))
    except Exception:
        path=OUTPUT/"report.json"
        if path.exists(): print(path.read_text(encoding="utf-8"))
        raise