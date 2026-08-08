from __future__ import annotations

import unicodedata

from healthia_one.clinical_intake import respond_to_clinical_intake
from healthia_one.context_compiler import compact_context_markdown, compile_query_context
from healthia_one.deterministic_router import respond as deterministic_respond
from healthia_one.models import ChatMessage, ChatResponse, PatientState
from healthia_one.safety import assess_text
from healthia_one.twin_runtime import record_interview_in_state


SOCIAL_ONLY = {
    "hola",
    "buenas",
    "buen dia",
    "buenos dias",
    "buenas tardes",
    "buenas noches",
    "como estas",
    "gracias",
    "muchas gracias",
    "ok",
    "okay",
}

DIRECT_SECTIONS = {
    "mis medicamentos",
    "mi tratamiento",
    "mis citas",
    "mi cita",
    "mis resultados",
    "mis documentos",
    "mi expediente",
    "mi genograma",
    "mi familia",
    "mi linea de salud",
    "mi linea de tiempo",
    "mi cronologia",
}

DIRECT_PREFIXES = (
    "muestrame mi ", "muestrame mis ",
    "mostrar mi ", "mostrar mis ",
    "ensename mi ", "ensename mis ",
    "abre mi ", "abre mis ",
    "abrir mi ", "abrir mis ",
    "lista mi ", "lista mis ",
    "listar mi ", "listar mis ",
    "quiero ver mi ", "quiero ver mis ",
    "llevame a mi ", "llevame a mis ",
    "organiza mi ", "organiza mis ",
    "organizar mi ", "organizar mis ",
    "prepara mi proxima consulta", "preparar mi proxima consulta",
    "prepara mi consulta", "preparar mi consulta",
)


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split()).strip(" .!?¡¿")


def _explicit_clinical_request(text: str) -> bool:
    normalized = _normalize(text)
    if any(exclusion in normalized for exclusion in ("preparar mi consulta", "prepara mi consulta", "proxima consulta", "agendar", "cita")):
        return False
    return any(
        phrase in normalized
        for phrase in (
            "quiero hacer una consulta",
            "quiero iniciar una consulta",
            "necesito una consulta medica",
            "quiero consultar por mi salud",
            "quiero que me evalues",
        )
    )


def _explicit_deterministic_action(text: str) -> bool:
    normalized = _normalize(text)
    return normalized in DIRECT_SECTIONS or normalized.startswith(DIRECT_PREFIXES)


def _social_response(text: str) -> ChatResponse | None:
    normalized = _normalize(text)
    if normalized not in SOCIAL_ONLY:
        return None
    if normalized in {"gracias", "muchas gracias"}:
        content = "Con gusto. ¿Hay algo más que quieras revisar?"
    elif normalized in {"ok", "okay"}:
        content = "Perfecto."
    else:
        content = "Hola, ¿cómo estás hoy?"
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="HealthIA",
            content=content,
            agent_plan=[],
            metadata={"llm_status": "not_needed", "agent_execution": "none", "semantic_route": "social"},
        )
    )


def _semantic_draft(state: PatientState, patient_text: str) -> ChatResponse:
    context = compile_query_context(state, patient_text)
    result_context = compact_context_markdown(context)
    content = (
        "Entendí tu pregunta. Voy a responder usando únicamente tu contexto de salud autorizado y sin asumir datos que no estén registrados."
    )
    if result_context:
        content += "\n\n" + result_context
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="HealthIA",
            content=content,
            agent_plan=[],
            metadata={
                "semantic_route": "model_required",
                "agent_execution": "on_demand",
                "compiled_result_ids": [item["id"] for item in context["relevant_results"]],
            },
        )
    )


def _record_completed_interview(state: PatientState, response: ChatResponse) -> ChatResponse:
    interview = response.message.metadata.get("clinical_interview")
    if not isinstance(interview, dict) or interview.get("status") != "completed":
        return response
    interview_id = str(interview.get("id") or "").strip()
    if not interview_id:
        return response
    record_interview_in_state(
        state,
        interview_id=interview_id,
        chief_complaint=str(interview.get("chief_complaint") or "Consulta de salud"),
        answers=interview.get("answers") if isinstance(interview.get("answers"), list) else [],
    )
    response.message.metadata["twin_updated"] = True
    response.message.metadata["twin_event_type"] = "clinical_interview_reported"
    return response


def respond(state: PatientState, patient_text: str) -> ChatResponse:
    """Single conversational front door.

    Deterministic safety always wins. Explicit navigation/data retrieval stays local
    and zero-token. Symptom intake can request Gemini-generated adaptive questions.
    Free language, relationships and longitudinal questions are left unresolved for
    the semantic model rather than being hijacked by a keyword router.
    """

    safety = assess_text(patient_text)
    if safety.must_stop_normal_flow:
        return deterministic_respond(state, patient_text)

    social = _social_response(patient_text)
    if social is not None:
        return social

    clinical_response = respond_to_clinical_intake(state, patient_text)
    if clinical_response is not None:
        return _record_completed_interview(state, clinical_response)

    if _explicit_clinical_request(patient_text):
        clinical_response = respond_to_clinical_intake(
            state,
            f"Paciente presenta una molestia no especificada y solicita consulta: {patient_text}",
        )
        if clinical_response is not None:
            interview = clinical_response.message.metadata.get("clinical_interview", {})
            interview["chief_complaint"] = patient_text
            return _record_completed_interview(state, clinical_response)

    if _explicit_deterministic_action(patient_text):
        return deterministic_respond(state, patient_text)

    return _semantic_draft(state, patient_text)
