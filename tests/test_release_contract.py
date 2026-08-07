from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_matches_current_patient_os():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for marker in [
        "Pathological genogram",
        "Patient document operating system",
        "Treatment and consultation continuity",
        "Patient control, audit and spending safety",
        "scripts/smoke_test.py",
        "deployment\\run-local-secure.ps1",
        "Local · 0 llamadas",
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
        "scripts/smoke_test.py",
    ]
    for relative in required:
        assert (ROOT / relative).is_file(), relative


def test_demo_script_preserves_truth_boundary():
    script = (ROOT / "docs" / "DEMO_SCRIPT.md").read_text(encoding="utf-8")
    for forbidden_claim in [
        "Do not claim:",
        "confirmed diagnosis",
        "prescription authority",
        "genetic prediction",
        "regulatory clearance",
    ]:
        assert forbidden_claim in script
