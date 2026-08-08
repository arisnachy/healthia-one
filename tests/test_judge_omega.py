from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "judge_omega.py"
SCORECARD = ROOT / "hackathon" / "judge_omega_scorecard.json"
CURRENT_EVIDENCE_SCORE = 100


def test_judge_omega_preserves_official_weights_and_current_baseline() -> None:
    payload = json.loads(SCORECARD.read_text(encoding="utf-8"))
    assert payload["official_rubric"] == {
        "innovation_operational_utility": 40,
        "architectural_discipline_tech_stack": 30,
        "demo_production_readiness": 30,
    }
    assert sum(item["max_points"] for item in payload["criteria"]) == 100
    assert sum(item["awarded_points"] for item in payload["criteria"]) == CURRENT_EVIDENCE_SCORE
    gates = {item["id"]: item["status"] for item in payload["hard_gates"]}
    assert gates["closed_loop_taskmaster"] == "proven"
    assert gates["cloud_runtime_proof"] == "proven"
    assert gates["cross_revision_continuity"] == "proven"
    assert gates["four_minute_demo"] == "proven"
    assert gates["final_submission_video_url"] == "proven"
    assert all(status == "proven" for status in gates.values())
    assert payload["critical_blockers"] == []


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
    assert result["verdict"] == "SUBMISSION_LOCKED"
    assert result["hard_gate_blockers"] == []
    assert result["critical_blockers"] == []
    assert len(result["next_actions"]) == 3


def test_judge_omega_strict_mode_accepts_fully_proven_submission() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--strict"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "100/100" in completed.stdout
    assert "SUBMISSION_LOCKED" in completed.stdout
