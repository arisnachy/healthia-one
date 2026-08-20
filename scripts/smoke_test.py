from __future__ import annotations

import os
from io import BytesIO
from tempfile import TemporaryDirectory

_SMOKE_TEMP = TemporaryDirectory(prefix="healthia-smoke-")
os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"
os.environ["HEALTHIA_PROACTIVE_INTERVAL_SECONDS"] = "3600"
os.environ["HEALTHIA_AUTH_REQUIRED"] = "true"
os.environ["HEALTHIA_ACCOUNTS_PATH"] = os.path.join(_SMOKE_TEMP.name, "accounts.json")

from fastapi.testclient import TestClient

from app.main import app


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run() -> None:
    with TestClient(app) as client:
        health = client.get("/healthz")
        require(health.status_code == 200, "healthz failed")

        readiness = client.get("/api/readiness").json()
        for capability in (
            "family_genogram",
            "document_archive",
            "unified_timeline",
            "medication_checkins",
            "appointments",
            "patient_consent",
            "audit_log",
            "patient_export",
        ):
            require(capability in readiness["capabilities"], f"missing capability: {capability}")

        registration = client.post(
            "/api/auth/register",
            json={
                "email": "synthetic-smoke@example.test",
                "password": "SyntheticSmokePassword!42",
                "display_name": "Synthetic Smoke Patient",
            },
        )
        require(registration.status_code == 201, "secure patient registration failed")
        require(registration.json()["authenticated"] is True, "secure patient session missing")
        private_bootstrap = client.get("/api/bootstrap")
        require(private_bootstrap.status_code == 200, "authenticated patient bootstrap failed")
        require(private_bootstrap.json()["profile"]["display_name"], "authenticated patient profile missing")
        require(client.post("/api/auth/logout").status_code == 200, "secure logout failed")

        # The remaining checks exercise the deterministic synthetic judge
        # fixture. Tests set this explicitly; the shipped product stays secure
        # by default and cloud mode cannot disable authentication.
        app.state.account_manager.settings.auth_required = False
        reset = client.post("/api/demo/reset")
        require(reset.status_code == 200, "synthetic fixture reset failed")

        bootstrap = client.get("/api/bootstrap").json()
        require(bootstrap["profile"]["display_name"], "patient profile missing")
        require(bootstrap["family_members"], "synthetic genogram missing")
        require(bootstrap["medication_plans"], "treatment plan missing")
        require(bootstrap["appointments"], "appointment missing")

        family_chat = client.post(
            "/api/chat",
            json={"message": "Muéstrame mi genograma y antecedentes familiares"},
        ).json()
        require(family_chat["mission"]["mission_type"] == "family_history", "family route failed")

        document = client.post(
            "/api/documents/upload",
            data={"category": "consultation", "title": "Nota sintética"},
            files={"file": ("nota-sintetica.txt", BytesIO(b"synthetic patient note"), "text/plain")},
        )
        require(document.status_code == 200, "document upload failed")
        document_id = document.json()["id"]
        require(client.get(f"/api/documents/{document_id}/download").status_code == 200, "document download failed")

        treatment = client.get("/api/treatment").json()
        medication_id = treatment["active_plans"][0]["id"]
        checkin = client.post(
            "/api/treatment/checkins",
            json={"medication_id": medication_id, "status": "taken", "note": "smoke test"},
        )
        require(checkin.status_code == 200, "medication check-in failed")

        consultation = client.post(
            "/api/chat",
            json={"message": "Prepara mi próxima consulta"},
        ).json()
        require(
            consultation["mission"]["mission_type"] == "consultation_preparation",
            "consultation route failed",
        )
        require(client.get("/api/consultation-brief").json()["questions"], "consultation brief missing")

        timeline = client.get("/api/timeline").json()["events"]
        event_types = {event["type"] for event in timeline}
        require({"vital", "weight", "activity", "document", "medication", "appointment"}.issubset(event_types), "timeline incomplete")

        consent = client.get("/api/consent").json()
        consent["quiet_hours_start"] = "22:00"
        consent["quiet_hours_end"] = "07:00"
        require(client.put("/api/consent", json=consent).status_code == 200, "consent update failed")

        first_tick = client.post("/api/demo/tick").json()
        second_tick = client.post("/api/demo/tick").json()
        require(first_tick["created"] >= 1, "manual agent review produced no findings")
        require(second_tick["created"] == 0, "manual agent review was not idempotent")

        control_chat = client.post(
            "/api/chat",
            json={"message": "Muéstrame mis permisos, auditoría y exportación"},
        ).json()
        require(control_chat["mission"]["mission_type"] == "patient_control", "control route failed")

        audit = client.get("/api/audit").json()
        require(audit["count"] > 0, "audit log is empty")
        exported = client.get("/api/export")
        require(exported.status_code == 200, "patient export failed")
        require(exported.json()["export"]["contains_binary_files"] is False, "export boundary missing")

    print("HealthIA ONE smoke test: PASS")


if __name__ == "__main__":
    try:
        run()
    finally:
        _SMOKE_TEMP.cleanup()
