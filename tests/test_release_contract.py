from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_matches_current_patient_os():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for marker in [
        "durable, consent-aware missions",
        "Result Guardian",
        "Appointment Guardian",
        "Post-Visit Guardian",
        "Real autonomous external follow-up",
        "scripts/smoke_test.py",
        "zero Google AI spend",
        "Gemini 3.5 Flash on Vertex AI",
        "HealthIA does **not** autonomously diagnose, prescribe, start/stop/change medication",
    ]:
        assert marker in readme


def test_release_evidence_files_exist():
    required = [
        "docs/ARCHITECTURE.md",
        "docs/DEMO_SCRIPT.md",
        "docs/SECURITY_AND_SAFETY_MATRIX.md",
        "docs/COST_CONTROL.md",
        "deployment/run-local-secure.ps1",
        "deployment/deploy-cloud-demo.ps1",
        "deployment/remove-cloud-demo.ps1",
        "deployment/check_cloud_permissions.py",
        "deployment/verify_cloud_demo.py",
        "scripts/smoke_test.py",
        "scripts/live_taskmaster_proof.py",
    ]
    for relative in required:
        assert (ROOT / relative).is_file(), relative


def test_demo_script_preserves_truth_boundary():
    script = (ROOT / "docs" / "DEMO_SCRIPT.md").read_text(encoding="utf-8")
    for forbidden_claim in [
        "Do **not** claim autonomous diagnosis",
        "autonomous prescribing",
        "clinical sensor validation",
        "regulatory approval",
        "universal security certification",
    ]:
        assert forbidden_claim in script
