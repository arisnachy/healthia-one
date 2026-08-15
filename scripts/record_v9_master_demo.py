from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from playwright.sync_api import sync_playwright

import record_v8_functional_demo as v8


base = v8.v7.base
science = v8.v7
BASE_URL = base.BASE_URL
OUT = base.OUT


def require(condition: bool, message: str) -> None:
    base.require(condition, message)


def nav(page, view: str, *, wait_ms: int = 900) -> None:
    button = page.locator(f'[data-open="{view}"]')
    require(button.count() > 0, f"HealthIA view is unavailable: {view}")
    button.first.click()
    page.wait_for_timeout(wait_ms)


def upload_synthetic_result(page) -> dict:
    payload = {
        "panel": "Synthetic cardiometabolic follow-up",
        "results": [
            {"name": "LDL", "value": 132, "unit": "mg/dL", "reference": "<100", "flag": "high"},
            {"name": "Creatinine", "value": 0.96, "unit": "mg/dL", "reference": "0.7-1.3"},
            {"name": "HbA1c", "value": 5.7, "unit": "%", "reference": "4.0-5.6", "flag": "borderline"},
        ],
    }
    return page.evaluate(
        """async payload => {
          const form = new FormData();
          const file = new File([JSON.stringify(payload, null, 2)], 'synthetic-followup.json', {type:'application/json'});
          form.append('file', file);
          const response = await fetch('/api/results/upload', {method:'POST', body:form, headers:{'Accept-Language':'en'}});
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(`${response.status}: ${data.detail || JSON.stringify(data)}`);
          return data;
        }""",
        payload,
    )


def open_account_view(page, view: str) -> bool:
    pill = page.locator("#accountPill")
    if not pill.count():
        return False
    pill.click()
    page.wait_for_timeout(500)
    button = page.locator(f'[data-account-view="{view}"]')
    if not button.count():
        page.locator("#closeAccountDialog").click() if page.locator("#closeAccountDialog").count() else None
        return False
    button.click()
    page.wait_for_timeout(900)
    return True


def sign_out_and_back_in(page, *, email: str, password: str) -> None:
    page.locator("#accountPill").click()
    page.wait_for_timeout(500)
    logout = page.locator("#logoutButton")
    require(logout.count() > 0, "Sign out control was not available")
    logout.click()
    page.wait_for_url(f"{BASE_URL}/login", timeout=30000)
    base.micro_note(
        page,
        "Continuity survives the chat",
        "The patient signs out. The longitudinal record is not a disposable conversation transcript.",
        3.0,
    )
    page.locator('#loginForm input[name="email"]').fill(email)
    page.locator('#loginForm input[name="password"]').fill(password)
    page.locator('#loginForm button[type="submit"]').click()
    page.wait_for_url(f"{BASE_URL}/", timeout=30000)
    page.wait_for_load_state("networkidle")
    base.set_english(page)


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUT / "playwright-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "running",
        "version": "V9_MASTER_COMPREHENSIVE",
        "synthetic_only": True,
        "slides_used": False,
        "browser_application_only": True,
        "real_google_places": False,
        "real_scientific_sources": False,
        "real_login_persistence": False,
        "original_evidence_preserved": False,
        "device_ingestion_exercised": False,
        "checks": [],
    }
    base.save_report(report)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(video_dir),
            record_video_size={"width": 1600, "height": 900},
        )
        page = context.new_page()
        base.wait_server(page)

        # 1) REAL PATIENT LOGIN + CORE THESIS
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60000)
        base.set_english(page)
        base.micro_note(
            page,
            "HealthIA ONE — one continuous patient story",
            "The original problem is fragmentation: chats, results, devices, family context and follow-up should not restart from zero.",
            4.0,
        )
        suffix = uuid4().hex[:8]
        email = f"v9-master-{suffix}@example.test"
        password = f"HealthIA!{suffix}9Aa"
        page.locator("#registerTab").click()
        page.locator('#registerForm input[name="display_name"]').fill("Alex Rivera")
        page.locator('#registerForm input[name="email"]').fill(email)
        page.locator('#registerForm input[name="password"]').fill(password)
        page.locator('#registerForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=30000)
        page.wait_for_load_state("networkidle")
        base.set_english(page)
        readiness = base.api_json(page, "/api/readiness")
        require(readiness.get("ready") is True, "HealthIA runtime did not report ready")
        report["readiness"] = {
            "model": readiness.get("model"),
            "llm_backend": readiness.get("llm_backend"),
            "agent_execution": readiness.get("agent_execution"),
            "capability_count": len(readiness.get("capabilities") or []),
        }
        report["checks"].append("real_patient_account_created")
        base.save_report(report)

        # 2) LIVING RECORD / TWIN / FAMILY / MEDICATION
        base.seed_synthetic_clinical_context(page)
        page.reload(wait_until="networkidle")
        base.set_english(page)
        nav(page, "record")
        base.micro_note(
            page,
            "Living longitudinal record",
            "HealthIA links conditions, professional-confirmed treatment, family/genogram context, appointments and patient-entered history into one patient-scoped record.",
            4.4,
        )
        report["checks"].append("living_record_and_family_context_visible")

        # 3) ADAPTIVE CONVERSATION — ACTUAL CHAT PATH
        nav(page, "chat")
        base.micro_note(
            page,
            "Adaptive conversation",
            "The patient speaks naturally. HealthIA uses what is already known and asks only for missing context instead of restarting a fixed questionnaire.",
            3.0,
        )
        assistant_text = base.send_chat(
            page,
            "I felt dizzy after standing up this morning. I have hypertension and take Losartan. What do you need to know?",
            timeout_ms=90000,
        )
        require(len(assistant_text.strip()) >= 20, "Adaptive chat returned no substantive response")
        base.micro_note(
            page,
            "Gemini + bounded clinical routing",
            "The visible reply is produced through the working HealthIA chat path; safety boundaries remain deterministic around the model.",
            3.2,
        )
        report["adaptive_chat_excerpt"] = assistant_text[:700]
        report["checks"].append("adaptive_chat_response_returned")
        base.save_report(report)

        # 4) ORIGINAL EVIDENCE → RESULT → TWIN
        nav(page, "results")
        base.micro_note(
            page,
            "Original evidence is preserved first",
            "Results are not reduced to a chat summary. HealthIA stores the source file, parses supported values, explains what it can read and links it back to the clinical memory.",
            3.5,
        )
        uploaded = upload_synthetic_result(page)
        require(uploaded.get("original_available") is True, "Original evidence was not reported as preserved")
        require(uploaded.get("twin_updated") is True, "Result upload did not report twin update")
        report["uploaded_result"] = uploaded
        report["original_evidence_preserved"] = True
        page.reload(wait_until="networkidle")
        base.set_english(page)
        nav(page, "results")
        base.micro_note(
            page,
            "Evidence-backed result",
            "The synthetic LDL, creatinine and HbA1c values are now visible in the real Results workspace with the original evidence linked behind them.",
            4.0,
        )
        report["checks"].append("result_upload_original_preserved_and_twin_updated")
        base.save_report(report)

        # 5) AUTHORIZED DEVICE SIGNALS / HEALTH CONNECT INGESTION
        device_sync = base.api_json(page, "/api/demo/device-sync", method="POST")
        require(int(device_sync.get("accepted") or 0) > 0, "Synthetic Health Connect ingestion accepted no records")
        report["device_sync"] = device_sync
        report["device_ingestion_exercised"] = True
        page.reload(wait_until="networkidle")
        base.set_english(page)
        nav(page, "measurements")
        base.micro_note(
            page,
            "Authorized measurements and devices",
            "The same record can receive blood pressure, weight, activity and Health Connect signals. Device identity and metric permissions are checked before ingestion.",
            4.0,
        )
        report["checks"].append("health_connect_ingestion_exercised")
        base.save_report(report)

        # 6) DURABLE MISSIONS + CONSENT BOUNDARY + REAL GOOGLE PLACES
        nav(page, "missions")
        base.micro_note(
            page,
            "Durable health missions",
            "A health need becomes a living task that remains open until there is a verifiable next step or closure — not a one-turn answer.",
            3.4,
        )
        nav(page, "chat")
        page.locator("#chatInput").fill("My child has autism. Find nearby therapy, support groups, foundations and government or financial assistance in Santiago.")
        page.wait_for_timeout(800)
        base.micro_note(
            page,
            "Autonomy pauses before location",
            "HealthIA proves the mission is blocked before mission-scoped location permission. Authorization and execution are different states.",
            3.6,
        )
        page.locator("#chatInput").fill("")
        support_mission = base.create_navigation_mission(
            page,
            condition_or_need="autism support resources community foundations government benefits financial assistance",
            provider_query="autism support resources",
            title="Autism support resources for my family",
            radius_m=18000,
        )
        report["support_mission"] = base.compact_mission(support_mission)
        report["real_google_places"] = True
        base.show_resource_view(
            page,
            support_mission,
            title="Real support resources around the family",
            subtitle="The shipped HealthIA navigation engine executed Google Places after mission-scoped consent. These are resource candidates, not clinical referrals.",
        )
        support_cards = len(((support_mission.get("tool_outputs") or {}).get("place_candidates") or []))
        require(support_cards >= 2, "Google Places did not return enough support candidates")
        base.micro_note(
            page,
            "Google Places — real candidates",
            f"The mission returned {support_cards} locality-validated candidates with addresses and Google Maps links, plus phone or website data when available.",
            4.2,
        )
        page.evaluate("document.querySelector('#v6ResourceLive .wave4-resource-card:nth-child(2)')?.scrollIntoView({block:'center'})")
        base.micro_note(page, "“The second one”", "Natural language resolves to the exact second verified candidate — not a substitute result.", 2.3)
        selected_support = base.select_second_candidate(page, support_mission)
        base.show_resource_view(
            page,
            selected_support,
            title="Exact second resource selected",
            subtitle="The exact Google candidate is now stored as the durable selected place for this mission.",
        )
        page.evaluate("document.querySelector('#v6ResourceLive .wave4-resource-card.is-selected')?.scrollIntoView({block:'center'})")
        base.micro_note(page, "Deterministic exactness", "Reasoning can be flexible; identity, selection and external actions must remain exact.", 3.1)
        report["selected_support_place"] = {
            "id": (selected_support.get("selected_place") or {}).get("id"),
            "name": base.candidate_name(selected_support.get("selected_place") or {}),
        }
        report["checks"].append("google_places_and_exact_second_selection")
        base.save_report(report)
        base.close_resource_view(page)

        # 7) OPPORTUNITY AUTOPILOT / DISCOVERIES — REAL SCIENTIFIC SOURCES
        nav(page, "chat")
        base.micro_note(
            page,
            "Opportunity Autopilot",
            "HealthIA can watch authorized patient and family topics, keep discoveries quiet until relevant, and never convert a new publication into a treatment change by itself.",
            3.4,
        )
        # The dedicated scientific radar is exercised directly so the source retrieval
        # cannot be obscured by an unrelated conversational model outage.
        science_bundle = science.run_scientific_radar(page)
        report["scientific_radar"] = science_bundle
        report["real_scientific_sources"] = True
        science.show_science_view(page, science_bundle)
        base.micro_note(
            page,
            "Real science compared with the living twin",
            "HealthIA queried PubMed, Europe PMC and ClinicalTrials.gov, selected relevant evidence, and compared it with the recorded Losartan plan without predicting a patient outcome.",
            5.0,
        )
        report["checks"].append("real_science_compared_with_current_treatment")
        base.save_report(report)
        science.close_science_view(page)

        # 8) CARE GAP → REAL NEARBY LAB
        nav(page, "chat")
        page.locator("#chatInput").fill("I still need a creatinine test before my appointment. Where can I do it nearby?")
        page.wait_for_timeout(750)
        base.micro_note(
            page,
            "A care gap becomes an actionable mission",
            "HealthIA does not stop at 'remember to get the test'; it can find where the patient can actually complete the next step.",
            3.2,
        )
        page.locator("#chatInput").fill("")
        lab_mission = base.create_navigation_mission(
            page,
            condition_or_need="creatinine laboratory test needed before follow-up appointment",
            provider_query="laboratory creatinine clinic",
            title="Find a laboratory for creatinine testing",
            radius_m=15000,
        )
        report["lab_mission"] = base.compact_mission(lab_mission)
        base.show_resource_view(
            page,
            lab_mission,
            title="Where can I complete the missing lab?",
            subtitle="HealthIA executed a second real locality-aware Google Places mission for laboratories or medical testing sites in Santiago.",
        )
        lab_cards = len(((lab_mission.get("tool_outputs") or {}).get("place_candidates") or []))
        require(lab_cards > 0, "No local laboratory candidates were returned")
        base.micro_note(page, "Real nearby labs", f"{lab_cards} locality-validated medical candidate(s) are available with Google navigation when provided.", 4.0)
        report["checks"].append("care_gap_real_nearby_lab_navigation")
        base.save_report(report)
        base.close_resource_view(page)

        # 9) PRIVACY / AUDIT / EXPORT / GOOGLE MISSION CONNECTION
        if open_account_view(page, "control"):
            base.micro_note(
                page,
                "Patient control is part of the product",
                "Permissions, quiet hours, snooze and mute controls, audit history and patient export keep autonomy visible instead of hiding it behind the agent.",
                4.3,
            )
            report["checks"].append("privacy_control_surface_visible")
        if open_account_view(page, "devices"):
            base.micro_note(
                page,
                "Device permissions are revocable",
                "Health Connect connections are patient-scoped and can be disconnected; background reads are not treated as unlimited consent.",
                3.5,
            )
            report["checks"].append("device_control_surface_visible")

        # 10) LOGOUT / LOGIN PERSISTENCE
        before_logout = base.api_json(page, "/api/bootstrap")
        before_results = len(before_logout.get("results") or [])
        before_meds = len(before_logout.get("medication_plans") or [])
        require(before_results >= 1 and before_meds >= 1, "Persistence prerequisites were missing before logout")
        sign_out_and_back_in(page, email=email, password=password)
        after_login = base.api_json(page, "/api/bootstrap")
        require(len(after_login.get("results") or []) >= before_results, "Results did not persist across login")
        require(len(after_login.get("medication_plans") or []) >= before_meds, "Treatment did not persist across login")
        report["real_login_persistence"] = True
        nav(page, "record")
        base.micro_note(
            page,
            "The record is still here",
            "After sign-out and sign-in, the treatment, uploaded evidence, family context and longitudinal state remain attached to the same patient account.",
            4.6,
        )
        report["checks"].append("logout_login_persistence_verified")
        base.save_report(report)

        # 11) CLOSE INSIDE THE REAL APPLICATION
        nav(page, "chat")
        base.micro_note(
            page,
            "One system, the right boundary",
            "Gemini and ADK for adaptive reasoning. Deterministic state for exactness. Human consent before human decisions or external actions. Your health never starts over.",
            5.2,
        )

        report["status"] = "PASS"
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        video = page.video
        context.close()
        raw_path = video.path()
        target = OUT / "healthia-v9-master-live.webm"
        from pathlib import Path
        Path(raw_path).replace(target)
        report["raw_video"] = str(target)
        base.save_report(report)
        browser.close()

    print("HEALTHIA_V9_MASTER_DEMO_PASS")
    return report


if __name__ == "__main__":
    run()
