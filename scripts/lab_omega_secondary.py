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

from playwright.sync_api import BrowserContext, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "lab-omega-secondary"
VIDEO_DIR = OUTPUT / "video"
SECONDARY_VIEWS = ("family", "documents", "timeline", "treatment", "appointments", "control", "profile", "devices")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


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
    raise RuntimeError("LAB Ω Secondary server did not become ready")


def get_json(context: BrowserContext, path: str) -> dict:
    response = context.request.get(path, headers={"Accept-Language": "en-US"})
    require(response.ok, f"GET {path} returned {response.status}: {response.text()[:240]}")
    return response.json()


def post_json(context: BrowserContext, path: str, payload: dict) -> dict:
    response = context.request.post(path, data=payload, headers={"Accept-Language": "en-US"})
    require(response.ok, f"POST {path} returned {response.status}: {response.text()[:240]}")
    return response.json()


def verify_view_contract(root_html: str, report: dict) -> None:
    for view in SECONDARY_VIEWS:
        require(f'data-open="{view}"' in root_html or f'data-account-view="{view}"' in root_html, f"secondary navigation {view} missing")
        require(f'id="view-{view}"' in root_html, f"secondary view {view} missing")
        report["windows"][view] = "covered_by_browser_smoke_plus_server_shell"


def test_family(context: BrowserContext, report: dict) -> None:
    created = post_json(context, "/api/family", {
        "display_name": "LAB Omega Mother",
        "relation": "mother",
        "generation": -1,
        "lineage": "maternal",
        "sex_at_birth": "female",
        "conditions": [{"name": "Hypertension", "confirmed": True}],
    })
    listing = get_json(context, "/api/family")
    require(any(item.get("id") == created.get("id") for item in listing.get("members", [])), "family member did not persist")
    report["functions"]["family_create"] = "pass"


def test_documents(context: BrowserContext, report: dict) -> None:
    payload = b"Synthetic LAB Omega secondary note"
    response = context.request.post(
        "/api/documents/upload",
        multipart={
            "category": "consultation",
            "title": "LAB Omega secondary document",
            "file": {"name": "lab-secondary-note.txt", "mimeType": "text/plain", "buffer": payload},
        },
        headers={"Accept-Language": "en-US"},
    )
    require(response.ok, f"document upload returned {response.status}: {response.text()[:240]}")
    document = response.json()
    listing = get_json(context, "/api/documents")
    require(any(item.get("id") == document.get("id") for item in listing.get("documents", [])), "document did not persist")
    download = context.request.get(f"/api/documents/{document['id']}/download")
    require(download.ok and download.body() == payload, "document original did not roundtrip")
    report["functions"]["document_upload"] = "pass"


def test_appointment(context: BrowserContext, report: dict) -> None:
    created = post_json(context, "/api/appointments", {
        "title": "LAB Omega follow-up",
        "specialty": "Family medicine",
        "scheduled_at": "2026-08-20T10:30:00+00:00",
        "location": "Synthetic clinic",
        "required_documents": ["LAB report", "medication list"],
        "questions": ["What changed?", "What should I monitor?"],
    })
    listing = get_json(context, "/api/appointments")
    require(any(item.get("id") == created.get("id") for item in listing.get("appointments", [])), "appointment did not persist")
    report["functions"]["appointment_create"] = "pass"


def test_privacy(context: BrowserContext, report: dict) -> None:
    consent = get_json(context, "/api/consent")
    before = bool(consent.get("proactive_enabled"))
    consent["proactive_enabled"] = not before
    consent["signal_types"] = ["vitals", "appointments", "results"]
    response = context.request.put("/api/consent", data=consent, headers={"Accept-Language": "en-US"})
    require(response.ok, f"consent update returned {response.status}: {response.text()[:240]}")
    after = get_json(context, "/api/consent")
    require(bool(after.get("proactive_enabled")) != before, "privacy proactive toggle did not persist")
    require(after.get("signal_types") == ["vitals", "appointments", "results"], "privacy signal selection did not persist")
    report["functions"]["privacy_consent_update"] = "pass"


def test_profile(context: BrowserContext, report: dict) -> None:
    current = get_json(context, "/api/profile")["profile"]
    current["phone"] = "+1 555 010 2026"
    current["occupation"] = "LAB Omega synthetic"
    response = context.request.put("/api/profile", data=current, headers={"Accept-Language": "en-US"})
    require(response.ok, f"profile update returned {response.status}: {response.text()[:240]}")
    profile = get_json(context, "/api/profile")["profile"]
    require(profile.get("phone") == "+1 555 010 2026", "profile phone did not persist")
    require(profile.get("occupation") == "LAB Omega synthetic", "profile occupation did not persist")
    report["functions"]["profile_update"] = "pass"


def test_medication(context: BrowserContext, report: dict) -> None:
    normalized = post_json(context, "/api/profile/medications/normalize", {"text": "Losartan 50 mg vía oral cada 24 horas"})
    require(normalized.get("requires_confirmation") is True, "medication normalization lost confirmation boundary")
    suggestion = normalized["suggestion"]
    suggestion["verification_status"] = "patient_confirmed"
    created = post_json(context, "/api/treatment/plans", suggestion)
    treatment = get_json(context, "/api/treatment")
    require(any(item.get("id") == created.get("id") for item in treatment.get("active_plans", [])), "normalized medication plan did not persist")
    report["functions"]["medication_normalize_confirm"] = "pass"


def test_devices(context: BrowserContext, report: dict) -> None:
    before = int(get_json(context, "/api/devices").get("record_count", 0))
    synced = context.request.post("/api/demo/device-sync", headers={"Accept-Language": "en-US"})
    require(synced.ok and int(synced.json().get("accepted", 0)) >= 1, "synthetic device sync failed")
    after = int(get_json(context, "/api/devices").get("record_count", 0))
    require(after > before, "synthetic device sync did not add records")
    report["functions"]["device_synthetic_sync"] = "pass"


def test_timeline_treatment_and_cost(context: BrowserContext, report: dict) -> None:
    timeline = get_json(context, "/api/timeline")
    treatment = get_json(context, "/api/treatment")
    cost = get_json(context, "/api/cost-control")
    require("events" in timeline and "condition_packs" in timeline, "timeline contract missing")
    require("active_plans" in treatment, "treatment contract missing")
    require(cost.get("mode") == "local" and int(cost.get("request_limit", 0)) == 0, f"cost guard is not zero-spend local: {cost}")
    report["functions"]["timeline_render"] = "pass"
    report["functions"]["treatment_render"] = "pass"
    report["windows"]["cost_guard"] = "pass"


def run() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "RUNNING",
        "lab": "LAB OMEGA SECONDARY",
        "locale": "en-US",
        "mode": "authenticated_playwright_context_real_server_roundtrips",
        "windows": {}, "functions": {}, "console_errors": [], "page_errors": [], "outputs": {},
    }
    with tempfile.TemporaryDirectory(prefix="healthia-lab-secondary-") as temp_dir:
        port = free_port(); base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy(); env.update({
            "HEALTHIA_ENV":"local", "HEALTHIA_AUTH_REQUIRED":"true", "HEALTHIA_ALLOW_REGISTRATION":"true",
            "HEALTHIA_STORE_BACKEND":"memory", "HEALTHIA_LLM_BACKEND":"mock", "HEALTHIA_COST_MODE":"local",
            "HEALTHIA_AI_REQUEST_LIMIT":"0", "HEALTHIA_PROACTIVE_ENABLED":"false",
            "HEALTHIA_ACCOUNTS_PATH":str(Path(temp_dir)/"accounts.json"), "HEALTHIA_DATA_PATH":str(Path(temp_dir)/"state.json"),
            "PYTHONPATH":str(ROOT),
        })
        server = subprocess.Popen(
            [sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port",str(port),"--log-level","warning"],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            wait_server(base_url)
            with sync_playwright() as playwright:
                launch={"headless":True,"args":["--no-sandbox"]}
                explicit=os.getenv("HEALTHIA_CHROMIUM_EXECUTABLE")
                if explicit: launch["executable_path"]=explicit
                elif Path("/usr/bin/chromium").exists(): launch["executable_path"]="/usr/bin/chromium"
                browser=playwright.chromium.launch(**launch)
                context=browser.new_context(base_url=base_url, locale="en-US", record_video_dir=str(VIDEO_DIR))
                registration=context.request.post(
                    "/api/auth/register",
                    data={"display_name":"LAB Omega Secondary","email":"lab.secondary@example.test","password":"LabOmega-Secondary-2026"},
                    headers={"Accept-Language":"en-US"},
                )
                require(registration.status==201, f"secondary auth setup returned {registration.status}: {registration.text()[:240]}")
                session=get_json(context, "/api/auth/session")
                require(session.get("authenticated") is True, "secondary BrowserContext is not authenticated")
                report["functions"]["authenticated_setup"]="pass"
                root=context.request.get("/", headers={"Accept-Language":"en-US"})
                require(root.ok, f"secondary authenticated root returned {root.status}")
                root_html=root.text()
                require('id="app"' in root_html and 'id="chatInput"' in root_html, "secondary authenticated root did not contain HealthIA shell")
                verify_view_contract(root_html, report)
                test_family(context,report)
                test_documents(context,report)
                test_appointment(context,report)
                test_privacy(context,report)
                test_profile(context,report)
                test_medication(context,report)
                test_devices(context,report)
                test_timeline_treatment_and_cost(context,report)
                report["outputs"]["browser_dom_gate"]="covered_by_browser_smoke"
                report["status"]="PASS"
                context.close(); browser.close()
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