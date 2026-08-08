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
from healthia_one.models import MissionStatus, PatientState, RiskLevel


CLINICAL_RESOLUTION_SYSTEM_INSTRUCTION = """
Eres HealthIA, un asistente de continuidad de salud dirigido al paciente.

Recibirás el motivo inicial, todas las respuestas acumuladas de una entrevista adaptativa y el contexto longitudinal autorizado.
Decide si ya hay información suficiente para dar una orientación clínica segura o si todavía falta una ronda realmente necesaria.

No confirmes diagnósticos. Puedes explicar posibilidades clínicas plausibles y qué datos las apoyan o las hacen inciertas.
No prescribas, no cambies dosis, no indiques suspender tratamientos y no declares que una situación peligrosa es segura.
Si existen señales de alarma, prioriza claramente la evaluación humana correspondiente.
No repitas preguntas ya contestadas. No pidas otra ronda por rutina: solo si un dato faltante puede cambiar de forma material el nivel de atención o la orientación.

Devuelve únicamente JSON válido:
{
  "decision": "summarize" | "ask_more",
  "clinical_focus": "qué se intenta aclarar",
  "missing_information": ["dato faltante importante"],
  "decision_reason": "por qué ya se puede orientar o por qué hace falta preguntar más",
  "patient_message": "Markdown para el paciente si decision=summarize; vacío si ask_more",
  "possible_explanations": [
    {
      "name": "posibilidad, no diagnóstico confirmado",
      "why_possible": "datos concretos que la hacen plausible",
      "why_uncertain": "qué falta o qué la limita"
    }
  ],
  "care_level": "self_care_information | routine_professional | priority_professional | urgent"
}

Cuando decision=summarize, patient_message debe sonar natural, como una conversación humana, e incluir:
- qué entendiste del caso;
- las posibilidades principales en lenguaje claro, dejando explícito que no son diagnósticos confirmados;
- qué dato pesa a favor o en contra;
- qué nivel de atención parece prudente;
- qué debe contar o preguntar al profesional;
- señales concretas por las que no debería esperar.

No menciones agentes internos, prompts, cadenas de pensamiento ni nombres de herramientas.
""".strip()


class AdkGeminiResponder(GeminiResponder):
    """Gemini patient boundary whose clinical planner is executed by Google ADK."""

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

    @staticmethod
    def _conversation_memory(state: PatientState) -> list[dict[str, str]]:
        memory: list[dict[str, str]] = []
        for message in state.messages[-16:]:
            text = str(message.content or "").strip()
            if not text or text.startswith("[ENTREVISTA_CLINICA]"):
                continue
            memory.append(
                {
                    "role": message.role,
                    "content": text[:1200],
                }
            )
        return memory

    def _generate_clinical_resolution(
        self,
        state: PatientState,
        *,
        chief_complaint: str,
        stage: int,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {
            "task": "decide_if_clinical_interview_is_sufficient_and_explain_next_step",
            "stage": stage,
            "chief_complaint": chief_complaint,
            "all_interview_answers": answers[-30:],
            "authorized_clinical_context": self.authorized_context(state),
            "recent_conversation_memory": self._conversation_memory(state),
            "constraints": {
                "maximum_interview_stage": 3,
                "ask_more_only_if_materially_decision_changing": True,
                "must_not_confirm_diagnosis": True,
                "must_not_prescribe_or_change_medication": True,
                "must_explain_uncertainty": True,
            },
        }
        interaction = self._get_client().interactions.create(
            model=self.settings.model,
            input=json.dumps(payload, ensure_ascii=False, default=str),
            system_instruction=CLINICAL_RESOLUTION_SYSTEM_INSTRUCTION,
            generation_config={
                "max_output_tokens": min(self.cost_guard.max_output_tokens, 1500),
                "thinking_level": "minimal",
            },
            store=False,
        )
        text = self._interaction_text(interaction)
        if not text:
            raise RuntimeError("Gemini devolvió una resolución clínica vacía")
        result = self._json_object(text)
        decision = str(result.get("decision", "")).strip().lower()
        if decision not in {"summarize", "ask_more"}:
            raise ValueError("Gemini no devolvió una decisión clínica válida")
        return result

    def _mission_for_interview_id(self, state: PatientState, interview: dict[str, Any]):
        mission_id = interview.get("mission_id")
        return next((item for item in state.missions if item.id == mission_id), None)

    def _mark_ai_resolution_unavailable(
        self,
        draft,
        interview: dict[str, Any],
        *,
        status: str,
        reason: str,
    ):
        interview["status"] = "ai_resolution_unavailable"
        interview.pop("question_block", None)
        draft.message.content = (
            "No pude generar una orientación clínica adaptativa con la IA en esta ejecución. "
            "No voy a sustituirla por preguntas precargadas ni fingir una conclusión. "
            "Tus respuestas quedaron guardadas; activa Google AI o reintenta cuando el servicio esté disponible. "
            "Si hay síntomas intensos, empeoramiento rápido o una señal de alarma, busca valoración humana sin esperar al chat."
        )
        draft.message.metadata.update(
            {
                "llm_backend": self.settings.llm_backend,
                "llm_status": status,
                "clinical_synthesis_source": "unavailable_not_faked",
                "llm_error": reason[:500],
                "cost_guard": self.cost_guard.snapshot(),
            }
        )
        self.last_status = status
        self.last_error = reason[:500]
        return draft

    async def _enhance_clinical_resolution(
        self,
        state: PatientState,
        draft,
        interview: dict[str, Any],
    ):
        chief_complaint = str(interview.get("chief_complaint") or "Consulta de salud").strip()
        answers = interview.get("answers") or interview.get("previous_answers") or []
        if not isinstance(answers, list):
            answers = []
        stage = int(interview.get("stage", 2))

        if self.settings.llm_backend != "gemini_api" or not self.settings.adk_ready:
            return self._mark_ai_resolution_unavailable(
                draft,
                interview,
                status="clinical_ai_resolution_not_configured",
                reason="Gemini no está configurado para esta ejecución.",
            )

        if draft.message.risk_level == RiskLevel.URGENT:
            return self._mark_ai_resolution_unavailable(
                draft,
                interview,
                status="deterministic_safety",
                reason="La seguridad determinista interrumpió la resolución rutinaria.",
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
                    raise ValueError("ADK no confirmó la intención de consulta clínica")
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
                    raise ValueError("JUDGE Ω rechazó el bloque adicional: " + "; ".join(review["blockers"]))
            except Exception as exc:
                return self._mark_ai_resolution_unavailable(
                    draft,
                    interview,
                    status="clinical_followup_generation_failed",
                    reason=f"{type(exc).__name__}: {exc}",
                )

            interview.update(
                {
                    "stage": next_stage,
                    "status": "awaiting_answers",
                    "previous_answers": answers,
                    "question_block": block,
                    "question_source": "gemini_dynamic",
                    "clinical_focus": str(model_payload.get("clinical_focus", "")).strip(),
                    "why_these_questions": model_payload.get("why_these_questions") or [],
                    "missing_information": model_payload.get("missing_information") or resolution.get("missing_information") or [],
                    "judge_review": review,
                }
            )
            mission = self._mission_for_interview_id(state, interview)
            if mission is not None:
                mission.status = MissionStatus.WAITING_PATIENT
                mission.next_action = "Responder una última ronda adaptativa porque todavía falta información que puede cambiar la orientación"
            draft.message.agent_plan = agent_plan
            draft.message.content = (
                "Con lo que ya me dijiste todavía falta aclarar un punto que puede cambiar la orientación. "
                "Preparé una última ronda de cinco preguntas específicas; no voy a repetir lo que ya respondiste."
            )
            draft.message.metadata.update(
                {
                    "llm_backend": "gemini_api",
                    "llm_status": "dynamic_clinical_followup_questions",
                    "question_source": "gemini_dynamic",
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
                reason="Gemini decidió resumir pero no devolvió un mensaje para el paciente.",
            )

        interview.update(
            {
                "status": "completed",
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
            mission.next_action = "Revisar la orientación con un profesional y actualizar HealthIA con el resultado"
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
        return await super().enhance(state, patient_text, draft)
