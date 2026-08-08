from __future__ import annotations

from healthia_one.clinical_intake import ANSWER_PREFIX, respond_to_clinical_intake
from healthia_one.conversation_brain import build_frame
from healthia_one.deterministic_router import respond as deterministic_respond
from healthia_one.models import ChatResponse, PatientState


ENGLISH_INTENT_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("medication", "medicine", "pill", "dose", "treatment"), "medicamento tratamiento dosis"),
    (("appointment", "visit", "specialist", "doctor visit"), "cita consulta especialista"),
    (("timeline", "health history", "full history"), "línea de tiempo historia completa"),
    (("family", "genogram", "hereditary", "family history"), "familia genograma antecedente familiar"),
    (("result", "results", "laboratory", "lab report", "scan", "imaging", "x-ray", "ultrasound"), "resultado laboratorio informe"),
    (("document", "documents", "file", "record", "report"), "documento archivo expediente"),
    (("weight", "gained weight", "lost weight"), "peso"),
    (("blood pressure", "hypertension"), "presión"),
    (("activity", "exercise", "walking", "steps"), "actividad pasos ejercicio"),
)

ENGLISH_SYMPTOM_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("pain when urinating", "burning when urinating", "urinary frequency", "urinate often"), "me arde al orinar desde ayer"),
    (("chest pain", "chest pressure"), "tengo dolor en el pecho"),
    (("shortness of breath", "difficulty breathing"), "tengo falta de aire"),
    (("headache",), "tengo dolor de cabeza"),
    (("abdominal pain", "stomach pain"), "tengo dolor abdominal"),
    (("back pain", "low back pain", "flank pain"), "tengo dolor lumbar"),
    (("fever",), "tengo fiebre"),
    (("vomiting", "vomit"), "tengo vómito"),
    (("nausea",), "tengo náusea"),
    (("dizziness", "dizzy"), "tengo mareo"),
    (("cough",), "tengo tos"),
    (("diarrhea",), "tengo diarrea"),
    (("bleeding",), "tengo sangrado"),
    (("weakness",), "tengo debilidad"),
    (("rash",), "tengo erupción"),
    (("swelling",), "tengo hinchazón"),
    (("palpitations",), "tengo palpitaciones"),
)


def _append_aliases(text: str, aliases: tuple[tuple[tuple[str, ...], str], ...]) -> str:
    if text.startswith(ANSWER_PREFIX):
        return text
    lower = text.lower()
    hints = [alias for signals, alias in aliases if any(signal in lower for signal in signals)]
    return text if not hints else f"{text} | {' | '.join(hints)}"


def _clinical_text(text: str) -> str:
    return _append_aliases(text, ENGLISH_SYMPTOM_ALIASES)


def _router_text(text: str) -> str:
    return _append_aliases(text, ENGLISH_INTENT_ALIASES)


def _explicit_clinical_request(text: str) -> bool:
    normalized = text.lower().strip()
    if any(exclusion in normalized for exclusion in (
        "preparar mi consulta", "prepara mi consulta", "próxima consulta", "proxima consulta", "agendar", "cita",
        "prepare my visit", "prepare my appointment", "schedule", "appointment",
    )):
        return False
    return any(
        phrase in normalized
        for phrase in (
            "quiero hacer una consulta",
            "quiero iniciar una consulta",
            "necesito una consulta médica",
            "necesito una consulta medica",
            "quiero consultar por mi salud",
            "quiero que me evalúes",
            "quiero que me evalues",
            "i want a health consultation",
            "i want to start a consultation",
            "i need a medical consultation",
            "i want to discuss a health problem",
            "i want you to evaluate my symptoms",
        )
    )


def _restore_original_complaint(response: ChatResponse | None, original: str) -> ChatResponse | None:
    if response is None or original.startswith(ANSWER_PREFIX):
        return response
    interview = response.message.metadata.get("clinical_interview")
    if isinstance(interview, dict) and interview.get("chief_complaint"):
        interview["chief_complaint"] = original
    return response


def _attach_conversation_frame(response: ChatResponse, frame) -> ChatResponse:
    response.message.metadata["conversation_context"] = {
        "ambiguous_reference": frame.ambiguous_reference,
        "correction": frame.correction,
        "last_action_target": frame.last_action_target,
        "last_mission_type": frame.last_mission_type,
    }
    return response


def respond(state: PatientState, patient_text: str) -> ChatResponse:
    """Route through safety and selective conversational memory before keyword fallback.

    Explicit current-turn meaning always wins. When a follow-up is elliptical (for
    example "¿y eso?" or "the one from yesterday"), Conversation Brain carries
    forward only the latest verified topic as a private routing hint. The public
    patient text is never rewritten or stored with that hint.
    """

    frame = build_frame(state, patient_text)
    routed_text = frame.routing_text

    clinical_response = respond_to_clinical_intake(state, _clinical_text(routed_text))
    clinical_response = _restore_original_complaint(clinical_response, patient_text)
    if clinical_response is not None:
        return _attach_conversation_frame(clinical_response, frame)

    if _explicit_clinical_request(patient_text):
        clinical_response = respond_to_clinical_intake(
            state,
            f"Paciente presenta una molestia no especificada y solicita consulta: {patient_text}",
        )
        if clinical_response is not None:
            interview = clinical_response.message.metadata.get("clinical_interview", {})
            interview["chief_complaint"] = patient_text
            return _attach_conversation_frame(clinical_response, frame)

    response = deterministic_respond(state, _router_text(routed_text))
    return _attach_conversation_frame(response, frame)
