from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from healthia_one.clinical_planner import ROLE_DEFINITIONS, extract_known_clinical_facts
from healthia_one.clinical_tools import execute_on_demand_clinical_tools
from healthia_one.config import Settings
from healthia_one.language import current_requested_locale, language_instruction, resolve_response_locale
from healthia_one.models import AgentStep, PatientState


CLINICAL_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["clinical_consultation"]},
        "clinical_focus": {"type": "string", "maxLength": 120},
        "why_these_questions": {
            "type": "array",
            "items": {"type": "string", "maxLength": 160},
            "minItems": 1,
            "maxItems": 2,
        },
        "missing_information": {
            "type": "array",
            "items": {"type": "string", "maxLength": 120},
            "minItems": 1,
            "maxItems": 3,
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "maxLength": 48},
                    "prompt": {"type": "string", "maxLength": 220},
                    "options": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 90},
                        "minItems": 3,
                        "maxItems": 5,
                    },
                    "multiple": {"type": "boolean"},
                    "detail_placeholder": {"type": "string", "maxLength": 120},
                },
                "required": ["id", "prompt", "options", "multiple", "detail_placeholder"],
            },
            "minItems": 5,
            "maxItems": 5,
        },
    },
    "required": [
        "intent",
        "clinical_focus",
        "why_these_questions",
        "missing_information",
        "questions",
    ],
}


ADK_CLINICAL_INSTRUCTION = """
You are HealthIA's clinical coordinator running through Google Agent Development Kit (ADK).
You do not diagnose or prescribe. Execute the minimum clinical control path and produce five adaptive questions for the current case.

Execution contract:
1. Before answering, call inspect_clinical_baseline exactly once.
2. That tool jointly executes the two mandatory checks: interview and safety.
3. Never invent tool results. Use only the tool result and authorized context.
4. Do not request any other tool in this phase.
5. After the tool call, return only the final object that satisfies the JSON schema enforced by the runtime.

Memory and natural-language rules:
- Treat chief_complaint and previous_answers as accumulated clinical memory.
- Do not ask for a fact already answered unless there is a concrete contradiction.
- Facts explicitly stated in chief_complaint are already answered. If it says
  "dolor de cuello", do not ask where the pain is; ask only a meaningful
  discriminator such as radiation, trigger, limitation or warning sign.
- Each new question must resolve a case-specific uncertainty.
- Prefer a concrete discriminator over a generic template.
- If duration, intensity, medication, allergy, exposure, vital sign, or warning sign is known, treat it as known.
- Options must fit the specific question; do not reuse a fixed option list.

Clinical and concision rules:
- Use the current complaint, prior answers, and authorized context.
- Include one question about case-specific warning signs.
- Never confirm diagnoses or instruct the patient to start, stop, or change medication/doses.
- Do not turn family history into predictions.
- Return exactly five questions with three to five short options each.
- clinical_focus must be one short phrase; why_these_questions at most two short reasons; missing_information at most three short items.
- Do not return selected_specialists: the runtime derives that from tools that actually executed.
""".strip()


@dataclass(frozen=True)
class AdkClinicalPlan:
    payload: dict[str, Any]
    executed_roles: tuple[str, ...]
    tool_outputs: tuple[dict[str, Any], ...]
    event_count: int
    session_id: str


def _answer_payload(previous_answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for item in previous_answers[-12:]:
        if not isinstance(item, dict):
            continue
        clean.append(
            {
                "question_id": str(item.get("question_id") or "")[:64],
                "question_prompt": str(item.get("question_prompt") or "")[:220],
                "selected": [str(value)[:100] for value in (item.get("selected") or [])[:5]],
                "detail": str(item.get("detail") or "")[:300],
            }
        )
    return clean


class AdkClinicalRuntime:
    """Low-latency ADK coordinator over authorized PatientState."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        value = str(text or "").strip()
        if value.startswith("```"):
            value = value.replace("```json", "", 1).replace("```", "", 1).strip()
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            start = value.find("{")
            end = value.rfind("}")
            if start >= 0 and end > start:
                try:
                    payload = json.loads(value[start : end + 1])
                except json.JSONDecodeError as nested:
                    raise ValueError(
                        "Google ADK returned incomplete or invalid structured JSON "
                        f"(chars={len(value)}, pos={nested.pos}, error={nested.msg})"
                    ) from nested
            else:
                raise ValueError(
                    "Google ADK did not return a structured JSON object "
                    f"(chars={len(value)}, pos={exc.pos}, error={exc.msg})"
                ) from exc
        if not isinstance(payload, dict):
            raise ValueError("Google ADK did not return a structured JSON object")
        return payload

    async def plan_clinical(
        self,
        state: PatientState,
        *,
        chief_complaint: str,
        stage: int,
        previous_answers: list[dict[str, Any]],
        authorized_clinical_context: dict[str, Any],
    ) -> AdkClinicalPlan:
        from google.adk.agents import LlmAgent
        from google.adk.models import Gemini
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        response_locale = resolve_response_locale(
            chief_complaint,
            requested_locale=current_requested_locale(),
            profile_locale=state.profile.locale,
        )
        executed_roles: list[str] = []
        tool_outputs: list[dict[str, Any]] = []
        baseline_calls = 0

        def execute_role(role_id: str) -> dict[str, Any]:
            if role_id in executed_roles:
                existing = next(item for item in tool_outputs if item.get("role") == role_id)
                return existing["result"]
            definition = ROLE_DEFINITIONS[role_id]
            step = AgentStep(
                agent=definition[0],
                action=definition[1],
                reason=definition[2],
                status="completed",
            )
            output = execute_on_demand_clinical_tools(
                state,
                [step],
                chief_complaint=chief_complaint,
                previous_answers=previous_answers,
                stage=stage,
            )[0]
            executed_roles.append(role_id)
            public_output = {
                "role": role_id,
                "tool": output["tool"],
                "status": output["status"],
                "result": output["result"],
            }
            tool_outputs.append(public_output)
            return public_output["result"]

        def inspect_clinical_baseline() -> dict[str, Any]:
            """Call exactly once before answering; runs interview and safety checks together."""
            nonlocal baseline_calls
            baseline_calls += 1
            return {
                "interview": execute_role("interview"),
                "safety": execute_role("safety"),
                "stage": stage,
                "previous_answer_count": len(previous_answers),
            }

        max_output_tokens = self.settings.ai_max_output_tokens
        instruction = f"{ADK_CLINICAL_INSTRUCTION}\n\n{language_instruction(response_locale)}"
        agent = LlmAgent(
            name="healthia_runtime_coordinator",
            model=Gemini(
                model=self.settings.model,
                retry_options=types.HttpRetryOptions(attempts=2),
            ),
            description="Low-latency demand-driven HealthIA coordinator over the current authorized patient state.",
            instruction=instruction,
            tools=[inspect_clinical_baseline],
            generate_content_config=types.GenerateContentConfig(
                max_output_tokens=max_output_tokens,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                response_mime_type="application/json",
                response_json_schema=CLINICAL_PLAN_JSON_SCHEMA,
            ),
        )

        session_service = InMemorySessionService()
        app_name = "healthia_runtime"
        user_id = state.profile.id or "patient"
        session_id = f"adk_{uuid.uuid4().hex}"
        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
        prompt = {
            "task": "generate_next_adaptive_clinical_question_block",
            "stage": stage,
            "chief_complaint": chief_complaint,
            "previous_answers": _answer_payload(previous_answers),
            "known_facts": extract_known_clinical_facts(chief_complaint, previous_answers),
            "authorized_clinical_context": authorized_clinical_context,
            "response_locale": response_locale,
            "constraints": {
                "exact_question_count": 5,
                "question_options_min": 3,
                "question_options_max": 5,
                "must_execute_tool": "inspect_clinical_baseline",
                "maximum_adk_function_calls": 1,
                "mandatory_roles_inside_tool": ["interview", "safety"],
                "structured_output_required": True,
                "must_not_repeat_known_answers": True,
                "must_not_repeat_explicit_chief_complaint_facts": True,
                "must_not_diagnose_or_prescribe": True,
                "patient_visible_language": response_locale,
            },
        }

        event_count = 0

        async def run_turn(text: str) -> str:
            nonlocal event_count
            message = types.Content(role="user", parts=[types.Part(text=text)])
            final_text = ""
            last_text = ""
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):
                event_count += 1
                content = getattr(event, "content", None)
                text_parts = [
                    str(getattr(part, "text", "") or "")
                    for part in (getattr(content, "parts", None) or [])
                    if getattr(part, "text", None) and not getattr(part, "thought", False)
                ]
                if text_parts:
                    last_text = "".join(text_parts).strip()
                is_final = getattr(event, "is_final_response", None)
                if callable(is_final) and is_final() and text_parts:
                    final_text = "".join(text_parts).strip()
            return final_text or last_text

        final_text = await run_turn(json.dumps(prompt, ensure_ascii=False, default=str))

        mandatory = ("interview", "safety")
        missing = [role for role in mandatory if role not in executed_roles]
        if missing or baseline_calls != 1:
            correction = {
                "task": "repair_missing_mandatory_tool_execution",
                "response_locale": response_locale,
                "instruction": (
                    "Call inspect_clinical_baseline exactly once, then return the final object that satisfies the configured JSON schema. "
                    "Do not call the tool more than once. " + language_instruction(response_locale)
                ),
            }
            repaired_text = await run_turn(json.dumps(correction, ensure_ascii=False, default=str))
            if repaired_text:
                final_text = repaired_text

        missing = [role for role in mandatory if role not in executed_roles]
        if missing:
            raise ValueError("ADK did not execute mandatory checks: " + ", ".join(missing))
        if baseline_calls != 1:
            raise ValueError(f"ADK executed inspect_clinical_baseline {baseline_calls} times; exactly one is required")
        if tuple(executed_roles) != mandatory:
            raise ValueError(f"ADK executed unexpected roles in the low-latency block: {executed_roles}")
        if not final_text:
            raise RuntimeError("Google ADK returned an empty clinical response")

        payload = self._parse_json(final_text)
        payload.setdefault("why_these_questions", [])
        payload.setdefault("missing_information", [])
        payload["response_locale"] = response_locale
        payload["selected_specialists"] = [
            {
                "role": role,
                "reason": f"{ROLE_DEFINITIONS[role][0]} check executed inside inspect_clinical_baseline by Google ADK",
            }
            for role in executed_roles
        ]
        payload["adk_execution"] = {
            "runtime": "google_adk_runner",
            "session_id": session_id,
            "event_count": event_count,
            "function_tool": "inspect_clinical_baseline",
            "function_call_count": baseline_calls,
            "thinking_level": "minimal",
            "max_output_tokens": max_output_tokens,
            "structured_output": True,
            "response_mime_type": "application/json",
            "response_locale": response_locale,
            "executed_roles": list(executed_roles),
            "tool_outputs": tool_outputs,
        }
        return AdkClinicalPlan(
            payload=payload,
            executed_roles=tuple(executed_roles),
            tool_outputs=tuple(tool_outputs),
            event_count=event_count,
            session_id=session_id,
        )
