import os
from datetime import datetime, timedelta, timezone

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"

from fastapi.testclient import TestClient

from app.main import app


def test_timeline_treatment_and_consultation_endpoints():
    with TestClient(app) as client:
        timeline = client.get("/api/timeline")
        treatment = client.get("/api/treatment")
        appointments = client.get("/api/appointments")
        brief = client.get("/api/consultation-brief")
        assert timeline.status_code == 200 and timeline.json()["events"]
        assert treatment.status_code == 200 and treatment.json()["active_plans"]
        assert appointments.status_code == 200 and appointments.json()["appointments"]
        assert brief.status_code == 200 and brief.json()["questions"]


def test_medication_checkin_requires_existing_plan():
    with TestClient(app) as client:
        treatment = client.get("/api/treatment").json()
        medication_id = treatment["active_plans"][0]["id"]
        success = client.post(
            "/api/treatment/checkins",
            json={"medication_id": medication_id, "status": "taken"},
        )
        missing = client.post(
            "/api/treatment/checkins",
            json={"medication_id": "med_missing", "status": "taken"},
        )
        assert success.status_code == 200
        assert missing.status_code == 404


def test_patient_can_add_an_appointment():
    with TestClient(app) as client:
        response = client.post(
            "/api/appointments",
            json={
                "title": "Consulta sintética de seguimiento",
                "specialty": "Medicina familiar",
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "location": "Centro sintético",
                "required_documents": ["Resultados"],
                "questions": ["¿Cuál es el próximo paso?"],
            },
        )
        assert response.status_code == 200
        listing = client.get("/api/appointments").json()["appointments"]
        assert any(item["id"] == response.json()["id"] for item in listing)
