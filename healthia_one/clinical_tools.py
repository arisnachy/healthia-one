from __future__ import annotations

from typing import Any, Iterable

from healthia_one.models import AgentStep, PatientState
from healthia_one.safety import assess_text


def _answer_text(previous_answers: Iterable[dict[str, Any]] | None) -> str:
    values: list[str] = []
    for answer in previous_answers or []:
        if not isinstance(answer, dict):
            continue
        values.extend(str(item) for item in answer.get("selected", []) if str(item).strip())
        detail = str(answer.get("detail", "")).strip()
        if detail:
            values.append(detail)
    return " ".join(values)


def _active_medications(state: PatientState) -> list[dict[str, str]]:
    return [
        {
            "name": item.name,
            "strength": item.strength,
            "schedule": item.schedule,
            "verification_status": item.verification_status,
        }
        for item in state.medication_plans
        if item.active
    ][:6]


def execute_on_demand_clinical_tools(
    state: PatientState,
    agent_plan: list[AgentStep],
    *,
    chief_complaint: str,
    previous_answers: Iterable[dict[str, Any]] | None,
    stage: int,
) -> list[dict[str, Any]]:
    """Run only the deterministic tools represented in the selected plan."""

    answer_text = _answer_text(previous_answers)
    combined_text = " ".join(part for part in (chief_complaint, answer_text) if part).strip()
    outputs: list[dict[str, Any]] = []

    for step in agent_plan:
        agent = step.agent
        result: dict[str, Any]

        if agent == "INTERVIEWER":
            result = {
                "chief_complaint": chief_complaint,
                "stage": stage,
                "answered_items": len(list(previous_answers or [])),
                "task": "identify the next highest-value missing information",
            }
        elif agent == "SENTINEL":
            decision = assess_text(combined_text)
            result = {
                "risk_level": decision.level.value,
                "must_stop_normal_flow": decision.must_stop_normal_flow,
                "public_direction": decision.message,
            }
        elif agent == "HISTORIA":
            result = {
                "confirmed_conditions": state.profile.confirmed_conditions[:6],
                "chronic_history": state.profile.personal_history.chronic_conditions[:6],
                "recent_vital_count": len(state.vitals[-5:]),
            }
        elif agent == "MEDSAFE":
            result = {
                "active_medications": _active_medications(state),
                "allergies": state.profile.allergies[:6],
                "boundary": "organize safety context only; do not change treatment",
            }
        elif agent == "ARCHIVUM":
            result = {
                "documents": [
                    {
                        "category": item.category.value,
                        "title": item.title,
                        "status": item.status,
                    }
                    for item in state.documents[-5:]
                ],
                "unread_content_policy": "do not invent content that has not been parsed",
            }
        elif agent == "LUMEN":
            result = {
                "results": [
                    {"panel": item.panel, "status": item.status, "explained": item.explained}
                    for item in state.results[-5:]
                ],
                "boundary": "explain meaning and limits; do not confirm diagnosis",
            }
        elif agent == "HEREDITAS":
            result = {
                "family_patterns": [
                    {
                        "relation": member.relation,
                        "conditions": [condition.name for condition in member.conditions],
                    }
                    for member in state.family_members[-8:]
                    if member.conditions
                ],
                "boundary": "aggregation is not prediction",
            }
        elif agent == "NAVIGATOR":
            result = {
                "stage": stage,
                "next_action": "complete current adaptive block" if stage == 1 else "prepare human-safe direction and closure condition",
                "active_mission_count": len([item for item in state.missions if item.status.value not in {"completed", "cancelled"}]),
            }
        elif agent == "BASTION":
            result = {
                "authorized_signals": state.consent.signal_types,
                "quiet_hours": f"{state.consent.quiet_hours_start}-{state.consent.quiet_hours_end}",
                "proactive_enabled": state.consent.proactive_enabled,
            }
        else:
            result = {"status": "unsupported_specialist"}

        outputs.append(
            {
                "area": step.reason,
                "tool": agent,
                "status": "completed",
                "result": result,
            }
        )

    return outputs
