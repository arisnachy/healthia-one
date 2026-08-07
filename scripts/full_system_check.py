from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"
os.environ["HEALTHIA_PROACTIVE_ENABLED"] = "false"
os.environ["HEALTHIA_COST_MODE"] = "local"
os.environ["HEALTHIA_AI_REQUEST_LIMIT"] = "0"

from fastapi.testclient import TestClient

from app.main import app
from healthia_one.clinical_intake import ANSWER_PREFIX


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def answers_for(interview: dict) -> str:
    questions = interview["question_block"]["questions"]
    answers = [
        {
            "question_id": question["id"],
            "question_prompt": question["prompt"],
            "selected": [question["options"][0]],
            "detail": "",
        }
        for question in questions
    ]
    return ANSWER_PREFIX + json.dumps(
        {"interview_id": interview["id"], "stage": interview["stage"], "answers": answers},
        ensure_ascii=False,
    )


def check(response, label: str, expected: int = 200):
    require(response.status_code == expected, f"{label}: HTTP {response.status_code} {response.text[:300]}")
    return response.json()


def run() -> dict:
    checks: dict[str, str] = {}
    now = datetime.now(timezone.utc)
    with TestClient(app) as client:
        check(client.post("/api/demo/reset"), "reset")
        check(client.get("/healthz"), "healthz")
        readiness = check(client.get("/api/readiness"), "readiness")
        require(readiness["cost_control"]["mode"] == "local", "local cost mode not active")
        require(readiness["cost_control"]["enabled"] is False, "AI should start disabled")
        checks["startup_and_cost_guard"] = "pass"

        initial = check(client.get("/api/bootstrap"), "bootstrap")
        require(initial["profile"]["display_name"] == "Ana Martínez", "synthetic identity missing")
        require(initial["vitals"] and initial["weights"] and initial["activity"], "seed continuity missing")
        checks["bootstrap_continuity"] = "pass"

        first = check(
            client.post("/api/chat", json={"message": "Desde ayer me arde al orinar y tengo que ir al baño a cada rato"}),
            "clinical block 1",
        )
        interview1 = first["message"]["metadata"]["clinical_interview"]
        require(len(interview1["question_block"]["questions"]) == 5, "block 1 must have five questions")
        require(first["message"]["metadata"]["question_source"] == "safe_fallback", "local fallback must be explicit")

        second = check(client.post("/api/chat", json={"message": answers_for(interview1)}), "clinical block 2")
        interview2 = second["message"]["metadata"]["clinical_interview"]
        require(interview2["chief_complaint"].startswith("Desde ayer me arde"), "chief complaint was lost")
        require(len(interview2["question_block"]["questions"]) == 5, "block 2 must have five questions")

        final = check(client.post("/api/chat", json={"message": answers_for(interview2)}), "clinical completion")
        require(final["message"]["metadata"]["clinical_interview"]["status"] == "completed", "interview did not complete")
        require("Desde ayer me arde al orinar" in final["message"]["content"], "final summary lost complaint")
        require("Las áreas clínicas necesarias" in final["message"]["content"], "final summary overclaims council")
        after_clinical = check(client.get("/api/bootstrap"), "post-clinical bootstrap")
        mission = next(item for item in after_clinical["missions"] if item["id"] == first["mission"]["id"])
        require(mission["status"] == "waiting_professional", "mission state did not advance")
        require(mission["closure_evidence"] == ["interview_two_blocks_completed"], "closure evidence missing")
        checks["clinical_closed_loop"] = "pass"

        urgent = check(
            client.post("/api/chat", json={"message": "Tengo dolor fuerte en el pecho y no puedo respirar"}),
            "urgent safety",
        )
        require(urgent["message"]["risk_level"] == "urgent", "urgent message not escalated")
        require("clinical_interview" not in urgent["message"]["metadata"], "urgent flow must not open routine intake")
        checks["deterministic_safety"] = "pass"

        check(client.post("/api/vitals", json={"systolic": 132, "diastolic": 84, "pulse": 72}), "vital")
        check(client.post("/api/weight", json={"weight_kg": 79.8, "note": "same scale"}), "weight")
        check(client.post("/api/activity", json={"steps": 5200, "active_minutes": 31}), "activity")
        checks["measurements"] = "pass"

        result_payload = {
            "panel": "Panel sintético de verificación",
            "results": [{"name": "LDL", "value": 128, "unit": "mg/dL", "reference": "<100"}],
        }
        parsed_result = check(
            client.post(
                "/api/results/upload",
                files={"file": ("labs.json", BytesIO(json.dumps(result_payload).encode()), "application/json")},
            ),
            "structured result",
        )
        require(parsed_result["status"] == "parsed" and parsed_result["explained"] is True, "result was not parsed")
        pending_result = check(
            client.post(
                "/api/results/upload",
                files={"file": ("scan.pdf", BytesIO(b"%PDF synthetic"), "application/pdf")},
            ),
            "unread pdf",
        )
        require(pending_result["status"] == "pending_multimodal", "PDF truth boundary failed")
        checks["results_truth_boundary"] = "pass"

        document = check(
            client.post(
                "/api/documents/upload",
                data={"category": "consultation", "title": "Nota de verificación"},
                files={"file": ("note.txt", BytesIO(b"synthetic note"), "text/plain")},
            ),
            "document upload",
        )
        require(client.get(f"/api/documents/{document['id']}/download").status_code == 200, "document download failed")
        checks["document_round_trip"] = "pass"

        normalized = check(
            client.post("/api/profile/medications/normalize", json={"text": "Metformina 500 mg vía oral cada 12 horas"}),
            "medication normalize",
        )
        suggestion = normalized["suggestion"]
        suggestion.update({"purpose": "Dato sintético", "verification_status": "patient_confirmed"})
        plan = check(client.post("/api/treatment/plans", json=suggestion), "add medication")
        check(client.post("/api/treatment/checkins", json={"medication_id": plan["id"], "status": "taken"}), "medication checkin")
        checks["medication_workflow"] = "pass"

        family = check(
            client.post(
                "/api/family",
                json={
                    "display_name": "Tía materna",
                    "relation": "tía materna",
                    "generation": -1,
                    "lineage": "maternal",
                    "sex_at_birth": "female",
                    "conditions": [{"name": "Diabetes", "confirmed": True}],
                },
            ),
            "family member",
        )
        require(family["relation"] == "tía materna", "family member not stored")
        checks["family_history"] = "pass"

        appointment = check(
            client.post(
                "/api/appointments",
                json={
                    "title": "Seguimiento sintético",
                    "specialty": "Medicina familiar",
                    "scheduled_at": (now + timedelta(days=5)).isoformat(),
                    "location": "Centro sintético",
                    "required_documents": ["Resultados"],
                    "questions": ["¿Cuál es el siguiente paso?"],
                },
            ),
            "appointment",
        )
        brief = check(client.get(f"/api/consultation-brief?appointment_id={appointment['id']}"), "consultation brief")
        require(brief["appointment"]["id"] == appointment["id"], "consultation brief mismatch")
        check(
            client.post(
                "/api/goals",
                json={
                    "title": "Serie de presión",
                    "metric": "mediciones",
                    "target": "dos por sesión",
                    "review_at": (now + timedelta(days=3)).isoformat(),
                },
            ),
            "goal",
        )
        checks["appointments_and_goals"] = "pass"

        pairing = check(client.post("/api/devices/pairing"), "pairing create")
        status = check(client.get(f"/api/devices/pairing/{pairing['code']}"), "pairing status")
        require(status["claimed"] is False, "new pairing already claimed")
        claim = check(
            client.post(
                "/api/devices/pairing/claim",
                json={"code": pairing["code"], "device_id": "full-check-phone", "display_name": "Full check phone"},
            ),
            "pairing claim",
        )
        sync = check(
            client.post(
                "/api/devices/health-connect/sync",
                headers={"Authorization": f"Bearer {claim['access_token']}"},
                json={
                    "device_id": "full-check-phone",
                    "source_package": "com.healthia.fullcheck",
                    "background_read": True,
                    "records": [
                        {
                            "external_id": "full-check-heart-1",
                            "metric": "heart_rate",
                            "observed_at": now.isoformat(),
                            "value": 74,
                            "unit": "bpm",
                            "source_package": "com.healthia.fullcheck",
                        }
                    ],
                },
            ),
            "health connect sync",
        )
        require(sync["accepted"] == 1, "device record not accepted")
        checks["device_pairing_and_sync"] = "pass"

        consent = check(client.get("/api/consent"), "consent")
        consent["quiet_hours_start"] = "21:30"
        consent["quiet_hours_end"] = "07:30"
        check(client.put("/api/consent", json=consent), "consent update")
        check(client.post("/api/consent/snooze", json={"hours": 2}), "consent snooze")
        check(client.post("/api/consent/mute", json={"prefix": "activity."}), "consent mute")
        checks["patient_control"] = "pass"

        timeline = check(client.get("/api/timeline"), "timeline")
        require(len(timeline["events"]) >= 8, "timeline did not aggregate created data")
        audit = check(client.get("/api/audit"), "audit")
        require(audit["count"] >= 10, "audit evidence too small")
        exported = client.get("/api/export")
        require(exported.status_code == 200 and exported.json()["export"]["contains_binary_files"] is False, "safe export failed")
        checks["timeline_audit_export"] = "pass"

        first_tick = check(client.post("/api/demo/tick"), "proactive tick 1")
        second_tick = check(client.post("/api/demo/tick"), "proactive tick 2")
        require(first_tick["created"] >= 1, "proactive check produced no work")
        require(second_tick["created"] == 0, "proactive check is not idempotent")
        checks["proactive_idempotency"] = "pass"

        agentic = check(client.post("/api/demo/agentic-closed-loop"), "agentic closed loop")
        require(agentic["model_calls"] == 0, "CI agentic proof must stay zero-spend")
        require(agentic["final_trace"]["mission"]["status"] == "completed", "agentic mission did not close")
        require(agentic["final_trace"]["artifacts"], "agentic closure artifact missing")
        stages = {item["stage"] for item in agentic["final_trace"]["run"]["events"]}
        require({"trigger", "tool", "persistence", "closure"}.issubset(stages), "agentic trace is incomplete")
        checks["agentic_closed_loop"] = "pass"

    return {"status": "PASS", "check_count": len(checks), "checks": checks}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
