from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCORECARD = ROOT / "hackathon" / "judge_omega_scorecard.json"
EXPECTED_RUBRIC = {
    "innovation_operational_utility": 40,
    "architectural_discipline_tech_stack": 30,
    "demo_production_readiness": 30,
}
VALID_STATUSES = {"proven", "partial", "missing"}


class JudgeOmegaError(RuntimeError):
    pass


def load_scorecard(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise JudgeOmegaError(f"Scorecard not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise JudgeOmegaError(f"Invalid scorecard JSON: {exc}") from exc


def validate_evidence(items: list[dict[str, Any]], context: str) -> None:
    for item in items:
        kind = item.get("kind")
        value = str(item.get("value", "")).strip()
        if kind != "repo_path":
            raise JudgeOmegaError(f"{context}: unsupported evidence kind {kind!r}")
        if not value:
            raise JudgeOmegaError(f"{context}: empty evidence path")
        if not (ROOT / value).exists():
            raise JudgeOmegaError(f"{context}: evidence path does not exist: {value}")


def validate_scorecard(scorecard: dict[str, Any]) -> None:
    if scorecard.get("official_rubric") != EXPECTED_RUBRIC:
        raise JudgeOmegaError(
            "Official rubric changed or was diluted. Expected exact 40/30/30 weights."
        )

    criteria = scorecard.get("criteria") or []
    if {item.get("id") for item in criteria} != set(EXPECTED_RUBRIC):
        raise JudgeOmegaError("Criteria must match the three official judging categories exactly.")

    max_total = 0
    awarded_total = 0
    for item in criteria:
        criterion_id = item["id"]
        maximum = int(item.get("max_points", -1))
        awarded = int(item.get("awarded_points", -1))
        if maximum != EXPECTED_RUBRIC[criterion_id]:
            raise JudgeOmegaError(f"{criterion_id}: maximum does not match official rubric")
        if awarded < 0 or awarded > maximum:
            raise JudgeOmegaError(f"{criterion_id}: awarded points outside valid range")
        evidence = item.get("evidence") or []
        if awarded > 0 and not evidence:
            raise JudgeOmegaError(f"{criterion_id}: points require repository evidence")
        validate_evidence(evidence, criterion_id)
        max_total += maximum
        awarded_total += awarded

    if max_total != 100:
        raise JudgeOmegaError(f"Rubric maximum must equal 100, found {max_total}")
    if awarded_total > 100:
        raise JudgeOmegaError("Awarded score cannot exceed 100")

    for gate in scorecard.get("hard_gates") or []:
        gate_id = str(gate.get("id", "unnamed_gate"))
        status = gate.get("status")
        if status not in VALID_STATUSES:
            raise JudgeOmegaError(f"{gate_id}: invalid status {status!r}")
        evidence = gate.get("evidence") or []
        if status in {"proven", "partial"} and not evidence:
            raise JudgeOmegaError(f"{gate_id}: {status} claims require evidence")
        validate_evidence(evidence, gate_id)


def verdict_for(score: int, unresolved_hard_gates: int) -> str:
    if unresolved_hard_gates:
        if score >= 85:
            return "HIGH_SCORE_BUT_BLOCKED"
        return "NOT_SUBMISSION_READY"
    if score >= 93:
        return "SUBMISSION_LOCKED"
    if score >= 85:
        return "WINNING_CANDIDATE"
    if score >= 75:
        return "FINALIST_CANDIDATE"
    if score >= 60:
        return "CREDIBLE_BUT_NOT_DIFFERENTIATED"
    return "NOT_COMPETITIVE"


def evaluate(scorecard: dict[str, Any]) -> dict[str, Any]:
    validate_scorecard(scorecard)
    score = sum(int(item["awarded_points"]) for item in scorecard["criteria"])
    hard_gate_blockers = [
        gate
        for gate in scorecard.get("hard_gates", [])
        if gate.get("blocker_if_not_proven") and gate.get("status") != "proven"
    ]
    return {
        "score": score,
        "target_score": int(scorecard.get("target_score", 90)),
        "verdict": verdict_for(score, len(hard_gate_blockers)),
        "primary_track": scorecard.get("primary_track"),
        "criteria": scorecard["criteria"],
        "hard_gate_blockers": hard_gate_blockers,
        "critical_blockers": scorecard.get("critical_blockers", []),
        "next_actions": scorecard.get("next_actions", [])[:3],
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# JUDGE Ω — Hackathon score",
        "",
        f"**Score:** {result['score']}/100",
        f"**Target:** {result['target_score']}/100",
        f"**Verdict:** `{result['verdict']}`",
        f"**Primary track:** {result['primary_track']}",
        "",
        "## Weighted criteria",
    ]
    for item in result["criteria"]:
        lines.append(
            f"- **{item['label']}: {item['awarded_points']}/{item['max_points']}** — {item['reason']}"
        )

    lines.extend(["", "## Hard-gate blockers"])
    if result["hard_gate_blockers"]:
        for gate in result["hard_gate_blockers"]:
            lines.append(f"- `{gate['status']}` — {gate['label']}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Critical blockers"])
    for blocker in result["critical_blockers"]:
        lines.append(f"- **{blocker['statement']}** Evidence required: {blocker['evidence_needed']}")

    lines.extend(["", "## Highest-value next actions"])
    for action in result["next_actions"]:
        lines.append(f"- {action}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate HealthIA against the hackathon judging rubric.")
    parser.add_argument("--scorecard", type=Path, default=DEFAULT_SCORECARD)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail while any hard gate is not proven or the target score is not reached.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = evaluate(load_scorecard(args.scorecard))
    except JudgeOmegaError as exc:
        print(f"JUDGE_OMEGA_INVALID: {exc}")
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))

    if args.strict and (
        result["hard_gate_blockers"] or result["score"] < result["target_score"]
    ):
        return 3
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
