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
No diagnosticas ni recetas. Tu función es ejecutar el control clínico mínimo necesario y producir exactamente cinco preguntas adaptativas para el caso actual.

Contrato de ejecución:
1. Antes de responder debes llamar exactamente una vez a inspect_clinical_baseline.
2. Esa herramienta ejecuta conjuntamente las dos comprobaciones obligatorias del runtime: entrevista y seguridad.
3. No inventes resultados de herramientas. Usa exclusivamente lo que inspect_clinical_baseline devuelve y el contexto autorizado del mensaje.
4. No pidas otras herramientas en esta fase. El bloque inicial debe ser rápido, acotado y apto para una conversación de paciente.
5. No des la respuesta final antes de haber recibido el resultado de inspect_clinical_baseline.

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
  "selected_specialists": [
    {"role": "interview", "reason": "control clínico ejecutado por ADK"},
    {"role": "safety", "reason": "control clínico ejecutado por ADK"}
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
    """Low-latency per-request ADK coordinator over authorized PatientState.

    The previous runtime exposed nine independent function tools and required the
    model to call interview and safety separately. A clinically simple patient
    turn could therefore require several model/tool/model round trips before a
    five-question block was available. The production runtime now exposes one
    aggregate ADK function tool. ADK still performs a real tool call, while the
    tool executes the two mandatory deterministic clinical checks in one bounded
    operation. The role-level outputs remain separately audited as evidence.
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
            """Call exactly once before answering; runs mandatory interview and safety checks together."""
            nonlocal baseline_calls
            baseline_calls += 1
            return {
                "interview": execute_role("interview"),
                "safety": execute_role("safety"),
                "stage": stage,
                "previous_answer_count": len(previous_answers),
            }

        agent = LlmAgent(
            name="healthia_runtime_coordinator",
            model=Gemini(
                model=self.settings.model,
                retry_options=types.HttpRetryOptions(attempts=2),
            ),
            description="Low-latency demand-driven HealthIA coordinator over the current authorized patient state.",
            instruction=ADK_CLINICAL_INSTRUCTION,
            tools=[inspect_clinical_baseline],
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
                "must_execute_tool": "inspect_clinical_baseline",
                "maximum_adk_function_calls": 1,
                "mandatory_roles_inside_tool": ["interview", "safety"],
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
        if missing or baseline_calls != 1:
            correction = {
                "task": "repair_missing_mandatory_tool_execution",
                "instruction": (
                    "La respuesta anterior no es aceptable. Ejecuta exactamente una vez "
                    "inspect_clinical_baseline y, después de recibir su resultado, devuelve el objeto JSON "
                    "clínico completo con exactamente cinco preguntas. No llames la herramienta más de una vez."
                ),
                "original_task": prompt,
            }
            repaired_text = await run_turn(json.dumps(correction, ensure_ascii=False, default=str))
            if repaired_text:
                final_text = repaired_text

        missing = [role for role in mandatory if role not in executed_roles]
        if missing:
            raise ValueError("ADK no ejecutó las comprobaciones obligatorias: " + ", ".join(missing))
        if baseline_calls != 1:
            raise ValueError(f"ADK ejecutó inspect_clinical_baseline {baseline_calls} veces; se exige exactamente una")
        if tuple(executed_roles) != mandatory:
            raise ValueError(f"ADK ejecutó roles inesperados en el bloque de baja latencia: {executed_roles}")
        if not final_text:
            raise RuntimeError("Google ADK devolvió una respuesta clínica vacía")

        payload = self._parse_json(final_text)
        payload["selected_specialists"] = [
            {
                "role": role,
                "reason": f"Comprobación {ROLE_DEFINITIONS[role][0]} ejecutada dentro de inspect_clinical_baseline por Google ADK",
            }
            for role in executed_roles
        ]
        payload["adk_execution"] = {
            "runtime": "google_adk_runner",
            "session_id": session_id,
            "event_count": event_count,
            "function_tool": "inspect_clinical_baseline",
            "function_call_count": baseline_calls,
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
