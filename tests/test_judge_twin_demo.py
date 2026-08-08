from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_living_twin_judge_rehearsal_is_zero_spend_and_closed() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/judge_twin_demo.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["status"] == "PASS"
    assert result["provider_requests"] == 0
    assert all(result["proof"].values())
    assert "Local zero-spend rehearsal" in result["truth_boundary"]
