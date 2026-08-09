from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from healthia_one.conversation_brain import ACTION_HINTS, build_frame
from healthia_one.models import ChatMessage, HealthMission, MissionStatus, PatientState, VitalRecord

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "dialogbench"


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    locale: str
    prior_target: str
    prior_mission: str
    patient_text: str


TOPICS = (
    ("results", "result_explanation"),
    ("measurements", "blood_pressure"),
    ("treatment", "medication_management"),
    ("appointments", "consultation_preparation"),
    ("timeline", "timeline_review"),
    ("family", "family_history"),
    ("documents", "document_management"),
    ("clinical_interview", "clinical_interview"),
)

ES_FOLLOWUPS = (
    ("pronoun", "¿Y eso qué significa?"),
    ("severity", "¿Y eso es grave?"),
    ("continuation", "¿Y entonces qué hago?"),
    ("why", "¿Por qué dices eso?"),
    ("yesterday", "¿Y lo de ayer?"),
    ("ordinal", "La segunda."),
    ("ellipsis", "¿Y mañana?"),
    ("correction", "No, me refería a eso."),
    ("typo", "y eso q signifika?"),
)

EN_FOLLOWUPS = (
    ("pronoun", "What does that mean?"),
    ("severity", "Is that serious?"),
    ("continuation", "So what do I do now?"),
    ("why", "Why are you saying that?"),
    ("yesterday", "What about the one from yesterday?"),
    ("ordinal", "The second one."),
    ("ellipsis", "And tomorrow?"),
    ("correction", "No, I meant that."),
    # This deliberately contains an explicit current topic plus a pronoun. It
    # proves that "result" wins over stale context instead of being overwritten
    # by the previous action target.
    ("spanglish", "Y that result, is it bad?"),
)


def scenarios() -> list[Scenario]:
    values: list[Scenario] = []
    for target, mission in TOPICS:
        for category, text in ES_FOLLOWUPS:
            values.append(Scenario(
                id=f"es-{target}-{category}", category=category, locale="es",
                prior_target=target, prior_mission=mission, patient_text=text,
            ))
        for category, text in EN_FOLLOWUPS:
            values.append(Scenario(
                id=f"en-{target}-{category}", category=category, locale="en",
                prior_target=target, prior_mission=mission, patient_text=text,
            ))
    return values


def state_for(scenario: Scenario) -> PatientState:
    state = PatientState()
    mission = HealthMission(
        title="DialogBench prior mission",
        mission_type=scenario.prior_mission,
        status=MissionStatus.WAITING_PATIENT,
        next_action="Continue the prior thread",
    )
    state.missions.append(mission)
    state.messages.extend([
        ChatMessage(role="patient", author="Patient", content="I want to review something from my health record."),
        ChatMessage(
            role="assistant",
            author="HealthIA",
            content="I found the relevant information and kept the thread open for your follow-up.",
            mission_id=mission.id,
            metadata={"action_target": scenario.prior_target, "mission_type": scenario.prior_mission},
        ),
    ])
    if scenario.prior_mission == "blood_pressure":
        state.vitals.append(VitalRecord(systolic=138, diastolic=88, pulse=72))
    return state


def evaluate(scenario: Scenario) -> dict:
    state = state_for(scenario)
    frame = build_frame(state, scenario.patient_text)
    routing_lower = frame.routing_text.lower()
    canonical_hint = ACTION_HINTS[scenario.prior_target].lower()
    if scenario.category == "spanglish":
        # The current turn explicitly names a result. Even though "that"/"it"
        # makes the sentence referential, the old topic must not be injected.
        resolved = (
            frame.ambiguous_reference
            and "result" in scenario.patient_text.lower()
            and "contextual_routing_hint:" not in routing_lower
            and frame.last_action_target == scenario.prior_target
        )
    else:
        resolved = (
            frame.ambiguous_reference
            and "contextual_routing_hint:" in routing_lower
            and canonical_hint in routing_lower
            and frame.last_action_target == scenario.prior_target
        )
    preserves_user_words = frame.routing_text.startswith(scenario.patient_text)
    bounded_memory = len(frame.recent_turns) <= 12 and sum(len(item["content"]) for item in frame.recent_turns) <= 6000
    return {
        "id": scenario.id,
        "category": scenario.category,
        "locale": scenario.locale,
        "resolved": resolved,
        "preserves_user_words": preserves_user_words,
        "bounded_memory": bounded_memory,
    }


def run() -> dict:
    cases = scenarios()
    results = [evaluate(case) for case in cases]
    passed = [item for item in results if item["resolved"] and item["preserves_user_words"] and item["bounded_memory"]]
    score = len(passed) / len(results) if results else 0.0
    report = {
        "status": "PASS" if len(cases) >= 120 and score >= 0.98 else "FAIL",
        "dialogue_count": len(cases),
        "pass_count": len(passed),
        "score": round(score, 4),
        "gate": {"minimum_dialogues": 120, "minimum_score": 0.98},
        "categories": sorted({item["category"] for item in results}),
        "locales": sorted({item["locale"] for item in results}),
        "failures": [item for item in results if item not in passed][:30],
        "claim_boundary": (
            "This deterministic gate proves bounded context/reference continuity plus explicit-current-topic precedence, "
            "not perfect human conversation. Live-model naturalness remains a separate submission gate."
        ),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)
