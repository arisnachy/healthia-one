from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
PROOF_PATH = ROOT / "deployment" / "live-gemini-proof-latest.json"


def choose_safe_option(question: dict) -> str:
    options = [str(item) for item in question.get("options") or []]
    preferred = (
        "ninguna",
        "no ",
        "no he",
        "no tengo",
        "no identifico",
        "no estoy",
        "sin ",
    )
    for prefix in preferred:
        for option in options:
            if prefix in option.lower():
                return option
    return options[-1] if options else "No estoy seguro"


def answer_payload(interview: dict) -> str:
    block = interview["question_block"]
    answers = []
    for question in block["questions"]:
        answers.append(
            {
                "question_id": question["id"],
                "question_prompt": question["prompt"],
                "selected": [choose_safe_option(question)],
                "detail": "",
            }
        )
    return "[ENTREVISTA_CLINICA]" + json.dumps(
        {"interview_id": interview["id"], "stage": block["stage"], "answers": answers},
        ensure_ascii=False,
    )


def tiny_pdf() -> bytes:
    text = "SYNTHETIC LAB RESULT - Glucose 104 mg/dL - Hemoglobin 14.2 g/dL"
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>endobj\n",
        b"4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
        b"5 0 obj<< /Length " + str(len(stream)).encode() + b" >>stream\n" + stream + b"\nendstream endobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fallback_diagnostic(message: dict) -> str:
    metadata = message.get("metadata") or {}
    review = metadata.get("judge_review") or {}
    blockers = review.get("blockers") or []
    parts = [str(item) for item in blockers if str(item).strip()]
    if metadata.get("llm_error"):
        parts.append(str(metadata["llm_error"]))
    diagnostic = " | ".join(parts) or "no sanitized fallback diagnostic available"
    secret = os.getenv("GEMINI_API_KEY") or ""
    if secret:
        diagnostic = diagnostic.replace(secret, "[redacted]")
    return diagnostic[:900]


def main() -> int:
    required_env = ["GEMINI_API_KEY", "HEALTHIA_SESSION_SECRET", "HEALTHIA_DEVICE_TOKEN_SECRET"]
    missing = [name for name in required_env if not os.getenv(name)]
    if missing:
        print("HEALTHIA_LIVE_PROOF_BLOCKED: missing required secret environment")
        return 2

    from app.main import app

    proof: dict = {
        "status": "running",
        "model": os.getenv("HEALTHIA_MODEL", ""),
        "checks": [],
        "synthetic_only": True,
        "transport": "https_testclient",
    }

    suffix = uuid4().hex[:10]
    password = f"HealthIA!{suffix}Aa9"
    email_a = f"live-a-{suffix}@example.test"
    email_b = f"live-b-{suffix}@example.test"

    try:
        with TestClient(app, base_url="https://healthia.test") as client:
            require(client.get("/api/bootstrap").status_code == 401, "protected API accepted anonymous request")
            proof["checks"].append("anonymous_patient_api_rejected")

            created_a = client.post(
                "/api/auth/register",
                json={"display_name": "Paciente Sintético A", "email": email_a, "password": password},
            )
            require(created_a.status_code == 201, f"patient A registration failed: {created_a.text[:300]}")
            session_a = created_a.json()
            patient_a = session_a["account"]["patient_id"]
            require(patient_a.startswith("patient_"), "patient A id not bound")
            require(client.get("/api/auth/session").json().get("authenticated") is True, "secure patient session cookie was not retained")
            proof["checks"].append("patient_a_authenticated")
            proof["checks"].append("secure_session_cookie_roundtrip")

            weight = client.post("/api/weight", json={"weight_kg": 81.2, "note": "synthetic isolation marker"})
            require(weight.status_code == 200, f"patient A weight write failed: HTTP {weight.status_code} {weight.text[:300]}")
            proof["checks"].append("patient_a_scoped_write")

            complaint = "Desde ayer tengo ardor al orinar y voy al baño muy seguido. Quiero saber qué información necesitas para orientarme."
            first = client.post("/api/chat", json={"message": complaint})
            require(first.status_code == 200, f"first clinical chat failed: {first.text[:500]}")
            first_message = first.json()["message"]
            first_interview = first_message["metadata"].get("clinical_interview") or {}
            block1 = first_interview.get("question_block") or {}
            first_status = first_message["metadata"].get("llm_status")
            if first_status != "dynamic_clinical_questions":
                diagnostic = fallback_diagnostic(first_message)
                proof["first_clinical_status"] = first_status
                proof["first_clinical_diagnostic"] = diagnostic
                raise AssertionError(f"first block did not come from live Gemini: {first_status}; diagnostic: {diagnostic}")
            require(first_interview.get("question_source") == "gemini_dynamic", "first question source not Gemini")
            require(len(block1.get("questions") or []) == 5, "first block is not exactly five questions")
            proof["checks"].append("gemini_adk_first_five_questions")
            proof["first_question_prompts"] = [q["prompt"] for q in block1["questions"]]

            second = client.post("/api/chat", json={"message": answer_payload(first_interview)})
            require(second.status_code == 200, f"second clinical chat failed: {second.text[:500]}")
            second_message = second.json()["message"]
            second_interview = second_message["metadata"].get("clinical_interview") or {}
            block2 = second_interview.get("question_block") or {}
            second_status = second_message["metadata"].get("llm_status")
            if second_status != "dynamic_clinical_questions":
                diagnostic = fallback_diagnostic(second_message)
                proof["second_clinical_status"] = second_status
                proof["second_clinical_diagnostic"] = diagnostic
                raise AssertionError(f"second block did not come from live Gemini: {second_status}; diagnostic: {diagnostic}")
            require(second_interview.get("question_source") == "gemini_dynamic", "second question source not Gemini")
            require(len(block2.get("questions") or []) == 5, "second block is not exactly five questions")
            previous = second_interview.get("previous_answers") or []
            require(len(previous) >= 5, "interview did not preserve first-block memory")
            require(all(item.get("question_prompt") for item in previous[:5]), "question meaning was lost from interview memory")
            first_prompts = {q["prompt"].strip().lower() for q in block1["questions"]}
            second_prompts = {q["prompt"].strip().lower() for q in block2["questions"]}
            require(not first_prompts.intersection(second_prompts), "second block repeated a first-block question verbatim")
            proof["checks"].append("second_block_uses_accumulated_question_memory")
            proof["second_question_prompts"] = [q["prompt"] for q in block2["questions"]]

            resolution = client.post("/api/chat", json={"message": answer_payload(second_interview)})
            require(resolution.status_code == 200, f"clinical resolution failed: {resolution.text[:500]}")
            resolution_message = resolution.json()["message"]
            resolution_interview = resolution_message["metadata"].get("clinical_interview") or {}
            status = resolution_message["metadata"].get("llm_status")
            if status == "dynamic_clinical_followup_questions":
                block3 = resolution_interview.get("question_block") or {}
                require(len(block3.get("questions") or []) == 5, "third adaptive block not five questions")
                require(len(resolution_interview.get("previous_answers") or []) >= 10, "third block lost accumulated memory")
                proof["checks"].append("gemini_decided_material_third_block")
                final = client.post("/api/chat", json={"message": answer_payload(resolution_interview)})
                require(final.status_code == 200, f"final clinical synthesis failed: {final.text[:500]}")
                resolution_message = final.json()["message"]
                status = resolution_message["metadata"].get("llm_status")
            require(status == "clinical_ai_orientation_completed", f"AI did not close with patient orientation: {status}")
            require(len(resolution_message.get("content", "")) >= 120, "patient orientation unexpectedly short")
            require(resolution_message["metadata"].get("clinical_synthesis_source") == "gemini", "final orientation source not Gemini")
            proof["checks"].append("gemini_decides_when_to_orient_patient")

            audit_payload = client.get("/api/audit?limit=100").json()
            adk_events = [
                event for event in audit_payload["events"]
                if event.get("actor") == "google_adk" and event.get("action") == "execute_demand_driven_clinical_plan"
            ]
            require(len(adk_events) >= 2, "Google ADK execution trajectory missing")
            for event in adk_events:
                roles = event.get("details", {}).get("executed_roles") or []
                require("interview" in roles and "safety" in roles, "ADK mandatory tools missing")
                require(len(roles) <= 4, "ADK activated too many tools")
            proof["checks"].append("auditable_google_adk_tool_trajectory")
            proof["adk_event_count"] = len(adk_events)

            pdf = tiny_pdf()
            uploaded = client.post(
                "/api/results/upload",
                files={"file": ("synthetic-lab.pdf", pdf, "application/pdf")},
            )
            require(uploaded.status_code == 200, f"multimodal upload failed: {uploaded.text[:500]}")
            result = uploaded.json()
            require(result.get("status") == "parsed", f"Gemini did not parse synthetic PDF: {result.get('status')}")
            require(result.get("document_id"), "original evidence document not linked")
            require(result.get("twin_updated") is True, "clinical twin not updated")
            original = client.get(f"/api/documents/{result['document_id']}/download")
            require(original.status_code == 200 and original.content == pdf, "original evidence did not round-trip byte-for-byte")
            proof["checks"].append("live_gemini_multimodal_original_twin_roundtrip")

            client.post("/api/auth/logout")
            require(client.get("/api/bootstrap").status_code == 401, "logout did not revoke browser access")
            created_b = client.post(
                "/api/auth/register",
                json={"display_name": "Paciente Sintético B", "email": email_b, "password": password},
            )
            require(created_b.status_code == 201, "patient B registration failed")
            patient_b = created_b.json()["account"]["patient_id"]
            require(patient_b != patient_a, "two accounts share patient identity")
            state_b_response = client.get("/api/bootstrap")
            require(state_b_response.status_code == 200, "patient B bootstrap failed")
            state_b = state_b_response.json()
            require(state_b["profile"]["id"] == patient_b, "patient B state identity mismatch")
            require(not any(abs(float(item["weight_kg"]) - 81.2) < 0.001 for item in state_b.get("weights") or []), "patient B can see patient A weight")
            require(all(item.get("patient_id", patient_b) == patient_b for item in state_b.get("messages") or []), "patient B received patient A messages")
            proof["checks"].append("two_patient_state_isolation")

            client.post("/api/auth/logout")
            login_a = client.post("/api/auth/login", json={"email": email_a, "password": password})
            require(login_a.status_code == 200, "patient A re-login failed")
            state_a_response = client.get("/api/bootstrap")
            require(state_a_response.status_code == 200, "patient A bootstrap failed after login")
            state_a = state_a_response.json()
            require(state_a["profile"]["id"] == patient_a, "patient A state identity mismatch after login")
            require(any(abs(float(item["weight_kg"]) - 81.2) < 0.001 for item in state_a.get("weights") or []), "patient A own longitudinal state was not recovered")
            proof["checks"].append("logout_relogin_restores_only_own_state")

            readiness = client.get("/api/readiness").json()
            require(readiness.get("agent_execution") == "demand_driven", "runtime is not demand driven")
            require(readiness.get("auth_required") is True, "live proof did not run with auth required")
            proof["checks"].append("demand_driven_authenticated_runtime")

        proof["status"] = "passed"
        proof["patient_ids_distinct"] = True
        PROOF_PATH.write_text(json.dumps(proof, ensure_ascii=False, indent=2), "utf-8")
        print("HEALTHIA_LIVE_GEMINI_PROOF_PASSED")
        print(json.dumps({"status": proof["status"], "checks": proof["checks"], "model": proof["model"]}, ensure_ascii=False))
        return 0
    except Exception as exc:
        proof["status"] = "failed"
        proof["error_type"] = type(exc).__name__
        proof["error"] = str(exc)[:1000]
        PROOF_PATH.write_text(json.dumps(proof, ensure_ascii=False, indent=2), "utf-8")
        print(f"HEALTHIA_LIVE_GEMINI_PROOF_FAILED: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())