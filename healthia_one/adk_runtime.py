from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from healthia_one.clinical_planner import ROLE_DEFINITIONS
from healthia_one.clinical_tools import execute_on_demand_clinical_tools
from healthia_one.config import Settings
from healthia_one.models import AgentStep, PatientState


ADK_CLINICAL_INSTRUCTION = """
Eres el coordinador clínico de HealthIA ejecutado por Google Agent Development Kit (ADK).
No diagnosticas ni recetas. Tu función es decidir y EJECUTAR el conjunto mínimo de herramientas que necesita el siguiente bloque de entrevista clínica y después producir exactamente cinco preguntas adaptativas.

Reglas de herramientas:
1. Debes ejecutar siempre inspect_interview_requirements e inspect_safety_context antes de responder.
2. Puedes ejecutar como máximo dos herramientas opcionales adicionales.
3. Ejecuta una herramienta opcional solo si el caso realmente necesita esa información.
4. No inventes resultados de herramientas. Usa exclusivamente lo que las funciones devuelven.
5. No uses una herramienta como decoración; cada llamada debe cambiar qué preguntas haces o qué falta aclarar.
6. No des la respuesta final hasta haber ejecutado las dos herramientas obligatorias.

Reglas de memoria y naturalidad:
- Trata chief_complaint y previous_answers como memoria clínica acumulada, no como texto decorativo.
- Cada previous_answer incluye la pregunta original, opciones elegidas y detalle libre. No vuelvas a preguntar ese hecho con otras palabras salvo que exista una contradicción concreta.
- Cada pregunta nueva debe poder justificarse por una incertidumbre específica del caso actual.
- Evita plantillas genéricas como "¿qué otros síntomas tienes?" cuando ya puedes preguntar por un discriminante concreto.
- Si la respuesta previa ya contiene duración, intensidad, medicamento, alergia, exposición, signo vital o señal de alarma, considéralo conocido.
- Las opciones deben corresponder a la pregunta concreta; no uses la misma lista fija entre casos distintos.

Reglas clínicas:
- Usa el motivo actual, respuestas anteriores y contexto autorizado del mensaje.
- Incluye una pregunta sobre señales de alarma específicas del caso.
- Nunca confirmes diagnósticos ni indiques iniciar, suspender o cambiar medicamentos/dosis.
- No conviertas antecedentes familiares en predicciones.

Devuelve únicamente JSON válido, sin Markdown ni texto exterior:
{
  "intent": "clinical_consultation",
  "clinical_focus": "frase breve",
  "why_these_questions": ["razón 1 ligada a un dato concreto", "razón 2 ligada a un dato concreto"],
  "missing_information": ["dato 1", "dato 2"],
  "selected_specialists": [{"role": "interview", "reason": "ejecutado por ADK"}],
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
El arreglo questions contiene exactamente cinco preguntas y cada una entre tres y siete opciones distintas.
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
    for item in previous_answers[-30:]:
        if not isinstance(item, dict):
            continue
        clean.append(
            {
                "question_id": str(item.get("question_id") or "")[:80],
                "question_prompt": str(item.get("question_prompt") or "")[:320],
                "selected": [str(value)[:160] for value in (item.get("selected") or [])[:8]],
                "detail": str(item.get("detail") or "")[:500],
            }
        )
    return clean


class AdkClinicalRuntime:
    """Per-request ADK coordinator over the real authorized PatientState.

    The ADK model chooses optional tools. Interview and safety are hard runtime
    requirements: if the first ADK turn omits either, the same ADK Runner/session
    receives a corrective turn and must execute the missing tools before a plan
    can be accepted. The executed tool list, not model self-report, is evidence.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        value = str(text or "").strip()
        if value.startswith("```"):
            value = value.replace("```json", "", 1).replace("```", "", 1).strip()
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("Google ADK no devolvió un objeto JSON")
            payload = json.loads(value[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Google ADK no devolvió un objeto JSON")
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

        executed_roles: list[str] = []
        tool_outputs: list[dict[str, Any]] = []

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

        def inspect_interview_requirements() -> dict[str, Any]:
            """Always call first. Returns interview stage and what information remains to be clarified."""
            return execute_role("interview")

        def inspect_safety_context() -> dict[str, Any]:
            """Always call. Checks case-specific urgent signals before routine questions are generated."""
            return execute_role("safety")

        def inspect_longitudinal_history() -> dict[str, Any]:
            """Call only when prior conditions, recurrent symptoms or longitudinal measurements affect the next questions."""
            return execute_role("history")

        def inspect_medication_safety() -> dict[str, Any]:
            """Call only when medications, allergies, adherence or treatment context affects what must be clarified."""
            return execute_role("medication")

        def inspect_available_documents() -> dict[str, Any]:
            """Call only when uploaded reports or documents are relevant. Never invent unread contents."""
            return execute_role("documents")

        def inspect_available_results() -> dict[str, Any]:
            """Call only when laboratory, imaging, ECG or other persisted results are relevant to this interview."""
            return execute_role("results")

        def inspect_family_context() -> dict[str, Any]:
            """Call only when family history is specifically relevant; aggregation is never a diagnosis or prediction."""
            return execute_role("family")

        def inspect_follow_up_context() -> dict[str, Any]:
            """Call when a later block needs a concrete next step or mission closure condition."""
            return execute_role("follow_up")

        def inspect_privacy_scope() -> dict[str, Any]:
            """Call only when consent, data sharing, privacy or authorization is materially relevant."""
            return execute_role("privacy")

        agent = LlmAgent(
            name="healthia_runtime_coordinator",
            model=Gemini(
                model=self.settings.model,
                retry_options=types.HttpRetryOptions(attempts=2),
            ),
            description="Demand-driven HealthIA clinical coordinator over the current authorized patient state.",
            instruction=ADK_CLINICAL_INSTRUCTION,
            tools=[
                inspect_interview_requirements,
                inspect_safety_context,
                inspect_longitudinal_history,
                inspect_medication_safety,
                inspect_available_documents,
                inspect_available_results,
                inspect_family_context,
                inspect_follow_up_context,
                inspect_privacy_scope,
            ],
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
            "authorized_clinical_context": authorized_clinical_context,
            "constraints": {
                "exact_question_count": 5,
                "question_options_min": 3,
                "question_options_max": 7,
                "must_execute_tools": ["interview", "safety"],
                "maximum_total_tools": 4,
                "must_not_repeat_known_answers": True,
                "must_not_use_generic_template_when_case_specific_question_is_possible": True,
                "must_not_diagnose_or_prescribe": True,
            },
        }

        event_count = 0

        async def run_turn(text: str) -> str:
            nonlocal event_count
            message = types.Content(role="user", parts=[types.Part(text=text)])
            final_text = ""
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):
                event_count += 1
                content = getattr(event, "content", None)
                for part in getattr(content, "parts", None) or []:
                    part_text = getattr(part, "text", None)
                    if isinstance(part_text, str) and part_text.strip():
                        final_text = part_text.strip()
            return final_text

        final_text = await run_turn(json.dumps(prompt, ensure_ascii=False, default=str))

        mandatory = ("interview", "safety")
        missing = [role for role in mandatory if role not in executed_roles]
        if missing:
            missing_tools = [
                "inspect_interview_requirements" if role == "interview" else "inspect_safety_context"
                for role in missing
            ]
            correction = {
                "task": "repair_missing_mandatory_tool_execution",
                "missing_tools": missing_tools,
                "instruction": (
                    "La respuesta anterior no es aceptable porque faltan herramientas obligatorias. "
                    "Ejecuta AHORA cada herramienta faltante mediante tool calling en esta misma sesión. "
                    "Después devuelve de nuevo el objeto JSON clínico completo con exactamente cinco preguntas, "
                    "incorporando los resultados de esas herramientas. No respondas antes de ejecutarlas."
                ),
                "original_task": prompt,
            }
            repaired_text = await run_turn(json.dumps(correction, ensure_ascii=False, default=str))
            if repaired_text:
                final_text = repaired_text

        missing = [role for role in mandatory if role not in executed_roles]
        if missing:
            raise ValueError("ADK no ejecutó las herramientas obligatorias: " + ", ".join(missing))
        if len(executed_roles) > 4:
            raise ValueError("ADK activó más de cuatro herramientas para un solo bloque")
        optional_roles = [role for role in executed_roles if role not in mandatory]
        if len(optional_roles) > 2:
            raise ValueError("ADK activó más de dos herramientas opcionales para un solo bloque")
        if not final_text:
            raise RuntimeError("Google ADK devolvió una respuesta clínica vacía")

        payload = self._parse_json(final_text)
        payload["selected_specialists"] = [
            {
                "role": role,
                "reason": f"Herramienta {ROLE_DEFINITIONS[role][0]} ejecutada por Google ADK en esta solicitud",
            }
            for role in executed_roles
        ]
        payload["adk_execution"] = {
            "runtime": "google_adk_runner",
            "session_id": session_id,
            "event_count": event_count,
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