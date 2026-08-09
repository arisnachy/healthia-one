from __future__ import annotations

import re

from healthia_one.clinical_intake import (
    ANSWER_PREFIX,
    detect_clinical_consultation,
    respond_to_clinical_intake,
    respond_to_social_small_talk,
)
from healthia_one.conversation_brain import build_frame
from healthia_one.deterministic_router import respond as deterministic_respond
from healthia_one.language import current_requested_locale, normalize_locale
from healthia_one.models import ChatMessage, ChatResponse, PatientState
from healthia_one.opportunity_integration import respond as opportunity_respond
from healthia_one.safety import assess_text


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
    (("device", "wearable", "health connect", "watch"), "dispositivo reloj health connect"),
    (("privacy", "permissions", "consent", "audit"), "privacidad permisos consentimiento auditoría"),
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

_UI_OPEN_VERBS = (
    "abre", "abrir", "muéstrame", "muestrame", "mostrar", "enséñame", "ensename", "ver", "ve a", "llévame", "llevame",
    "open", "show me", "show", "go to", "take me to", "view",
)
_UI_RECORD_VERBS = (
    "registrar", "registra", "anotar", "anota", "añadir", "agregar", "guardar", "quiero poner",
    "record", "log", "add", "save",
)
_UI_UPLOAD_VERBS = ("subir", "cargar", "adjuntar", "upload", "attach")

_UI_VIEW_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("results", ("resultado", "resultados", "results", "labs", "laboratorio")),
    ("measurements", ("mediciones", "medición", "medicion", "measurements", "vitals", "signos vitales")),
    ("profile", ("perfil", "mi perfil", "patient profile", "profile")),
    ("record", ("mi expediente", "expediente clínico", "expediente clinico", "my record", "health record")),
    ("missions", ("misiones", "health missions", "missions")),
    ("today", ("hoy", "today")),
    ("timeline", ("línea de salud", "linea de salud", "línea de tiempo", "linea de tiempo", "timeline")),
    ("treatment", ("tratamiento", "medicamentos", "medicación", "medicacion", "treatment", "medications")),
    ("appointments", ("citas", "cita", "appointments", "appointment")),
    ("family", ("genograma", "familia", "antecedentes familiares", "family", "genogram")),
    ("documents", ("documentos", "documento", "archivos", "documents", "files")),
    ("devices", ("dispositivos", "dispositivo", "health connect", "reloj", "devices", "wearable")),
    ("control", ("privacidad", "permisos", "consentimiento", "auditoría", "auditoria", "privacy", "permissions", "consent", "audit")),
)

_CONCRETE_CLINICAL_SIGNALS = (
    "me duele", "tengo dolor", "dolor", "tengo fiebre", "fiebre", "me arde", "ardor", "orinar",
    "vómito", "vomito", "náusea", "nausea", "mareo", "tos", "diarrea", "sangrado", "debilidad",
    "dificultad para respirar", "falta de aire", "erupción", "erupcion", "hinchazón", "hinchazon", "palpitaciones",
    "headache", "pain", "fever", "vomiting", "nausea", "dizziness", "cough", "diarrhea", "bleeding", "weakness",
    "shortness of breath", "difficulty breathing", "rash", "swelling", "palpitations",
)

_ENGLISH_MISSION_TITLES = {
    "clinical_interview": "Understand the current health problem and guide the next step",
    "result_explanation": "Understand a health result",
    "medication_management": "Organize treatment and adherence",
    "consultation_preparation": "Prepare the next appointment",
    "timeline_review": "Review the health timeline",
    "family_history": "Review family health history",
    "document_management": "Organize patient documents",
    "weight_followup": "Understand a weight change",
    "blood_pressure": "Review blood pressure",
    "activity_plan": "Review activity and movement",
    "device_connection": "Connect and review a health device",
}


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


def _automatic_structured_intake(text: str) -> bool:
    normalized = text.lower().strip()
    if not normalized or text.startswith(ANSWER_PREFIX):
        return False
    concrete = sum(1 for signal in _CONCRETE_CLINICAL_SIGNALS if signal in normalized)
    has_duration = bool(re.search(
        r"\b(desde|hace|llevo|empez[oó]|since|for)\b.{0,28}\b(hoy|ayer|today|yesterday|\d+|una|uno|dos|tres|horas?|d[ií]as?|semanas?|hours?|days?|weeks?)\b",
        normalized,
    ))
    has_case_language = any(term in normalized for term in (
        "síntoma", "sintoma", "síntomas", "sintomas", "molestia", "empeora", "empeorando",
        "symptom", "symptoms", "worse", "worsening",
    ))
    return concrete >= 2 or (concrete >= 1 and (has_duration or has_case_language))


def _contains_command_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, flags=re.IGNORECASE))


def _has_any_command_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains_command_phrase(text, phrase) for phrase in phrases)


def _requested_ui_action(text: str) -> dict[str, str] | None:
    normalized = text.lower().strip()
    if not normalized:
        return None

    wants_record = _has_any_command_phrase(normalized, _UI_RECORD_VERBS)
    if wants_record and any(term in normalized for term in ("presión", "presion", "tensión", "tension", "blood pressure", "vital", "signos vitales")):
        return {"type": "open_dialog", "view": "measurements", "dialog": "vital"}
    if wants_record and any(term in normalized for term in ("peso", "weight")):
        return {"type": "open_dialog", "view": "measurements", "dialog": "weight"}
    if wants_record and any(term in normalized for term in ("actividad", "pasos", "ejercicio", "activity", "steps", "exercise")):
        return {"type": "open_dialog", "view": "measurements", "dialog": "activity"}

    wants_upload = _has_any_command_phrase(normalized, _UI_UPLOAD_VERBS)
    if wants_upload and any(term in normalized for term in ("resultado", "laboratorio", "analítica", "analitica", "imagen", "result", "lab", "scan", "image")):
        return {"type": "pick_file", "view": "results", "picker": "result"}

    wants_open = _has_any_command_phrase(normalized, _UI_OPEN_VERBS)
    if wants_open:
        for view, terms in _UI_VIEW_TERMS:
            if any(term in normalized for term in terms):
                return {"type": "open_view", "view": view}
    return None


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


def _attach_ui_action(response: ChatResponse, ui_action: dict[str, str] | None) -> ChatResponse:
    if ui_action:
        response.message.metadata["ui_action"] = ui_action
        response.message.metadata["health_os_control"] = True
    return response


def _human_clinical_conversation(state: PatientState, patient_text: str) -> ChatResponse:
    safety = assess_text(patient_text)
    if safety.must_stop_normal_flow:
        return deterministic_respond(state, _router_text(patient_text))
    english = bool(re.search(r"\b(i|my|have|feel|pain|hurt|cough|fever|dizzy|headache)\b", patient_text.lower()))
    content = (
        "I hear you. We can talk through this naturally; I won't turn one symptom mention into a questionnaire. "
        "Tell me what changed or what worries you most right now, and I'll ask one useful thing at a time."
        if english else
        "Te escucho. Podemos hablar de esto de forma natural; no voy a convertir una sola mención de un síntoma en un formulario. "
        "Cuéntame qué cambió o qué es lo que más te preocupa ahora, y te iré preguntando una cosa útil a la vez."
    )
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="HealthIA",
            content=content,
            metadata={
                "intent": "clinical_conversation",
                "clinical_mode": "conversation_first",
                "structured_interview_started": False,
                "action_target": None,
            },
        )
    )


def _route_response(state: PatientState, patient_text: str) -> ChatResponse:
    safety = assess_text(patient_text)
    if safety.must_stop_normal_flow:
        frame = build_frame(state, patient_text)
        response = deterministic_respond(state, _router_text(patient_text))
        return _attach_conversation_frame(response, frame)

    opportunity_response = opportunity_respond(state, patient_text)
    if opportunity_response is not None:
        frame = build_frame(state, patient_text)
        return _attach_conversation_frame(opportunity_response, frame)

    social_response = respond_to_social_small_talk(state, _clinical_text(patient_text))
    if social_response is not None:
        frame = build_frame(state, patient_text)
        return _attach_conversation_frame(social_response, frame)

    frame = build_frame(state, patient_text)
    routed_text = frame.routing_text
    ui_action = _requested_ui_action(patient_text)

    if patient_text.startswith(ANSWER_PREFIX):
        clinical_response = respond_to_clinical_intake(state, patient_text)
        if clinical_response is not None:
            return _attach_conversation_frame(clinical_response, frame)

    if ui_action is not None:
        response = deterministic_respond(state, _router_text(routed_text))
        response = _attach_ui_action(response, ui_action)
        return _attach_conversation_frame(response, frame)

    if _explicit_clinical_request(patient_text) or _automatic_structured_intake(routed_text):
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

    is_clinical, _ = detect_clinical_consultation(_clinical_text(routed_text))
    if is_clinical:
        response = _human_clinical_conversation(state, patient_text)
        return _attach_conversation_frame(response, frame)

    response = deterministic_respond(state, _router_text(routed_text))
    return _attach_conversation_frame(response, frame)


def _mission_status_value(mission) -> str:
    value = getattr(mission.status, "value", mission.status)
    return str(value or "")


def _english_next_action(mission) -> str | None:
    status = _mission_status_value(mission)
    mission_type = str(mission.mission_type or "")
    if mission_type == "clinical_interview":
        if status == "waiting_professional":
            return "Complete the clinical orientation and confirm the appropriate level of care"
        return "Answer the adaptive questions generated for this case"
    if mission_type == "result_explanation":
        if status == "completed":
            return "Mission closed: result retrieved, explained, and linked to its persisted evidence"
        return "Upload the result you want to review"
    defaults = {
        "medication_management": "Record a dose, omission, or question without changing the prescribed plan",
        "consultation_preparation": "Review the summary and confirm documents and questions",
        "timeline_review": "Open the timeline and select an event",
        "family_history": "Confirm relationships, conditions, and age at diagnosis",
        "document_management": "Upload or select the document you need",
        "weight_followup": "Record weight and answer the context questions",
        "blood_pressure": "Review the measurement and any associated symptoms",
        "activity_plan": "Review the activity trend and choose the next realistic step",
        "device_connection": "Open Devices and review permissions or connection status",
    }
    return defaults.get(mission_type)


def _localize_state_missions(state: PatientState) -> None:
    locale = normalize_locale(current_requested_locale(), fallback="es")
    if locale != "en":
        return
    for mission in state.missions:
        title = _ENGLISH_MISSION_TITLES.get(str(mission.mission_type or ""))
        next_action = _english_next_action(mission)
        if title:
            mission.title = title
        if next_action:
            mission.next_action = next_action


def _persist_response_mission(state: PatientState, response: ChatResponse) -> ChatResponse:
    mission = response.mission
    if mission is None:
        return response
    mission.patient_id = state.profile.id
    response.message.mission_id = mission.id
    for index, existing in enumerate(state.missions):
        if existing.id == mission.id:
            state.missions[index] = mission
            break
    else:
        state.missions.append(mission)
    return response


def respond(state: PatientState, patient_text: str) -> ChatResponse:
    response = _persist_response_mission(state, _route_response(state, patient_text))
    _localize_state_missions(state)
    return response
