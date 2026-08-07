from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
PROOF_PATH = ROOT / "deployment" / "live-taskmaster-proof-latest.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def tiny_pdf() -> bytes:
    text = "SYNTHETIC TASKMASTER LAB - Glucose 104 mg/dL - Hemoglobin 14.2 g/dL"
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


def main() -> int:
    required = ["GEMINI_API_KEY", "HEALTHIA_SESSION_SECRET", "HEALTHIA_DEVICE_TOKEN_SECRET"]
    if any(not os.getenv(name) for name in required):
        print("HEALTHIA_TASKMASTER_PROOF_BLOCKED: missing required secret environment")
        return 2

    from app.main import app

    proof: dict = {
        "status": "running",
        "synthetic_only": True,
        "model": os.getenv("HEALTHIA_MODEL", ""),
        "expected_gemini_requests": 1,
        "checks": [],
    }
    suffix = uuid4().hex[:10]
    password = f"Taskmaster!{suffix}Aa9"
    email_a = f"taskmaster-a-{suffix}@example.test"
    email_b = f"taskmaster-b-{suffix}@example.test"

    try:
        with TestClient(app, base_url="https://healthia.test") as client:
            created = client.post(
                "/api/auth/register",
                json={"display_name": "Paciente Taskmaster A", "email": email_a, "password": password},
            )
            require(created.status_code == 201, f"patient A registration failed: {created.text[:300]}")
            patient_a = created.json()["account"]["patient_id"]
            proof["checks"].append("authenticated_patient_created")

            pdf = tiny_pdf()
            uploaded = client.post(
                "/api/results/upload",
                files={"file": ("taskmaster-synthetic-lab.pdf", pdf, "application/pdf")},
            )
            require(uploaded.status_code == 200, f"result upload failed: {uploaded.text[:500]}")
            result = uploaded.json()
            if result.get("status") != "parsed":
                readiness = client.get("/api/readiness").json()
                raise AssertionError(
                    "Gemini multimodal did not parse the synthetic PDF: "
                    f"status={result.get('status')} ai_status={readiness.get('ai_status')} "
                    f"detail={str(result.get('explanation') or '')[:500]}"
                )
            require(result.get("document_id"), "uploaded result missing linked original document")
            require(result.get("twin_updated") is True, "uploaded result did not update clinical twin")
            proof["checks"].append("one_gemini_multimodal_request_persisted_result_original_and_twin")

            original = client.get(f"/api/documents/{result['document_id']}/download")
            require(original.status_code == 200 and original.content == pdf, "original PDF failed byte-for-byte round-trip")
            proof["checks"].append("original_evidence_roundtrip")

            usage_after_upload = client.get("/api/readiness").json()["cost_control"]
            require(usage_after_upload.get("requests_used") == 1, f"upload should use exactly one Gemini request: {usage_after_upload}")

            chat = client.post(
                "/api/chat",
                json={"message": "Explícame el resultado taskmaster-synthetic-lab.pdf que acabo de subir y confirma que quedó guardado."},
            )
            require(chat.status_code == 200, f"result retrieval chat failed: {chat.text[:500]}")
            payload = chat.json()
            mission = payload.get("mission") or {}
            require(mission.get("mission_type") == "result_explanation", "wrong Taskmaster mission type")
            require(mission.get("status") == "completed", f"Taskmaster mission did not close: {mission.get('status')}")
            require(result["id"] in (mission.get("evidence_ids") or []), "mission missing result evidence id")
            require(result["document_id"] in (mission.get("evidence_ids") or []), "mission missing original document id")
            closures = mission.get("closure_evidence") or []
            for marker in (
                "persisted_result_retrieved",
                "patient_explanation_returned",
                "original_evidence_link_resolved",
            ):
                require(marker in closures, f"mission missing closure evidence: {marker}")
            metadata = payload["message"].get("metadata") or {}
            require(metadata.get("llm_status") == "persisted_result_retrieval", f"retrieval unexpectedly used/altered AI path: {metadata.get('llm_status')}")
            require(metadata.get("ai_request_skipped") is True, "retrieval did not prove redundant Gemini call was skipped")
            usage_after_chat = client.get("/api/readiness").json()["cost_control"]
            require(usage_after_chat.get("requests_used") == 1, f"closed mission spent a second Gemini request: {usage_after_chat}")
            proof["checks"].append("closed_loop_taskmaster_mission_without_second_ai_call")

            client.post("/api/auth/logout")
            created_b = client.post(
                "/api/auth/register",
                json={"display_name": "Paciente Taskmaster B", "email": email_b, "password": password},
            )
            require(created_b.status_code == 201, "patient B registration failed")
            patient_b = created_b.json()["account"]["patient_id"]
            require(patient_b != patient_a, "patient identities collided")
            state_b = client.get("/api/bootstrap").json()
            require(not state_b.get("results"), "patient B can see patient A result")
            require(not state_b.get("documents"), "patient B can see patient A document")
            require(not any(item.get("mission_type") == "result_explanation" for item in state_b.get("missions") or []), "patient B can see patient A closed mission")
            proof["checks"].append("closed_outcome_is_patient_isolated")

            client.post("/api/auth/logout")
            login_a = client.post("/api/auth/login", json={"email": email_a, "password": password})
            require(login_a.status_code == 200, "patient A re-login failed")
            state_a = client.get("/api/bootstrap").json()
            closed = [
                item for item in state_a.get("missions") or []
                if item.get("mission_type") == "result_explanation" and item.get("status") == "completed"
            ]
            require(closed, "closed Taskmaster mission was not durable across logout/login")
            require(result["id"] in closed[-1].get("evidence_ids", []), "durable mission lost result provenance")
            require(result["document_id"] in closed[-1].get("evidence_ids", []), "durable mission lost original provenance")
            proof["checks"].append("closed_outcome_persists_across_relogin")

        proof["status"] = "passed"
        proof["gemini_requests_used"] = 1
        proof["mission"] = {
            "type": mission.get("mission_type"),
            "status": mission.get("status"),
            "evidence_count": len(mission.get("evidence_ids") or []),
            "closure_evidence": closures,
        }
        PROOF_PATH.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
        print("HEALTHIA_LIVE_TASKMASTER_PROOF_PASSED")
        print(json.dumps({"status": proof["status"], "checks": proof["checks"], "gemini_requests_used": 1}, ensure_ascii=False))
        return 0
    except Exception as exc:
        proof["status"] = "failed"
        proof["error_type"] = type(exc).__name__
        proof["error"] = str(exc)[:1200]
        PROOF_PATH.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_LIVE_TASKMASTER_PROOF_FAILED: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
