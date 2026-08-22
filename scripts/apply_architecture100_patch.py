from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_main() -> None:
    path = Path("app/main.py")
    text = path.read_text("utf-8")
    text = replace_once(
        text,
        "from healthia_one.pairing import DevicePairingManager, PairingError\nfrom healthia_one.service import HealthIAService\n",
        "from healthia_one.pairing import DevicePairingManager, PairingError\n"
        "from healthia_one.runtime_architecture import build_pairing_manager, build_service, runtime_readiness\n"
        "from healthia_one.service import HealthIAService\n",
        label="runtime architecture import",
    )
    text = replace_once(
        text,
        "service = HealthIAService(settings)\npairing_manager = DevicePairingManager()\n",
        "service = build_service(settings)\npairing_manager = build_pairing_manager(settings)\n",
        label="runtime factories",
    )

    start = text.index('@app.get("/api/readiness")')
    end = text.index('\n\n@app.get("/api/cost-control")', start)
    readiness = '''@app.get("/api/readiness")
async def readiness():
    dependency_readiness = await runtime_readiness(
        service,
        settings,
        pairing_manager,
        fcm_registration_store,
    )
    cloud = settings.env.strip().lower() == "cloud"
    patient_sessions_ready = (not cloud) or account_manager.credential_persistence == "restart_safe"
    runtime_checks = dependency_readiness["runtime"]["checks"]
    runtime_checks["patient_sessions_restart_safe"] = patient_sessions_ready
    dependency_readiness["runtime"]["ready"] = all(runtime_checks.values())
    dependency_readiness["ready"] = bool(
        dependency_readiness["ready"] and dependency_readiness["runtime"]["ready"]
    )

    payload = {
        "ready": dependency_readiness["ready"],
        "llm_backend": settings.llm_backend,
        "model": settings.model,
        "adk_ready": settings.adk_ready,
        "ai_ready": settings.adk_ready,
        "ai_status": service.gemini.last_status,
        "store_backend": settings.store_backend,
        "evidence_backend": evidence_backend(),
        "agent_execution": "demand_driven",
        "proactive_enabled": False,
        "living_evaluation_available": bool(settings.evaluation_enabled and settings.evaluation_access_key.strip()),
        "release_sha": settings.release_sha,
        "auth_required": settings.auth_required,
        "patient_session_persistence": account_manager.credential_persistence,
        "patient_state_scope": "authenticated_patient" if settings.auth_required else "demo_patient",
        "cost_control": service.gemini.cost_status(),
        "dependency_readiness": dependency_readiness,
        "capabilities": [
            "chat",
            "gemini_adaptive_clinical_interview",
            "interview_memory",
            "ai_followup_or_orientation_decision",
            "demand_driven_followup",
            "patient_login_logout",
            "patient_scoped_state",
            "patient_scoped_events",
            "vitals",
            "weight",
            "activity",
            "results",
            "multimodal_result_interpretation",
            "clinical_twin",
            "durable_original_evidence",
            "family_genogram",
            "document_archive",
            "unified_timeline",
            "medication_checkins",
            "appointments",
            "consultation_brief",
            "condition_packs",
            "patient_consent",
            "quiet_hours",
            "snooze_and_mute",
            "audit_log",
            "patient_export",
            "patient_profile",
            "reproductive_health",
            "pregnancy_and_postpartum",
            "bmi_and_nutrition_context",
            "health_connect_sync",
            "fcm_private_notifications",
            "device_medication_cross_check",
            "cloud_cost_guard",
            "bounded_living_system_evaluation",
            "multi_instance_pairing",
            "distributed_event_fanout",
            "truthful_dependency_readiness",
        ],
        "truth_boundary": (
            "Patient continuity system. It does not confirm diagnoses, prescribe, change medication, "
            "or replace emergency and professional care."
        ),
    }
    if not payload["ready"]:
        return JSONResponse(status_code=503, content=payload)
    return payload
'''
    text = text[:start] + readiness + text[end:]

    replacements = {
        "payload = pairing_manager.create(patient_id=patient_id)":
            "payload = await asyncio.to_thread(pairing_manager.create, patient_id)",
        "payload = pairing_manager.status(code)":
            "payload = await asyncio.to_thread(pairing_manager.status, code)",
        "initial = pairing_manager.status(code)":
            "initial = await asyncio.to_thread(pairing_manager.status, code)",
        "return pairing_manager.claim(claim.code, claim.device_id, claim.display_name)":
            "return await asyncio.to_thread(pairing_manager.claim, claim.code, claim.device_id, claim.display_name)",
    }
    for old, new in replacements.items():
        text = replace_once(text, old, new, label=f"async pairing boundary: {old}")

    path.write_text(text, "utf-8")


def patch_deploy() -> None:
    path = Path("deployment/deploy-cloud-demo.ps1")
    text = path.read_text("utf-8")
    text = replace_once(
        text,
        'Write-Host "Cloud Run: min 0, max 1; agentes a demanda y proactive=false." -ForegroundColor Green',
        'Write-Host "Cloud Run: min 0, max 3; estado, pairing y eventos distribuidos; proactive=false." -ForegroundColor Green',
        label="deploy description",
    )
    text = replace_once(
        text,
        '"--max-instances", "1",',
        '"--max-instances", "3",',
        label="Cloud Run max instances",
    )
    path.write_text(text, "utf-8")


def patch_env_example() -> None:
    path = Path(".env.example")
    if not path.exists():
        return
    text = path.read_text("utf-8")
    text = text.replace("gemini-3.6-flash", "gemini-3.5-flash")
    path.write_text(text, "utf-8")


if __name__ == "__main__":
    patch_main()
    patch_deploy()
    patch_env_example()
    print("HEALTHIA_ARCHITECTURE_100_PATCH_APPLIED")
