from __future__ import annotations

import json
import re
import unicodedata
from typing import Any
from uuid import uuid4

from healthia_one.models import AgentStep, ChatMessage, ChatResponse, HealthMission, MissionStatus, PatientState, RiskLevel
from healthia_one.safety import assess_text

ANSWER_PREFIX = "[ENTREVISTA_CLINICA]"

NON_CLINICAL_INTENTS = (
    "mi expediente",
    "mis documentos",
    "mi tratamiento",
    "mis medicamentos",
    "mi cita",
    "mis citas",
    "mis resultados",
    "mi genograma",
    "mi familia",
    "mis permisos",
    "mi privacidad",
    "mi linea de salud",
    "mi línea de salud",
)

SYMPTOM_SIGNALS = (
    "me duele",
    "tengo dolor",
    "tengo fiebre",
    "me arde",
    "siento",
    "presento",
    "paciente viene",
    "paciente presenta",
    "desde ayer",
    "desde hace",
    "empeora",
    "vomito",
    "vómito",
    "nausea",
    "náusea",
    "mareo",
    "tos",
    "diarrea",
    "sangrado",
    "debilidad",
    "dificultad para respirar",
    "falta de aire",
    "dolor de cabeza",
    "dolor de garganta",
    "dolor abdominal",
    "dolor lumbar",
    "orinar",
    "erupcion",
    "erupción",
    "hinchazon",
    "hinchazón",
    "palpitaciones",
)

DOMAIN_SIGNALS: dict[str, tuple[str, ...]] = {
    "respiratory": ("tos", "garganta", "congestion", "congestión", "ronquera", "respirar", "falta de aire", "pecho"),
    "urinary": ("orinar", "orina", "urinario", "ardor", "frecuencia urinaria", "flanco"),
    "gastrointestinal": ("abdomen", "abdominal", "diarrea", "vomito", "vómito", "nausea", "náusea", "estomago", "estómago"),
    "neurologic": ("cabeza", "cefalea", "mareo", "debilidad", "hablar", "vision", "visión", "desmayo", "confusion", "confusión"),
    "musculoskeletal": ("espalda", "lumbar", "articulacion", "articulación", "musculo", "músculo", "rodilla", "hombro"),
    "skin": ("piel", "erupcion", "erupción", "picor", "comezon", "comezón", "lesion", "lesión"),
}

SOCIAL_PATTERNS: dict[str, tuple[str, ...]] = {
    "greeting": (
        "hola", "buenas", "buen dia", "buenos dias", "buenas tardes", "buenas noches",
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    ),
    "wellbeing": (
        "como vas", "como estas", "que tal", "como te va", "como va todo",
        "how are you", "how is it going", "how are things",
    ),
    "thanks": ("gracias", "muchas gracias", "te agradezco", "thank you", "thanks"),
    "farewell": ("adios", "hasta luego", "nos vemos", "hasta pronto", "chao", "chau", "bye", "goodbye", "see you"),
}
ENGLISH_SOCIAL_MARKERS = ("hello", "hi", "hey", "good ", "how are", "how is", "thank", "thanks", "bye", "goodbye", "see you")


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


def _plan() -> list[AgentStep]:
    """Initial safe shell only.

    The real Gemini/ADK path replaces this with the minimum set of tools actually
    executed for the current request. Keeping only the two mandatory areas here
    prevents a static six-agent council from masquerading as demand-driven work.
    """

    return [
        AgentStep(
            agent="INTERVIEWER",
            action="Identificar qué información falta para entender el motivo actual",
            reason="Entrevista clínica",
            status="completed",
        ),
        AgentStep(
            agent="SENTINEL",
            action="Comprobar señales de alarma antes de continuar",
            reason="Seguridad clínica",
            status="completed",
        ),
    ]


def detect_clinical_consultation(text: str) -> tuple[bool, str]:
    normalized = _normalize(text)
    if not normalized or normalized in {"hola", "buenas", "buen dia", "buenos dias", "como estas", "gracias"}:
        return False, "general"
    if any(_normalize(intent) in normalized for intent in NON_CLINICAL_INTENTS):
        return False, "general"

    score = sum(1 for signal in SYMPTOM_SIGNALS if _normalize(signal) in normalized)
    score += 1 if re.search(r"\b(duele|dolor|fiebre|ardor|mareo|tos|vomit|diarrea|sangr|debilidad|hinch)\w*\b", normalized) else 0
    score += 1 if re.search(r"\b(desde|hace)\s+(hoy|ayer|\d+|una|dos|tres|varios?)\b", normalized) else 0
    score += 1 if len(normalized.split()) >= 6 and any(token in normalized for token in ("paciente", "sintoma", "sintomas", "molestia")) else 0
    if score < 1:
        return False, "general"

    domain_scores = {
        domain: sum(1 for signal in signals if _normalize(signal) in normalized)
        for domain, signals in DOMAIN_SIGNALS.items()
    }
    domain = max(domain_scores, key=domain_scores.get)
    if domain_scores[domain] == 0:
        domain = "general"
    return True, domain


def respond_to_social_small_talk(state: PatientState, patient_text: str) -> ChatResponse | None:
    """Answer social turns locally so courtesy never becomes a clinical intake."""

    is_clinical, _ = detect_clinical_consultation(patient_text)
    if is_clinical:
        return None
    normalized = _normalize(patient_text)

    def contains_phrase(phrase: str) -> bool:
        return phrase in normalized if " " in phrase else bool(re.search(rf"\b{re.escape(phrase)}\b", normalized))

    intent = next(
        (name for name, phrases in SOCIAL_PATTERNS.items() if any(contains_phrase(phrase) for phrase in phrases)),
        None,
    )
    if intent is None:
        return None

    english = any(marker in normalized for marker in ENGLISH_SOCIAL_MARKERS)
    name = state.profile.display_name.split()[0] if state.profile.display_name else ""
    if english:
        responses = {
            "greeting": f"Hi{', ' + name if name else ''}. I’m here with you. What would you like help with today?",
            "wellbeing": "I’m here and ready to help. What would you like to review today?",
            "thanks": "You’re welcome. I’m here whenever you need help organizing a health question or record.",
            "farewell": "Take care. You can return whenever you want to review something from your health record.",
        }
    else:
        responses = {
            "greeting": f"Hola{', ' + name if name else ''}. Estoy aquí contigo. ¿Qué te gustaría revisar hoy?",
            "wellbeing": "Estoy aquí y lista para ayudarte. ¿Qué te gustaría revisar hoy?",
            "thanks": "Con gusto. Aquí estaré cuando quieras organizar una duda o revisar algo de tu expediente.",
            "farewell": "Cuídate. Puedes volver cuando quieras revisar algo de tu expediente.",
        }
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            author="HealthIA",
            content=responses[intent],
            metadata={
                "intent": "social_small_talk",
                "social_intent": intent,
                "skip_llm": "deterministic_social",
                "action_target": None,
            },
        )
    )


def question_scaffold(stage: int) -> dict[str, Any]:
    """State marker only; it deliberately contains no prefabricated questions."""

    return {
        "stage": stage,
        "title": f"Entrevista clínica adaptativa · bloque {stage}",
        "instruction": "HealthIA está preparando preguntas específicas con la información ya disponible.",
        "questions": [],
        "submit_label": "Continuar entrevista",
        "generation_required": True,
    }


def _latest_interview(state: PatientState) -> dict[str, Any] | None:
    for message in reversed(state.messages):
        if message.role != "assistant":
            continue
        interview = message.metadata.get("clinical_interview")
        if isinstance(interview, dict) and interview.get("status") == "awaiting_answers":
            return interview
    return None


def _parse_answer(text: str) -> dict[str, Any] | None:
    if not text.startswith(ANSWER_PREFIX):
        return None
    try:
        payload = json.loads(text[len(ANSWER_PREFIX):])
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _answer_lines(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for answer in payload.get("answers", []):
        if not isinstance(answer, dict):
            continue
        selected = [str(item) for item in answer.get("selected", []) if str(item).strip()]
        detail = str(answer.get("detail", "")).strip()
        value = ", ".join(selected)
        if detail:
            value = f"{value}. {detail}" if value else detail
        if value:
            label = str(answer.get("question_prompt") or answer.get("question_id") or "Dato clínico").strip()
            lines.append(f"- **{label}:** {value}")
    return lines


def _has_alarm(payload: dict[str, Any]) -> bool:
    values = " ".join(_answer_lines(payload)).lower()
    alarms = (
        "dificultad marcada",
        "dolor fuerte en el pecho",
        "desmayo",
        "confusión",
        "debilidad de un lado",
        "sangrado importante",
        "empeoramiento rápido",
    )
    return any(alarm in values for alarm in alarms)


def _clean_answers(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def respond_to_clinical_intake(state: PatientState, patient_text: str) -> ChatResponse | None:
    safety = assess_text(patient_text)
    if safety.must_stop_normal_flow:
        return None

    answer = _parse_answer(patient_text)
    active = _latest_interview(state)
    if answer is not None and active is not None:
        if answer.get("interview_id") != active.get("id"):
            return None

        stage = int(active.get("stage", 1))
        domain = str(active.get("domain", "general"))
        prior_answers = _clean_answers(active.get("previous_answers"))
        current_answers = _clean_answers(answer.get("answers"))
        accumulated = [*prior_answers, *current_answers]
        mission = next((item for item in state.missions if item.id == active.get("mission_id")), None)

        if stage == 1:
            message = ChatMessage(
                role="assistant",
                author="HealthIA",
                content=(
                    "Gracias. Ya tengo esa parte. Voy a usar tus respuestas junto con lo que contaste al inicio "
                    "para preguntarte únicamente lo que todavía haga falta aclarar."
                ),
                mission_id=mission.id if mission else None,
                agent_plan=_plan(),
                metadata={
                    "intent": "clinical_consultation",
                    "clinical_interview": {
                        "id": active["id"],
                        "mission_id": active.get("mission_id"),
                        "chief_complaint": active.get("chief_complaint", "Consulta de salud"),
                        "domain": domain,
                        "stage": 2,
                        "status": "awaiting_answers",
                        "previous_answers": accumulated,
                        "question_block": question_scaffold(2),
                    },
                },
            )
            return ChatResponse(message=message)

        all_payload = {"answers": accumulated}
        lines = _answer_lines(all_payload)
        alarm = _has_alarm(all_payload)
        risk = RiskLevel.PRIORITY if alarm else RiskLevel.INFO
        if mission:
            mission.status = MissionStatus.WAITING_PROFESSIONAL
            mission.risk_level = risk
            mission.next_action = "Completar la orientación clínica y confirmar el nivel de atención"
            mission.closure_evidence = ["adaptive_interview_answers_collected"]

        urgency = (
            "Aparece al menos una respuesta que puede requerir valoración humana prioritaria."
            if alarm
            else "No se marcó una señal de alarma mayor, aunque el formulario por sí solo no descarta un problema importante."
        )
        evidence_summary = "\n".join(lines) if lines else "- Respuestas clínicas recibidas y guardadas."
        content = (
            "Ya reuní la información de esta parte de la entrevista. "
            "Ahora HealthIA debe decidir con IA si todavía falta una ronda específica de preguntas "
            "o si ya puede darte una orientación clara.\n\n"
            f"**Seguridad hasta ahora:** {urgency}\n\n"
            f"{evidence_summary}"
        )
        message = ChatMessage(
            role="assistant",
            author="HealthIA",
            content=content,
            risk_level=risk,
            mission_id=mission.id if mission else None,
            agent_plan=_plan(),
            metadata={
                "intent": "clinical_consultation",
                "clinical_interview": {
                    "id": active["id"],
                    "mission_id": active.get("mission_id"),
                    "chief_complaint": active.get("chief_complaint", "Consulta de salud"),
                    "domain": domain,
                    "stage": stage,
                    "status": "ready_for_synthesis",
                    "answers": accumulated,
                    "previous_answers": accumulated,
                },
                "council_status": "awaiting_ai_resolution",
                "action_target": "clinical_interview",
            },
        )
        return ChatResponse(message=message)

    is_consultation, domain = detect_clinical_consultation(patient_text)
    if not is_consultation:
        return None

    interview_id = f"interview_{uuid4().hex[:12]}"
    plan = _plan()
    mission = HealthMission(
        title="Comprender el problema actual y orientar el siguiente paso",
        mission_type="clinical_interview",
        status=MissionStatus.WAITING_PATIENT,
        next_action="Responder las preguntas adaptativas generadas para este caso",
        agent_plan=plan,
    )
    state.missions.append(mission)
    message = ChatMessage(
        role="assistant",
        author="HealthIA",
        content=(
            "Entendí lo que te está pasando. Voy a usar lo que acabas de contar y tu información autorizada "
            "para preguntarte solo lo que realmente haga falta antes de orientarte."
        ),
        mission_id=mission.id,
        agent_plan=plan,
        metadata={
            "intent": "clinical_consultation",
            "action_target": "clinical_interview",
            "clinical_interview": {
                "id": interview_id,
                "mission_id": mission.id,
                "chief_complaint": patient_text,
                "domain": domain,
                "stage": 1,
                "status": "awaiting_answers",
                "previous_answers": [],
                "question_block": question_scaffold(1),
            },
        },
    )
    return ChatResponse(message=message, mission=mission)
