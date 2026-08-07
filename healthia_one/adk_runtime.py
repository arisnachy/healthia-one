from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from healthia_one.config import Settings
from healthia_one.cost_guard import CostGuard, CostGuardBlocked
from healthia_one.mission_engine import MissionDecision, deterministic_decision, validate_adk_decision
from healthia_one.models import AgenticEvent, PatientState


@dataclass
class RuntimeDecisionReport:
    decision: MissionDecision
    runtime: str
    model: str = ""
    provider_requests_reserved: int = 0
    trace: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


def _compact_event_context(state: PatientState, event: AgenticEvent, oracle: MissionDecision) -> dict[str, Any]:
    active_missions = [
        {
            "id": item.id,
            "mission_type": item.mission_type,
            "status": item.status.value,
            "risk_level": item.risk_level.value,
            "next_action": item.next_action,
            "evidence_ids": item.evidence_ids[-4:],
        }
        for item in state.missions
        if item.status.value not in {"completed", "cancelled"}
    ][-4:]
    latest_vitals = [
        {
            "id": item.id,
            "systolic": item.systolic,
            "diastolic": item.diastolic,
            "pulse": item.pulse,
            "oxygen_saturation": item.oxygen_saturation,
            "symptoms": item.symptoms[:5],
            "measured_at": item.measured_at.isoformat(),
        }
        for item in state.vitals[-3:]
    ]
    appointments = [
        {
            "id": item.id,
            "title": item.title,
            "scheduled_at": item.scheduled_at.isoformat(),
            "status": item.status,
        }
        for item in state.appointments[-3:]
    ]
    return {
        "event": event.model_dump(mode="json"),
        "deterministic_safety_floor": oracle.as_dict(),
        "active_missions": active_missions,
        "latest_vitals": latest_vitals,
        "upcoming_appointments": appointments,
        "consent": {
            "proactive_enabled": state.consent.proactive_enabled,
            "authorized_signal_types": state.consent.signal_types,
        },
        "truth_boundary": (
            "Choose one bounded operational action only. Do not diagnose, prescribe, change medication, "
            "or downgrade deterministic safety."
        ),
    }


def _extract_parts(event: Any) -> list[Any]:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    return list(parts or [])


def _function_args(call: Any) -> dict[str, Any]:
    args = getattr(call, "args", None)
    if isinstance(args, dict):
        return dict(args)
    if hasattr(args, "items"):
        return dict(args.items())
    return {}


class AdkMissionRuntime:
    """Demand-driven Google ADK coordinator for durable background missions.

    Zero-spend local and CI paths do not instantiate ADK. In cloud/demo mode a
    single actionable event atomically reserves the two-call worst-case budget and
    executes a bounded ADK run with ``max_llm_calls=2``. The resulting action is always
    validated against the deterministic safety oracle before it can mutate state.
    """

    def __init__(self, settings: Settings, cost_guard: CostGuard) -> None:
        self.settings = settings
        self.cost_guard = cost_guard

    @property
    def enabled(self) -> bool:
        return self.settings.mission_runtime == "adk" and self.settings.adk_ready

    async def decide(self, state: PatientState, event: AgenticEvent) -> RuntimeDecisionReport:
        oracle = deterministic_decision(state, event)
        base_trace = [
            {
                "stage": "decision",
                "actor": "deterministic_safety_oracle",
                "action": oracle.action,
                "details": oracle.as_dict(),
            }
        ]
        # No model request for events that have no useful work. This is the main
        # token-saving boundary for background operation.
        if oracle.action == "no_action":
            return RuntimeDecisionReport(
                decision=oracle,
                runtime="deterministic_fallback",
                trace=base_trace,
            )
        if not self.enabled:
            return RuntimeDecisionReport(
                decision=oracle,
                runtime="deterministic_fallback",
                trace=base_trace,
                error="ADK runtime disabled or Google credentials unavailable",
            )

        try:
            first_reserved, last_reserved = self.cost_guard.authorize_many(
                "adk_background_mission_decision", 2
            )
        except CostGuardBlocked as exc:
            return RuntimeDecisionReport(
                decision=oracle,
                runtime="deterministic_fallback",
                trace=base_trace,
                error=str(exc),
            )

        context = _compact_event_context(state, event, oracle)
        prompt = "AGENTIC_EVENT\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        trace = list(base_trace)
        trace.append(
            {
                "stage": "decision",
                "actor": "cost_guard",
                "action": "reserve_model_call_budget",
                "details": {
                    "reserved_calls": 2,
                    "reservation_range": [first_reserved, last_reserved],
                    "max_llm_calls": 2,
                },
            }
        )
        candidate: dict[str, Any] | None = None
        final_text = ""
        try:
            from google.adk.agents.run_config import RunConfig
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.genai import types
            from healthia_agent.agent import root_agent

            session_service = InMemorySessionService()
            session_id = f"mission-{event.id}"
            await session_service.create_session(
                app_name="healthia_agent",
                user_id=event.patient_id,
                session_id=session_id,
            )
            runner = Runner(
                app_name="healthia_agent",
                agent=root_agent,
                session_service=session_service,
            )
            message = types.Content(role="user", parts=[types.Part(text=prompt)])
            run_config = RunConfig(max_llm_calls=2)
            async for adk_event in runner.run_async(
                user_id=event.patient_id,
                session_id=session_id,
                new_message=message,
                run_config=run_config,
            ):
                author = str(getattr(adk_event, "author", "adk"))
                for part in _extract_parts(adk_event):
                    call = getattr(part, "function_call", None)
                    if call is not None:
                        name = str(getattr(call, "name", ""))
                        args = _function_args(call)
                        trace.append(
                            {
                                "stage": "tool",
                                "actor": author,
                                "action": name,
                                "details": {"args": args},
                            }
                        )
                        if name == "commit_mission_action":
                            candidate = args
                    response = getattr(part, "function_response", None)
                    if response is not None:
                        trace.append(
                            {
                                "stage": "tool",
                                "actor": author,
                                "action": str(getattr(response, "name", "tool_response")),
                                "details": {"response_observed": True},
                            }
                        )
                    text = getattr(part, "text", None)
                    if isinstance(text, str) and text.strip():
                        final_text = text.strip()
            selected = validate_adk_decision(state, event, candidate)
            trace.append(
                {
                    "stage": "decision",
                    "actor": "adk_guard",
                    "action": selected.action,
                    "details": {
                        "candidate": candidate or {},
                        "final_text_present": bool(final_text),
                        "safety_validated": True,
                    },
                }
            )
            return RuntimeDecisionReport(
                decision=selected,
                runtime="google_adk",
                model=self.settings.model,
                provider_requests_reserved=2,
                trace=trace,
            )
        except Exception as exc:
            trace.append(
                {
                    "stage": "error",
                    "actor": "google_adk",
                    "action": "fallback_to_deterministic_oracle",
                    "details": {"type": type(exc).__name__, "message": str(exc)[:300]},
                }
            )
            return RuntimeDecisionReport(
                decision=oracle,
                runtime="deterministic_fallback",
                model=self.settings.model,
                provider_requests_reserved=2,
                trace=trace,
                error=f"{type(exc).__name__}: {str(exc)[:300]}",
            )
