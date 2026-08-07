from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "judge_omega.py"
SCORECARD = ROOT / "hackathon" / "judge_omega_scorecard.json"
CURRENT_EVIDENCE_SCORE = 76


def test_judge_omega_preserves_official_weights_and_current_baseline() -> None:
    payload = json.loads(SCORECARD.read_text(encoding="utf-8"))
    assert payload["official_rubric"] == {
        "innovation_operational_utility": 40,
        "architectural_discipline_tech_stack": 30,
        "demo_production_readiness": 30,
    }
    assert sum(item["max_points"] for item in payload["criteria"]) == 100
    assert sum(item["awarded_points"] for item in payload["criteria"]) == CURRENT_EVIDENCE_SCORE
    assert any(item["status"] != "proven" for item in payload["hard_gates"])


def test_judge_omega_evaluator_validates_repository_evidence() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["score"] == CURRENT_EVIDENCE_SCORE
    assert result["verdict"] == "NOT_SUBMISSION_READY"
    assert result["hard_gate_blockers"]
    assert any(item["id"] == "cloud_runtime_proof" for item in result["hard_gate_blockers"])
    assert len(result["next_actions"]) == 3


def test_judge_omega_strict_mode_blocks_premature_submission() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--strict"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 3
    assert "NOT_SUBMISSION_READY" in completed.stdout
