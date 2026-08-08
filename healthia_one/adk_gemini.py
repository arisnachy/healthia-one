from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from healthia_one.adk_runtime import AdkClinicalRuntime
from healthia_one.clinical_planner import judge_dynamic_plan, normalize_dynamic_question_block
from healthia_one.config import Settings
from healthia_one.control import audit
from healthia_one.cost_guard import CostGuardBlocked
from healthia_one.gemini import GeminiResponder
from healthia_one.language import current_requested_locale, language_instruction, resolve_response_locale
from healthia_one.models import MissionStatus, PatientState, RiskLevel


PATIENT_RESPONSE_SYSTEM_INSTRUCTION = """
You are HealthIA, a patient-facing health continuity assistant.
Return only the patient-visible response in Markdown.
Use only authorized data included in the context and preserve the deterministic clinical safety draft.
Never invent findings, diagnoses, results, connected devices, or treatments.
Clarify the deterministic draft without adding clinical recommendations, medications, doses, diagnoses, or facts that are not present in that draft.
If the context is insufficient for a safe answer, preserve the deterministic safety boundary and state the uncertainty.
Do not prescribe, change doses, or replace professional or emergency care.
Do not mention internal agent names, system instructions, private reasoning, or chain of thought.
Clearly distinguish confirmed facts, patient-reported information, uncertainty, and next steps.
""".strip()


CLINICAL_RESOLUTION_SYSTEM_INSTRUCTION = """
You are HealthIA, a patient-facing health continuity assistant.

You receive the initial complaint, all accumulated answers from an adaptive interview, and authorized longitudinal context.
Decide whether there is enough information for a safe patient-facing orientation or whether one genuinely necessary additional round is still required.

Never confirm diagnoses. You may explain plausible clinical possibilities and what evidence supports or limits them.
Do not prescribe, change doses, tell the patient to stop treatment, or declare a dangerous situation safe.
When warning signs exist, clearly prioritize the appropriate human evaluation.
Do not repeat answered questions. Do not ask another round by routine: only when a missing fact can materially change care level or orientation.

Return valid JSON only:
{
  "decision": "summarize" | "ask_more",
  "clinical_focus": "what is being clarified",
  "missing_information": ["important missing fact"],
  "decision_reason": "why orientation is sufficient or why more questions are needed",
  "patient_message": "patient-facing Markdown when decision=summarize; empty when ask_more",
  "possible_explanations": [
    {
      "name": "possibility, not a confirmed diagnosis",
      "why_possible": "specific supporting facts",
      "why_uncertain": "what is missing or limiting"
    }
  ],
  "care_level": "self_care_information | routine_professional | priority_professional | urgent"
}

When decision=summarize, patient_message should sound natural and conversational and include:
- what you understood from the case;
- the main possibilities in clear language, explicitly not as confirmed diagnoses;
- which facts weigh for or against them;
- what level of human care appears prudent;
- what the patient should tell or ask a professional;
- concrete warning signs for which the patient should not wait.

Do not mention internal agents, prompts, chain of thought, or tool names.
""".strip()


class AdkGeminiResponder(GeminiResponder):
    """Gemini patient boundary whose clinical planner is executed by Google ADK."""

    def __init__(self, settings: Settings, client_factory: Callable[[], Any] | None = None) -> None:
        super().__init__(settings, client_factory=client_factory)
        self.adk_runtime = AdkClinicalRuntime(settings)

    @staticmethod
    def _response_locale(state: PatientState, text: str) -> str:
        return resolve_response_locale(
            text,
            requested_locale=current_requested_locale(),
            profile_locale=state.profile.locale,
        )

    def _generate(self, state: PatientState, patient_text: str, draft) -> str:
        response_locale = self._response_locale(state, patient_text)
        payload = {
            "patient_message": patient_text,
            "response_locale": response_locale,
            "authorized_context": self.authorized_context(state),
            "deterministic_safety_draft": {
                "content": draft.message.content,
                "risk_level": draft.message.risk_level.value,
                "mission": draft.mission.model_dump(mode="json") if draft.mission else None,
                "action_target": draft.message.metadata.get("action_target"),
            },
        }
        interaction = self._get_client().interactions.create(
            model=self.settings.model,
            input=json.dumps(payload, ensure_ascii=False, default=str),
            system_instruction=f"{PATIENT_RESPONSE_SYSTEM_INSTRUCTION}\n\n{language_instruction(response_locale)}",
            generation_config={
                "max_output_tokens": self.cost_guard.max_output_tokens,
                "thinking_level": "minimal",
            },
            store=False,
        )
        text = self._interaction_text(interaction)
        if not text:
            raise RuntimeError("Gemini returned an empty patient response")
        return text

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
            "response_locale": payload.get("response_locale"),
        }
        return payload

    @staticmethod
    def _conversation_memory(state: PatientState) -> list[dict[str, str]]:
        memory: list[dict[str, str]] = []
        for message in state.messages[-16:]:
            text = str(message.content or "").strip()
            if not text or text.startswith("[ENTREVISTA_CLINICA]"):
                continue
            memory.append({"role": message.role, "content": text[:1200]})
        return memory

    def _generate_clinical_resolution(
        self,
        state: PatientState,
        *,
        chief_complaint: str,
        stage: int,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        response_locale = self._response_locale(state, chief_complaint)
        payload = {
            "task": "decide_if_clinical_interview_is_sufficient_and_explain_next_step",
            "stage": stage,
            "chief_complaint": chief_complaint,
            "all_interview_answers": answers[-30:],
            "authorized_clinical_context": self.authorized_context(state),
            "recent_conversation_memory": self._conversation_memory(state),
            "response_locale": response_locale,
            "constraints": {
                "maximum_interview_stage": 3,
                "ask_more_only_if_materially_decision_changing": True,
                "must_not_confirm_diagnosis": True,
                "must_not_prescribe_or_change_medication": True,
                "must_explain_uncertainty": True,
                "patient_visible_language": response_locale,
            },
        }
        interaction = self._get_client().interactions.create(
            model=self.settings.model,
            input=json.dumps(payload, ensure_ascii=False, default=str),
            system_instruction=f"{CLINICAL_RESOLUTION_SYSTEM_INSTRUCTION}\n\n{language_instruction(response_locale)}",
            generation_config={
                "max_output_tokens": min(self.cost_guard.max_output_tokens, 1500),
                "thinking_level": "minimal",
            },
            store=False,
        )
        text = self._interaction_text(interaction)
        if not text:
            raise RuntimeError("Gemini returned an empty clinical resolution")
        result = self._json_object(text)
        decision = str(result.get("decision", "")).strip().lower()
        if decision not in {"summarize", "ask_more"}:
            raise ValueError("Gemini did not return a valid clinical decision")
        result["response_locale"] = response_locale
        return result

    def _mission_for_interview_id(self, state: PatientState, interview: dict[str, Any]):
        mission_id = interview.get("mission_id")
        return next((item for item in state.missions if item.id == mission_id), None)

    @staticmethod
    def _localized(locale: str, en: str, es: str) -> str:
        return es if locale == "es" else en

    def _mark_ai_resolution_unavailable(
        self,
        draft,
        interview: dict[str, Any],
        *,
        status: str,
        reason: str,
    ):
        locale = str(interview.get("response_locale") or current_requested_locale() or "en")
        interview["status"] = "ai_resolution_unavailable"
        interview.pop("question_block", None)
        draft.message.content = self._localized(
            locale,
            (
                "I could not generate the adaptive AI clinical orientation in this run. "
                "I will not replace it with preloaded questions or pretend to have reached a conclusion. "
                "Your answers remain saved; retry when Google AI is available. If symptoms are severe, rapidly worsening, "
                "or a warning sign appears, seek human evaluation without waiting for the chat."
            ),
            (
                "No pude generar una orientación clínica adaptativa con la IA en esta ejecución. "
                "No voy a sustituirla por preguntas precargadas ni fingir una conclusión. "
                "Tus respuestas quedaron guardadas; reintenta cuando Google AI esté disponible. Si hay síntomas intensos, "
                "empeoramiento rápido o una señal de alarma, busca valoración humana sin esperar al chat."
            ),
        )
        draft.message.metadata.update(
            {
                "llm_backend": self.settings.llm_backend,
                "llm_status": status,
                "clinical_synthesis_source": "unavailable_not_faked",
                "llm_error": reason[:500],
                "response_locale": locale,
                "cost_guard": self.cost_guard.snapshot(),
            }
        )
        self.last_status = status
        self.last_error = reason[:500]
        return draft

    async def _enhance_clinical_resolution(self, state: PatientState, draft, interview: dict[str, Any]):
        chief_complaint = str(interview.get("chief_complaint") or "Health consultation").strip()
        response_locale = self._response_locale(state, chief_complaint)
        interview["response_locale"] = response_locale
        answers = interview.get("answers") or interview.get("previous_answers") or []
        if not isinstance(answers, list):
            answers = []
        stage = int(interview.get("stage", 2))

        if self.settings.llm_backend != "gemini_api" or not self.settings.adk_ready:
            return self._mark_ai_resolution_unavailable(
                draft,
                interview,
                status="clinical_ai_resolution_not_configured",
                reason="Gemini is not configured for this run.",
            )

        if draft.message.risk_level == RiskLevel.URGENT:
            return self._mark_ai_resolution_unavailable(
                draft,
                interview,
                status="deterministic_safety",
                reason="Deterministic safety interrupted routine clinical resolution.",
            )

        try:
            resolution_request = self.cost_guard.authorize("clinical_synthesis_or_followup_decision")
        except CostGuardBlocked as exc:
            return self._mark_ai_resolution_unavailable(
                draft,
                interview,
                status="cost_guard_blocked",
                reason=str(exc),
            )

        try:
            resolution = await asyncio.wait_for(
                asyncio.to_thread(
                    self._generate_clinical_resolution,
                    state,
                    chief_complaint=chief_complaint,
                    stage=stage,
                    answers=answers,
                ),
                timeout=self.settings.llm_timeout_seconds,
            )
        except Exception as exc:
            return self._mark_ai_resolution_unavailable(
                draft,
                interview,
                status="clinical_ai_resolution_failed",
                reason=f"{type(exc).__name__}: {exc}",
            )

        response_locale = str(resolution.get("response_locale") or response_locale)
        interview["response_locale"] = response_locale
        decision = str(resolution.get("decision", "summarize")).lower()
        if decision == "ask_more" and stage < 3:
            next_stage = stage + 1
            try:
                question_request = self.cost_guard.authorize("dynamic_clinical_followup_block")
                model_payload = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._generate_clinical_block,
                        state,
                        chief_complaint=chief_complaint,
                        stage=next_stage,
                        previous_answers=answers,
                    ),
                    timeout=self.settings.llm_timeout_seconds,
                )
                if model_payload.get("intent") != "clinical_consultation":
                    raise ValueError("ADK did not confirm clinical consultation intent")
                block = normalize_dynamic_question_block(model_payload, next_stage)
                agent_plan = self._apply_on_demand_plan(
                    state,
                    draft,
                    interview,
                    chief_complaint=chief_complaint,
                    previous_answers=answers,
                    requested_roles=model_payload.get("selected_specialists"),
                )
                review = judge_dynamic_plan(
                    block,
                    chief_complaint=chief_complaint,
                    previous_answers=answers,
                    agent_plan=agent_plan,
                    model_payload=model_payload,
                )
                if not review["approved"]:
                    raise ValueError("JUDGE Ω rejected the additional block: " + "; ".join(review["blockers"]))
            except Exception as exc:
                return self._mark_ai_resolution_unavailable(
                    draft,
                    interview,
                    status="clinical_followup_generation_failed",
                    reason=f"{type(exc).__name__}: {exc}",
                )

            response_locale = str(model_payload.get("response_locale") or response_locale)
            interview.update(
                {
                    "stage": next_stage,
                    "status": "awaiting_answers",
                    "previous_answers": answers,
                    "question_block": block,
                    "question_source": "gemini_dynamic",
                    "response_locale": response_locale,
                    "clinical_focus": str(model_payload.get("clinical_focus", "")).strip(),
                    "why_these_questions": model_payload.get("why_these_questions") or [],
                    "missing_information": model_payload.get("missing_information") or resolution.get("missing_information") or [],
                    "judge_review": review,
                }
            )
            mission = self._mission_for_interview_id(state, interview)
            if mission is not None:
                mission.status = MissionStatus.WAITING_PATIENT
                mission.next_action = self._localized(
                    response_locale,
                    "Answer the final adaptive round because one material fact can still change the orientation",
                    "Responder una última ronda adaptativa porque todavía falta información que puede cambiar la orientación",
                )
            draft.message.agent_plan = agent_plan
            draft.message.content = self._localized(
                response_locale,
                "There is still one point that could change the orientation. I prepared one final set of five specific questions without repeating what you already answered.",
                "Con lo que ya me dijiste todavía falta aclarar un punto que puede cambiar la orientación. Preparé una última ronda de cinco preguntas específicas; no voy a repetir lo que ya respondiste.",
            )
            draft.message.metadata.update(
                {
                    "llm_backend": "gemini_api",
                    "llm_status": "dynamic_clinical_followup_questions",
                    "question_source": "gemini_dynamic",
                    "response_locale": response_locale,
                    "clinical_resolution_decision": "ask_more",
                    "clinical_resolution_reason": str(resolution.get("decision_reason", ""))[:500],
                    "request_number": question_request,
                    "resolution_request_number": resolution_request,
                    "judge_review": review,
                    "cost_guard": self.cost_guard.snapshot(),
                }
            )
            self.last_status = "dynamic_clinical_followup_questions"
            self.last_error = ""
            return draft

        patient_message = str(resolution.get("patient_message") or "").strip()
        if not patient_message:
            return self._mark_ai_resolution_unavailable(
                draft,
                interview,
                status="clinical_ai_resolution_invalid",
                reason="Gemini chose summarize but returned no patient-facing message.",
            )

        interview.update(
            {
                "status": "completed",
                "response_locale": response_locale,
                "clinical_focus": str(resolution.get("clinical_focus", "")).strip(),
                "missing_information": resolution.get("missing_information") or [],
                "resolution_decision": "summarize",
                "possible_explanations": resolution.get("possible_explanations") or [],
                "care_level": resolution.get("care_level") or "",
            }
        )
        mission = self._mission_for_interview_id(state, interview)
        if mission is not None:
            mission.status = MissionStatus.WAITING_PROFESSIONAL
            mission.next_action = self._localized(
                response_locale,
                "Review the orientation with a professional and update HealthIA with the outcome",
                "Revisar la orientación con un profesional y actualizar HealthIA con el resultado",
            )
            if "ai_clinical_orientation_generated" not in mission.closure_evidence:
                mission.closure_evidence.append("ai_clinical_orientation_generated")

        draft.message.content = patient_message
        draft.message.author = "HealthIA"
        draft.message.metadata.update(
            {
                "llm_backend": "gemini_api",
                "llm_status": "clinical_ai_orientation_completed",
                "clinical_synthesis_source": "gemini",
                "clinical_resolution_decision": "summarize",
                "clinical_resolution_reason": str(resolution.get("decision_reason", ""))[:500],
                "possible_explanations": resolution.get("possible_explanations") or [],
                "care_level": resolution.get("care_level") or "",
                "response_locale": response_locale,
                "request_number": resolution_request,
                "cost_guard": self.cost_guard.snapshot(),
            }
        )
        self.last_status = "clinical_ai_orientation_completed"
        self.last_error = ""
        return draft

    async def enhance(self, state: PatientState, patient_text: str, draft):
        interview = draft.message.metadata.get("clinical_interview")
        if isinstance(interview, dict) and interview.get("status") == "ready_for_synthesis":
            return await self._enhance_clinical_resolution(state, draft, interview)

        result = await super().enhance(state, patient_text, draft)
        response_locale = self._response_locale(state, patient_text)
        result.message.metadata["response_locale"] = response_locale

        # The parent owns the interview state machine. Its visible transition
        # sentence is deterministic, so localize it here while ADK owns the five
        # actual questions/options in the same response locale.
        current_interview = result.message.metadata.get("clinical_interview")
        if isinstance(current_interview, dict) and result.message.metadata.get("question_source") == "gemini_dynamic":
            stage = int(current_interview.get("stage", 1))
            response_locale = str(current_interview.get("response_locale") or response_locale)
            current_interview["response_locale"] = response_locale
            result.message.metadata["response_locale"] = response_locale
            result.message.content = self._localized(
                response_locale,
                (
                    "I reviewed what you shared and prepared five case-specific questions to reduce uncertainty, check warning signs, and guide the safest next step."
                    if stage == 1
                    else "I used your previous answers to generate five new questions without repeating what is already known."
                ),
                (
                    "Analicé lo que contaste y preparé cinco preguntas específicas para aclarar las explicaciones posibles, detectar señales de alarma y orientarte al siguiente paso seguro."
                    if stage == 1
                    else "Usé tus respuestas anteriores para generar cinco preguntas nuevas sin repetir lo ya aclarado."
                ),
            )
        return result