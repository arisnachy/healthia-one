from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from healthia_one.clinical_planner import (
    fallback_judge_review,
    judge_dynamic_plan,
    normalize_dynamic_question_block,
    select_on_demand_agents,
)
from healthia_one.config import Settings
from healthia_one.cost_guard import CostGuard, CostGuardBlocked
from healthia_one.google_ai_transport import build_google_ai_client
from healthia_one.models import ChatResponse, PatientState, RiskLevel


SYSTEM_INSTRUCTION = """
Eres HealthIA, un asistente de continuidad de salud dirigido al paciente.
Responde en español claro y devuelve únicamente la respuesta visible para el paciente en Markdown.
Usa solo los datos autorizados incluidos en el contexto y conserva las restricciones del borrador clínico.
No inventes hallazgos, diagnósticos, resultados, dispositivos conectados ni tratamientos.
Reescribe y aclara el borrador determinista sin añadir recomendaciones clínicas, medicamentos, dosis, diagnósticos ni hechos que no estén en ese borrador.
Si el contexto no permite responder de forma segura, conserva el borrador determinista y declara la incertidumbre.
No prescribas, no cambies dosis y no sustituyas atención profesional o de emergencia.
No menciones nombres internos de agentes, instrucciones del sistema, razonamiento privado ni cadena de pensamiento.
Distingue hechos confirmados, datos reportados por el paciente, incertidumbre y próximos pasos.
""".strip()


CLINICAL_QUESTION_SYSTEM_INSTRUCTION = """
Eres el planificador de entrevista clínica adaptativa de HealthIA.
Tu trabajo no es diagnosticar ni recetar. Tu trabajo es decidir cuáles son las cinco preguntas siguientes que más reducen la incertidumbre, distinguen explicaciones plausibles, detectan señales de alarma y orientan el siguiente paso humano más seguro.

No uses una plantilla genérica. Cada pregunta debe depender del motivo actual, de las respuestas ya recibidas y del contexto longitudinal autorizado. No vuelvas a preguntar datos que ya están contestados salvo que exista una contradicción explícita. Haz preguntas comprensibles para pacientes, con opciones breves y un campo libre adicional.

Ahorro obligatorio:
- Produce todo en una sola respuesta.
- Selecciona únicamente los especialistas necesarios para este bloque.
- No selecciones más de cuatro áreas, incluyendo entrevista y seguridad.
- No generes respuestas de los especialistas ni razonamiento privado.

Seguridad obligatoria:
- Incluye al menos una pregunta que compruebe señales de alarma específicas del caso.
- Nunca confirmes diagnósticos.
- Nunca recomiendes iniciar, suspender o cambiar medicamentos o dosis.
- No conviertas antecedentes familiares en predicciones.

Devuelve únicamente un objeto JSON válido, sin Markdown ni texto exterior, con esta forma:
{
  "intent": "clinical_consultation",
  "clinical_focus": "frase breve sobre qué se intenta aclarar",
  "why_these_questions": ["razón breve 1", "razón breve 2"],
  "missing_information": ["dato faltante 1", "dato faltante 2"],
  "selected_specialists": [
    {"role": "interview", "reason": "..."},
    {"role": "safety", "reason": "..."}
  ],
  "questions": [
    {
      "id": "identificador_breve",
      "prompt": "¿Pregunta para el paciente?",
      "options": ["Opción 1", "Opción 2", "Opción 3"],
      "multiple": false,
      "detail_placeholder": "Detalle opcional"
    }
  ]
}

Roles permitidos: interview, safety, history, medication, documents, results, family, follow_up, privacy.
El arreglo questions debe contener exactamente cinco preguntas. Cada pregunta debe tener entre tres y siete opciones distintas.
""".strip()


class GeminiResponder:
    """Patient-facing Gemini boundary with deterministic safety and cost fallback."""

    def __init__(self, settings: Settings, client_factory: Callable[[], Any] | None = None) -> None:
        self.settings = settings
        self._client_factory = client_factory
        self._client: Any | None = None
        self.cost_guard = CostGuard(
            mode=settings.cost_mode,
            request_limit=settings.ai_request_limit,
            start_enabled=settings.cost_guard_start_enabled,
            max_output_tokens=settings.ai_max_output_tokens,
        )
        self.last_status = "not_called"
        self.last_error = ""

    def cost_status(self) -> dict[str, Any]:
        payload = self.cost_guard.snapshot()
        payload.update(
            {
                "llm_backend": self.settings.llm_backend,
                "model": self.settings.model,
                "google_ai_configured": self.settings.adk_ready,
                "ai_transport": "vertex_ai" if self.settings.vertex_ai_enabled else "developer_api",
                "ui_control_available": bool(self.settings.cost_control_ui and self.settings.env == "local"),
            }
        )
        return payload

    def set_cost_enabled(self, enabled: bool) -> dict[str, Any]:
        if not self.settings.cost_control_ui or self.settings.env != "local":
            raise CostGuardBlocked("El interruptor remoto está deshabilitado fuera del entorno local.")
        if enabled and not self.settings.adk_ready:
            raise CostGuardBlocked("Google AI no está configurado para esta ejecución local.")
        self.cost_guard.set_enabled(enabled)
        return self.cost_status()

    def _get_client(self) -> Any:
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory()
            else:
                self._client = build_google_ai_client(self.settings)
        return self._client

    @staticmethod
    def _interaction_text(interaction: Any) -> str:
        direct = getattr(interaction, "output_text", "")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        outputs = getattr(interaction, "outputs", None) or []
        for output in reversed(outputs):
            text = getattr(output, "text", "")
            if isinstance(text, str) and text.strip():
                return text.strip()
            if isinstance(output, dict):
                text = output.get("text", "")
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return ""

    @staticmethod
    def _json_object(text: str) -> dict[str, Any]:
        value = text.strip()
        if value.startswith("```"):
            value = value.replace("```json", "", 1).replace("```", "", 1).strip()
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("Gemini no devolvió un objeto JSON")
            payload = json.loads(value[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Gemini no devolvió un objeto JSON")
        return payload

    @staticmethod
    def authorized_context(state: PatientState) -> dict[str, Any]:
        profile = state.profile
        return {
            "patient": {
                "display_name": profile.display_name,
                "locale": profile.locale,
                "confirmed_conditions": profile.confirmed_conditions,
                "allergies": profile.allergies,
            },
            "recent_vitals": [item.model_dump(mode="json") for item in state.vitals[-5:]],
            "recent_weights": [item.model_dump(mode="json") for item in state.weights[-5:]],
            "recent_activity": [item.model_dump(mode="json") for item in state.activity[-5:]],
            "medications": [
                {
                    "name": item.name,
                    "strength": item.strength,
                    "route": item.route,
                    "schedule": item.schedule,
                    "purpose": item.purpose,
                    "verification_status": item.verification_status,
                }
                for item in state.medication_plans
                if item.active
            ],
            "recent_results": [
                {
                    "panel": item.panel,
                    "status": item.status,
                    "explanation": item.explanation,
                    "uploaded_at": item.uploaded_at.isoformat(),
                }
                for item in state.results[-3:]
            ],
            "upcoming_appointments": [
                {
                    "title": item.title,
                    "specialty": item.specialty,
                    "scheduled_at": item.scheduled_at.isoformat(),
                    "location": item.location,
                }
                for item in state.appointments[-3:]
            ],
            "active_missions": [
                {
                    "title": item.title,
                    "mission_type": item.mission_type,
                    "status": item.status.value,
                    "next_action": item.next_action,
                }
                for item in state.missions[-5:]
            ],
            "truth_boundary": "Datos del paciente autorizados. No diagnosticar, prescribir ni inventar datos faltantes.",
        }

    @staticmethod
    def compact_clinical_context(state: PatientState) -> dict[str, Any]:
        profile = state.profile
        reproductive = profile.reproductive_health
        return {
            "sex_at_birth": profile.sex_at_birth,
            "pregnancy_status": reproductive.pregnancy_status if reproductive.applicable else "not_applicable_or_unknown",
            "confirmed_conditions": profile.confirmed_conditions[:6],
            "relevant_history": profile.personal_history.chronic_conditions[:6],
            "allergies": profile.allergies[:6],
            "active_medications": [
                {
                    "name": item.name,
                    "strength": item.strength,
                    "schedule": item.schedule,
                    "verification_status": item.verification_status,
                }
                for item in state.medication_plans
                if item.active
            ][:6],
            "latest_vitals": [item.model_dump(mode="json") for item in state.vitals[-3:]],
            "recent_result_panels": [item.panel for item in state.results[-3:]],
            "available_documents": [item.category.value for item in state.documents[-5:]],
        }

    @staticmethod
    def _chief_complaint(state: PatientState, interview: dict[str, Any]) -> str:
        direct = str(interview.get("chief_complaint", "")).strip()
        if direct:
            return direct
        interview_id = interview.get("id")
        for message in reversed(state.messages):
            stored = message.metadata.get("clinical_interview")
            if isinstance(stored, dict) and stored.get("id") == interview_id:
                complaint = str(stored.get("chief_complaint", "")).strip()
                if complaint:
                    return complaint
        return "Consulta clínica iniciada por el paciente"

    def _generate(self, state: PatientState, patient_text: str, draft: ChatResponse) -> str:
        payload = {
            "patient_message": patient_text,
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
            system_instruction=SYSTEM_INSTRUCTION,
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
        payload = {
            "task": "generate_next_adaptive_clinical_question_block",
            "stage": stage,
            "chief_complaint": chief_complaint,
            "previous_answers": previous_answers,
            "authorized_clinical_context": self.compact_clinical_context(state),
            "constraints": {
                "exact_question_count": 5,
                "question_options_min": 3,
                "question_options_max": 7,
                "must_include_case_specific_safety_check": True,
                "must_not_repeat_known_answers": True,
                "must_not_diagnose_or_prescribe": True,
                "maximum_selected_specialists": 4,
                "single_model_call": True,
            },
        }
        interaction = self._get_client().interactions.create(
            model=self.settings.model,
            input=json.dumps(payload, ensure_ascii=False, default=str),
            system_instruction=CLINICAL_QUESTION_SYSTEM_INSTRUCTION,
            generation_config={
                "max_output_tokens": min(self.cost_guard.max_output_tokens, 1200),
                "thinking_level": "minimal",
            },
            store=False,
        )
        text = self._interaction_text(interaction)
        if not text:
            raise RuntimeError("Gemini devolvió un plan clínico vacío")
        return self._json_object(text)

    @staticmethod
    def _mission_for_interview(state: PatientState, draft: ChatResponse, interview: dict[str, Any]):
        if draft.mission is not None:
            return draft.mission
        mission_id = interview.get("mission_id")
        return next((item for item in state.missions if item.id == mission_id), None)

    def _apply_on_demand_plan(
        self,
        state: PatientState,
        draft: ChatResponse,
        interview: dict[str, Any],
        *,
        chief_complaint: str,
        previous_answers: list[dict[str, Any]],
        requested_roles: list[Any] | None = None,
    ):
        stage = int(interview.get("stage", 1))
        agent_plan = select_on_demand_agents(
            state,
            chief_complaint,
            previous_answers,
            stage=stage,
            requested_roles=requested_roles,
        )
        draft.message.agent_plan = agent_plan
        mission = self._mission_for_interview(state, draft, interview)
        if mission is not None:
            mission.agent_plan = agent_plan
        return agent_plan

    def _clinical_fallback(
        self,
        state: PatientState,
        draft: ChatResponse,
        interview: dict[str, Any],
        *,
        chief_complaint: str,
        previous_answers: list[dict[str, Any]],
        reason: str,
        status: str,
    ) -> ChatResponse:
        agent_plan = self._apply_on_demand_plan(
            state,
            draft,
            interview,
            chief_complaint=chief_complaint,
            previous_answers=previous_answers,
        )
        review = fallback_judge_review(reason, agent_plan)
        interview.update(
            {
                "question_source": "safe_fallback",
                "agent_execution": "on_demand",
                "selected_agent_count": len(agent_plan),
                "judge_review": review,
            }
        )
        draft.message.metadata.update(
            {
                "llm_backend": self.settings.llm_backend,
                "llm_status": status,
                "model": self.settings.model,
                "question_source": "safe_fallback",
                "agent_execution": "on_demand",
                "selected_agent_count": len(agent_plan),
                "judge_review": review,
                "cost_guard": self.cost_guard.snapshot(),
            }
        )
        self.last_status = status
        self.last_error = reason
        return draft

    async def _enhance_clinical_interview(
        self,
        state: PatientState,
        patient_text: str,
        draft: ChatResponse,
        interview: dict[str, Any],
    ) -> ChatResponse:
        chief_complaint = self._chief_complaint(state, interview)
        previous_answers = interview.get("previous_answers") or interview.get("answers") or []
        if not isinstance(previous_answers, list):
            previous_answers = []

        if interview.get("status") != "awaiting_answers" or not isinstance(interview.get("question_block"), dict):
            agent_plan = self._apply_on_demand_plan(
                state,
                draft,
                interview,
                chief_complaint=chief_complaint,
                previous_answers=previous_answers,
            )
            draft.message.metadata.update(
                {
                    "llm_backend": self.settings.llm_backend,
                    "llm_status": "structured_workflow_completed",
                    "model": self.settings.model,
                    "agent_execution": "on_demand",
                    "selected_agent_count": len(agent_plan),
                }
            )
            self.last_status = "structured_workflow_completed"
            self.last_error = ""
            return draft

        if self.settings.llm_backend != "gemini_api" or not self.settings.adk_ready:
            return self._clinical_fallback(
                state,
                draft,
                interview,
                chief_complaint=chief_complaint,
                previous_answers=previous_answers,
                reason="Gemini está apagado o no configurado; el bloque de respaldo no demuestra generación adaptativa.",
                status="clinical_safe_fallback_not_configured",
            )

        if draft.message.risk_level == RiskLevel.URGENT:
            return self._clinical_fallback(
                state,
                draft,
                interview,
                chief_complaint=chief_complaint,
                previous_answers=previous_answers,
                reason="La seguridad determinista detuvo la generación de preguntas de rutina.",
                status="deterministic_safety",
            )

        try:
            request_number = self.cost_guard.authorize("dynamic_clinical_question_block")
        except CostGuardBlocked as exc:
            return self._clinical_fallback(
                state,
                draft,
                interview,
                chief_complaint=chief_complaint,
                previous_answers=previous_answers,
                reason=str(exc),
                status="cost_guard_blocked",
            )

        stage = int(interview.get("stage", 1))
        try:
            model_payload = await asyncio.wait_for(
                asyncio.to_thread(
                    self._generate_clinical_block,
                    state,
                    chief_complaint=chief_complaint,
                    stage=stage,
                    previous_answers=previous_answers,
                ),
                timeout=self.settings.llm_timeout_seconds,
            )
            if model_payload.get("intent") != "clinical_consultation":
                raise ValueError("Gemini no confirmó la intención de consulta clínica")
            block = normalize_dynamic_question_block(model_payload, stage)
            agent_plan = self._apply_on_demand_plan(
                state,
                draft,
                interview,
                chief_complaint=chief_complaint,
                previous_answers=previous_answers,
                requested_roles=model_payload.get("selected_specialists"),
            )
            review = judge_dynamic_plan(
                block,
                chief_complaint=chief_complaint,
                previous_answers=previous_answers,
                agent_plan=agent_plan,
                model_payload=model_payload,
            )
            if not review["approved"]:
                raise ValueError("JUDGE Ω rechazó el bloque: " + "; ".join(review["blockers"]))
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"[:500]
            fallback = self._clinical_fallback(
                state,
                draft,
                interview,
                chief_complaint=chief_complaint,
                previous_answers=previous_answers,
                reason=reason,
                status="clinical_safe_fallback",
            )
            fallback.message.metadata.update(
                {
                    "request_number": request_number,
                    "store": False,
                    "cost_guard": self.cost_guard.snapshot(),
                }
            )
            return fallback

        interview.update(
            {
                "question_block": block,
                "question_source": "gemini_dynamic",
                "clinical_focus": str(model_payload.get("clinical_focus", "")).strip(),
                "why_these_questions": model_payload.get("why_these_questions") or [],
                "missing_information": model_payload.get("missing_information") or [],
                "agent_execution": "on_demand",
                "selected_agent_count": len(agent_plan),
                "judge_review": review,
            }
        )
        draft.message.agent_plan = agent_plan
        draft.message.metadata.update(
            {
                "llm_backend": "gemini_api",
                "llm_status": "dynamic_clinical_questions",
                "model": self.settings.model,
                "store": False,
                "request_number": request_number,
                "question_source": "gemini_dynamic",
                "agent_execution": "on_demand",
                "selected_agent_count": len(agent_plan),
                "judge_review": review,
                "cost_guard": self.cost_guard.snapshot(),
            }
        )
        draft.message.content = (
            "Analicé lo que contaste y preparé cinco preguntas específicas para aclarar las explicaciones posibles, "
            "detectar señales de alarma y orientarte al siguiente paso seguro. Solo activé las áreas necesarias para este bloque."
            if stage == 1
            else "Usé tus respuestas anteriores para generar cinco preguntas nuevas sin repetir lo ya aclarado. Después de este bloque, la junta seleccionada organizará la dirección más segura."
        )
        self.last_status = "dynamic_clinical_questions"
        self.last_error = ""
        return draft

    async def enhance(self, state: PatientState, patient_text: str, draft: ChatResponse) -> ChatResponse:
        interview = draft.message.metadata.get("clinical_interview")
        if isinstance(interview, dict):
            return await self._enhance_clinical_interview(state, patient_text, draft, interview)

        if self.settings.llm_backend != "gemini_api" or not self.settings.adk_ready:
            self.last_status = "not_configured"
            return draft
        if draft.message.risk_level == RiskLevel.URGENT:
            self.last_status = "deterministic_safety"
            return draft
        try:
            request_number = self.cost_guard.authorize("patient_chat_enhancement")
        except CostGuardBlocked as exc:
            self.last_status = "cost_guard_blocked"
            self.last_error = str(exc)
            draft.message.metadata.update(
                {
                    "llm_backend": "gemini_api",
                    "llm_status": "cost_guard_blocked",
                    "model": self.settings.model,
                    "cost_guard": self.cost_guard.snapshot(),
                }
            )
            return draft
        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(self._generate, state, patient_text, draft),
                timeout=self.settings.llm_timeout_seconds,
            )
        except Exception as exc:
            self.last_status = "fallback"
            self.last_error = f"{type(exc).__name__}: {exc}"[:500]
            draft.message.metadata.update(
                {
                    "llm_backend": "gemini_api",
                    "llm_status": "fallback",
                    "model": self.settings.model,
                    "request_number": request_number,
                    "cost_guard": self.cost_guard.snapshot(),
                }
            )
            return draft

        draft.message.content = text
        draft.message.author = "HealthIA"
        draft.message.metadata.update(
            {
                "llm_backend": "gemini_api",
                "llm_status": "completed",
                "model": self.settings.model,
                "store": False,
                "request_number": request_number,
                "cost_guard": self.cost_guard.snapshot(),
            }
        )
        self.last_status = "completed"
        self.last_error = ""
        return draft

    def _live_probe(self) -> str:
        interaction = self._get_client().interactions.create(
            model=self.settings.model,
            input="Responde únicamente con HEALTHIA_OK",
            system_instruction="Prueba técnica mínima. No añadas ninguna otra palabra.",
            generation_config={"max_output_tokens": 32, "thinking_level": "minimal"},
            store=False,
        )
        text = self._interaction_text(interaction)
        if not text:
            raise RuntimeError("Gemini respondió sin texto utilizable")
        return text

    async def probe(self) -> dict[str, Any]:
        if self.settings.llm_backend != "gemini_api" or not self.settings.adk_ready:
            return {
                "ok": False,
                "status": "not_configured",
                "model": self.settings.model,
                "live_request": False,
                "detail": "Falta configurar GEMINI_API_KEY en el proceso local.",
                "cost_guard": self.cost_guard.snapshot(),
            }
        try:
            request_number = self.cost_guard.authorize("manual_readiness_probe")
        except CostGuardBlocked as exc:
            self.last_status = "cost_guard_blocked"
            self.last_error = str(exc)
            return {
                "ok": False,
                "status": "cost_guard_blocked",
                "model": self.settings.model,
                "live_request": False,
                "detail": str(exc),
                "cost_guard": self.cost_guard.snapshot(),
            }
        try:
            client = self._get_client()
            if not hasattr(client, "interactions"):
                raise RuntimeError("google-genai 2.x con Interactions API no está instalado")
            response = await asyncio.wait_for(
                asyncio.to_thread(self._live_probe),
                timeout=min(self.settings.llm_timeout_seconds, 30),
            )
            try:
                sdk_version = version("google-genai")
            except PackageNotFoundError:
                sdk_version = "unknown"
        except Exception as exc:
            self.last_status = "probe_failed"
            self.last_error = f"{type(exc).__name__}: {exc}"[:500]
            return {
                "ok": False,
                "status": "probe_failed",
                "model": self.settings.model,
                "live_request": True,
                "detail": self.last_error,
                "request_number": request_number,
                "cost_guard": self.cost_guard.snapshot(),
            }
        self.last_status = "ready"
        self.last_error = ""
        return {
            "ok": True,
            "status": "ready",
            "model": self.settings.model,
            "sdk_version": sdk_version,
            "live_request": True,
            "response": response,
            "store": False,
            "request_number": request_number,
            "cost_guard": self.cost_guard.snapshot(),
        }
