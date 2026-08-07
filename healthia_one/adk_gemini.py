from __future__ import annotations

import asyncio
from typing import Any, Callable

from healthia_one.adk_runtime import AdkClinicalRuntime
from healthia_one.config import Settings
from healthia_one.control import audit
from healthia_one.gemini import GeminiResponder
from healthia_one.models import PatientState


class AdkGeminiResponder(GeminiResponder):
    """Gemini patient boundary whose clinical planner is executed by Google ADK.

    The parent class keeps deterministic safety, cost guard, question
    normalization, Judge Ω and patient-facing enhancement. Only the model call
    that creates an adaptive clinical block is replaced: an ADK Runner chooses
    and executes the minimum current-state tools, then returns the same JSON
    contract expected by the proven pipeline.
    """

    def __init__(self, settings: Settings, client_factory: Callable[[], Any] | None = None) -> None:
        super().__init__(settings, client_factory=client_factory)
        self.adk_runtime = AdkClinicalRuntime(settings)

    def _generate_clinical_block(
        self,
        state: PatientState,
        *,
        chief_complaint: str,
        stage: int,
        previous_answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # The parent executes this sync hook inside asyncio.to_thread(), so ADK
        # receives its own event loop and does not block FastAPI's main loop.
        plan = asyncio.run(
            self.adk_runtime.plan_clinical(
                state,
                chief_complaint=chief_complaint,
                stage=stage,
                previous_answers=previous_answers,
                authorized_clinical_context=self.compact_clinical_context(state),
            )
        )
        public_tool_outputs = list(plan.tool_outputs)
        audit(
            state,
            actor="google_adk",
            action="execute_demand_driven_clinical_plan",
            resource_type="agent_runtime",
            resource_id=plan.session_id,
            details={
                "model": self.settings.model,
                "stage": stage,
                "executed_roles": list(plan.executed_roles),
                "event_count": plan.event_count,
                "tool_outputs": public_tool_outputs,
            },
        )
        payload = dict(plan.payload)
        payload["adk_execution"] = {
            "runtime": "google_adk_runner",
            "session_id": plan.session_id,
            "event_count": plan.event_count,
            "executed_roles": list(plan.executed_roles),
            "tool_outputs": public_tool_outputs,
        }
        return payload
