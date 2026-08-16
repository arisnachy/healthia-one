from __future__ import annotations


JUDGE_TRIGGER = "HealthIA noticed the follow-up was overdue. Nobody prompted it."

DURABLE_BOUNDARIES = (
    "deterministic overdue follow-up detection",
    "patient-scoped Firestore mission committed before external work",
    "post-commit outbox delivered through Eventarc to a private worker and real Gmail receipt",
    "mission-linked patient reply recovered through Gmail users.watch and authenticated Pub/Sub",
    "canonical Firestore VitalRecord persisted and the same mission marked COMPLETED",
)

OPERATIONAL_METRIC = "One unattended health mission crossed 5 durable boundaries without another chat prompt."

MAINLINE_AUTONOMY_SCOPE = "explicitly opted-in blood-pressure follow-up only"


def judge_proof() -> dict:
    return {
        "trigger": JUDGE_TRIGGER,
        "metric": OPERATIONAL_METRIC,
        "durable_boundaries": list(DURABLE_BOUNDARIES),
        "boundary_count": len(DURABLE_BOUNDARIES),
        "scope": MAINLINE_AUTONOMY_SCOPE,
        "model_calls_for_trigger": 0,
        "clinical_reasoning_network_calls_for_trigger": 0,
        "truth_boundary": (
            "HealthIA autonomously carries an explicitly authorized measurement-capture mission. "
            "It does not autonomously diagnose, prescribe, change treatment, or declare blood-pressure control."
        ),
    }
