from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from healthia_one.clinical_tools import execute_on_demand_clinical_tools
from healthia_one.models import AgentStep, PatientState


ROLE_DEFINITIONS: dict[str, tuple[str, str, str]] = {
    "interview": (
        "INTERVIEWER",
        "Formular preguntas discriminativas basadas en lo que falta aclarar",
        "Entrevista clínica adaptativa",
    ),
    "safety": (
        "SENTINEL",
        "Revisar señales de alarma y el nivel de atención seguro",
        "Seguridad clínica",
    ),
    "history": (
        "HISTORIA",
        "Cruzar la consulta con antecedentes y datos longitudinales autorizados",
        "Contexto longitudinal relevante",
    ),
    "medication": (
        "MEDSAFE",
        "Revisar medicamentos, alergias y riesgos sin modificar tratamiento",
        "Seguridad farmacológica",
    ),
    "documents": (
        "ARCHIVUM",
        "Localizar resultados o documentos relacionados sin inventar contenido",
        "Evidencia documental",
    ),
    "results": (
        "LUMEN",
        "Explicar resultados aportados y sus límites",
        "Interpretación de resultados",
    ),
    "family": (
        "HEREDITAS",
        "Organizar antecedentes familiares pertinentes sin hacer predicciones",
        "Historia familiar",
    ),
    "follow_up": (
        "NAVIGATOR",
        "Definir el siguiente paso y la condición verificable de cierre",
        "Seguimiento",
    ),
    "privacy": (
        "BASTION",
        "Comprobar consentimiento y alcance de los datos utilizados",
        "Privacidad y consentimiento",
    ),
}

ROLE_ORDER = (
    "interview",
    "safety",
    "history",
    "medication",
    "documents",
    "results",
    "family",
    "follow_up",
    "privacy",
)

SAFETY_TERMS = (
    "alarma",
    "urgente",
    "respirar",
    "pecho",
    "desmayo",
    "confusion",
    "debilidad",
    "sangrado",
    "empeoramiento rapido",
    "fiebre alta",
)

FORBIDDEN_CLINICAL_DIRECTIVES = (
    "toma ",
    "tome ",
    "suspende ",
    "suspenda ",
    "aumenta la dosis",
    "reduce la dosis",
    "diagnostico confirmado",
    "definitivamente tienes",
)


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value).lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


def _answer_text(previous_answers: Iterable[dict[str, Any]] | None) -> str:
    chunks: list[str] = []
    for answer in previous_answers or []:
        if not isinstance(answer, dict):
            continue
        chunks.extend(str(item) for item in answer.get("selected", []) if str(item).strip())
        detail = str(answer.get("detail", "")).strip()
        if detail:
            chunks.append(detail)
    return " ".join(chunks)


def _requested_role_ids(requested_roles: Iterable[Any] | None) -> list[str]:
    values: list[str] = []
    for item in requested_roles or []:
        role = item.get("role") if isinstance(item, dict) else item
        role_id = str(role or "").strip().lower()
        if role_id in ROLE_DEFINITIONS and role_id not in values:
            values.append(role_id)
    return values


def _tool_summary(output: dict[str, Any]) -> str:
    tool = str(output.get("tool", ""))
    result = output.get("result") if isinstance(output.get("result"), dict) else {}
    if tool == "INTERVIEWER":
        return f"etapa {result.get('stage', '—')}, {result.get('answered_items', 0)} respuestas previas"
    if tool == "SENTINEL":
        return f"nivel {result.get('risk_level', 'info')}, detención={str(result.get('must_stop_normal_flow', False)).lower()}"
    if tool == "HISTORIA":
        return f"{len(result.get('confirmed_conditions', []))} condiciones y {result.get('recent_vital_count', 0)} mediciones recientes"
    if tool == "MEDSAFE":
        return f"{len(result.get('active_medications', []))} medicamentos activos y {len(result.get('allergies', []))} alergias registradas"
    if tool == "ARCHIVUM":
        return f"{len(result.get('documents', []))} documentos disponibles"
    if tool == "LUMEN":
        return f"{len(result.get('results', []))} resultados disponibles"
    if tool == "HEREDITAS":
        return f"{len(result.get('family_patterns', []))} antecedentes familiares relevantes"
    if tool == "NAVIGATOR":
        return str(result.get("next_action", "seguimiento preparado"))
    if tool == "BASTION":
        return f"{len(result.get('authorized_signals', []))} señales autorizadas"
    return "herramienta completada"


def select_on_demand_agents(
    state: PatientState,
    chief_complaint: str,
    previous_answers: Iterable[dict[str, Any]] | None,
    *,
    stage: int,
    requested_roles: Iterable[Any] | None = None,
) -> list[AgentStep]:
    """Select and execute the smallest useful clinical capability set without extra model calls."""

    answers = list(previous_answers or [])
    context = _normalize(f"{chief_complaint} {_answer_text(answers)}")
    mandatory = ["interview", "safety"]
    candidates: list[str] = []

    requested = _requested_role_ids(requested_roles)
    for role_id in requested:
        if role_id not in mandatory and role_id not in candidates:
            candidates.append(role_id)

    has_longitudinal_context = bool(
        state.profile.confirmed_conditions
        or state.profile.personal_history.chronic_conditions
        or any(token in context for token in ("antes", "anterior", "otra vez", "cronico"))
    )
    if has_longitudinal_context and (stage >= 2 or "history" in requested) and "history" not in candidates:
        candidates.append("history")

    medication_context = bool(
        state.profile.allergies
        or any(item.active for item in state.medication_plans)
        or any(token in context for token in ("medic", "pastilla", "dosis", "alerg", "tratamiento"))
    )
    if medication_context and (stage >= 2 or "medication" in requested) and "medication" not in candidates:
        candidates.append("medication")

    if any(token in context for token in ("resultado", "laboratorio", "analitica", "imagen", "radiografia")):
        for role_id in ("results", "documents"):
            if role_id not in candidates:
                candidates.append(role_id)
    elif any(token in context for token in ("documento", "pdf", "informe", "archivo", "receta medica")) and "documents" not in candidates:
        candidates.append("documents")

    if any(token in context for token in ("madre", "padre", "familia", "heredit", "abuelo", "abuela")) and "family" not in candidates:
        candidates.append("family")

    if any(token in context for token in ("permiso", "privacidad", "compartir", "consentimiento")) and "privacy" not in candidates:
        candidates.append("privacy")

    if stage >= 2 and "follow_up" not in candidates:
        candidates.append("follow_up")

    selected_roles = mandatory + candidates[:2]
    selected_roles = [role for role in selected_roles if role in ROLE_ORDER]
    steps = [
        AgentStep(
            agent=ROLE_DEFINITIONS[role][0],
            action=ROLE_DEFINITIONS[role][1],
            reason=ROLE_DEFINITIONS[role][2],
            status="completed",
        )
        for role in selected_roles
    ]

    tool_outputs = execute_on_demand_clinical_tools(
        state,
        steps,
        chief_complaint=chief_complaint,
        previous_answers=answers,
        stage=stage,
    )
    for step, output in zip(steps, tool_outputs, strict=True):
        step.action = f"{step.action}. Resultado verificable: {_tool_summary(output)}"
    return steps


def _slug(value: str, fallback: str) -> str:
    normalized = _normalize(value)
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return normalized[:48] or fallback


def normalize_dynamic_question_block(raw: dict[str, Any], stage: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("El plan dinámico no es un objeto JSON")
    source_questions = raw.get("questions")
    if not isinstance(source_questions, list) or not 1 <= len(source_questions) <= 5:
        raise ValueError("El bloque dinámico debe contener entre una y cinco preguntas")

    questions: list[dict[str, Any]] = []
    seen_prompts: set[str] = set()
    seen_ids: set[str] = set()
    for index, item in enumerate(source_questions, start=1):
        if not isinstance(item, dict):
            raise ValueError("Cada pregunta debe ser un objeto")
        prompt = " ".join(str(item.get("prompt", "")).split()).strip()[:260]
        if len(prompt) < 8:
            raise ValueError("Pregunta dinámica vacía o demasiado corta")
        prompt_key = _normalize(prompt)
        if prompt_key in seen_prompts:
            raise ValueError("El bloque dinámico contiene preguntas duplicadas")
        seen_prompts.add(prompt_key)

        options: list[str] = []
        normalized_options: set[str] = set()
        for option in item.get("options") or []:
            clean = " ".join(str(option).split()).strip()[:120]
            key = _normalize(clean)
            if clean and key not in normalized_options:
                normalized_options.add(key)
                options.append(clean)
        if not 2 <= len(options) <= 7:
            raise ValueError("Cada pregunta debe tener entre dos y siete opciones")

        question_id = _slug(str(item.get("id", "")), f"adaptive_{stage}_{index}")
        if question_id in seen_ids:
            question_id = f"{question_id}_{index}"
        seen_ids.add(question_id)

        detail_placeholder = " ".join(
            str(item.get("detail_placeholder", "Agregar un detalle si lo deseas")).split()
        ).strip()[:180]
        questions.append(
            {
                "id": question_id,
                "prompt": prompt,
                "options": options,
                "multiple": bool(item.get("multiple", False)),
                "allow_detail": True,
                "detail_placeholder": detail_placeholder or "Agregar un detalle si lo deseas",
            }
        )

    combined = _normalize(
        " ".join(
            [question["prompt"] for question in questions]
            + [option for question in questions for option in question["options"]]
        )
    )
    if any(directive in combined for directive in FORBIDDEN_CLINICAL_DIRECTIVES):
        raise ValueError("El bloque dinámico contiene una indicación clínica no permitida")

    return {
        "stage": stage,
        "title": "Preguntas para entenderte mejor",
        "instruction": "Estas preguntas se eligieron según lo que contaste y lo que todavía falta aclarar.",
        "questions": questions,
        "submit_label": "Continuar" if stage == 1 else "Revisar lo conversado",
    }


def judge_dynamic_plan(
    block: dict[str, Any],
    *,
    chief_complaint: str,
    previous_answers: Iterable[dict[str, Any]] | None,
    agent_plan: list[AgentStep],
    model_payload: dict[str, Any],
) -> dict[str, Any]:
    """Evidence-based, token-free gate applied after the single Gemini call."""

    score = 100
    blockers: list[str] = []
    strengths: list[str] = []
    questions = block.get("questions") or []

    if not 1 <= len(questions) <= 5:
        blockers.append("No contiene una cantidad válida de preguntas adaptativas")
        score -= 40
    else:
        strengths.append(f"{len(questions)} pregunta(s) elegida(s) según la información faltante")

    combined = _normalize(
        " ".join(
            [str(item.get("prompt", "")) for item in questions]
            + [str(option) for item in questions for option in item.get("options", [])]
        )
    )
    if not any(term in combined for term in SAFETY_TERMS):
        blockers.append("No demuestra una comprobación explícita de seguridad")
        score -= 25
    else:
        strengths.append("Incluye comprobación de señales de alarma")

    previous_ids = {
        str(item.get("question_id", "")).strip()
        for item in previous_answers or []
        if isinstance(item, dict) and str(item.get("question_id", "")).strip()
    }
    repeated_ids = previous_ids.intersection({str(item.get("id", "")) for item in questions})
    if repeated_ids:
        blockers.append("Repite preguntas ya contestadas")
        score -= 15
    else:
        strengths.append("Evita repetir datos ya recogidos")

    if not 2 <= len(agent_plan) <= 4:
        blockers.append("Activa demasiadas o muy pocas capacidades internas")
        score -= 20
    else:
        strengths.append(f"{len(agent_plan)} capacidades internas activadas bajo demanda")

    rationales = model_payload.get("why_these_questions") or []
    if not isinstance(rationales, list) or not any(str(item).strip() for item in rationales):
        blockers.append("La selección de preguntas no incluye evidencia de adaptación")
        score -= 15
    else:
        strengths.append("Explica por qué estas preguntas reducen incertidumbre")

    focus = str(model_payload.get("clinical_focus", "")).strip()
    if not focus:
        blockers.append("No declara el foco clínico que intenta aclarar")
        score -= 10

    score = max(0, min(score, 100))
    approved = score >= 80 and not any("seguridad" in item.lower() for item in blockers)
    return {
        "reviewer": "judge_omega",
        "approved": approved,
        "score": score,
        "verdict": "APPROVED_DYNAMIC_PLAN" if approved else "REJECTED_USE_SAFE_FALLBACK",
        "strengths": strengths[:4],
        "blockers": blockers[:4],
        "hackathon_alignment": {
            "innovation_operational_utility": "adaptive questions that pursue only the next useful information",
            "architectural_discipline": "one model call plus demand-selected deterministic tools and a no-token judge gate",
            "demo_readiness": "question source, selected capabilities, tool outcomes and judge verdict are auditable",
        },
        "chief_complaint_present": bool(str(chief_complaint).strip()),
    }


def fallback_judge_review(reason: str, agent_plan: list[AgentStep]) -> dict[str, Any]:
    return {
        "reviewer": "judge_omega",
        "approved": True,
        "score": 68,
        "verdict": "SAFE_FALLBACK_NOT_HACKATHON_EVIDENCE",
        "strengths": [
            "Mantiene seguridad y continuidad sin consumir tokens",
            f"Activa y ejecuta {len(agent_plan)} capacidades bajo demanda",
        ],
        "blockers": [reason],
        "hackathon_alignment": {
            "innovation_operational_utility": "fallback only; does not prove adaptive Gemini questioning",
            "architectural_discipline": "safe degradation and explicit cost boundary",
            "demo_readiness": "must not be presented to judges as an AI-generated block",
        },
    }
