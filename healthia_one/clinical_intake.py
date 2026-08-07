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
    "me duele", "tengo dolor", "tengo fiebre", "me arde", "siento", "presento",
    "paciente viene", "paciente presenta", "desde ayer", "desde hace", "empeora",
    "vomito", "vómito", "nausea", "náusea", "mareo", "tos", "diarrea", "sangrado",
    "debilidad", "dificultad para respirar", "falta de aire", "dolor de cabeza",
    "dolor de garganta", "dolor abdominal", "dolor lumbar", "orinar", "erupcion",
    "erupción", "hinchazon", "hinchazón", "palpitaciones",
)

DOMAIN_SIGNALS: dict[str, tuple[str, ...]] = {
    "respiratory": ("tos", "garganta", "congestion", "congestión", "ronquera", "respirar", "falta de aire", "pecho"),
    "urinary": ("orinar", "orina", "urinario", "ardor", "frecuencia urinaria", "flanco"),
    "gastrointestinal": ("abdomen", "abdominal", "diarrea", "vomito", "vómito", "nausea", "náusea", "estomago", "estómago"),
    "neurologic": ("cabeza", "cefalea", "mareo", "debilidad", "hablar", "vision", "visión", "desmayo", "confusion", "confusión"),
    "musculoskeletal": ("espalda", "lumbar", "articulacion", "articulación", "musculo", "músculo", "rodilla", "hombro"),
    "skin": ("piel", "erupcion", "erupción", "picor", "comezon", "comezón", "lesion", "lesión"),
}

DOMAIN_OPTIONS: dict[str, list[str]] = {
    "respiratory": ["Fiebre", "Tos", "Dolor de garganta", "Congestión o secreción nasal", "Dificultad para respirar", "Dolor de pecho"],
    "urinary": ["Ardor al orinar", "Orino con más frecuencia", "Urgencia urinaria", "Dolor bajo del abdomen", "Dolor lumbar o en el flanco", "Sangre visible en la orina"],
    "gastrointestinal": ["Dolor abdominal", "Náuseas", "Vómitos", "Diarrea", "Estreñimiento", "Sangre en vómito o heces"],
    "neurologic": ["Dolor de cabeza", "Mareo", "Visión alterada", "Debilidad o adormecimiento", "Dificultad para hablar", "Desmayo o confusión"],
    "musculoskeletal": ["Dolor localizado", "Rigidez", "Inflamación", "Traumatismo", "Limitación de movimiento", "Debilidad"],
    "skin": ["Erupción", "Picazón", "Dolor", "Ampollas", "Secreción", "Fiebre asociada"],
    "general": ["Dolor", "Fiebre", "Cansancio", "Mareo", "Náuseas o vómitos", "Otro síntoma"],
}


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


def _plan() -> list[AgentStep]:
    """Safe fallback only: two capabilities, never a permanent six-agent council.

    Gemini may replace this with a smaller/different case-specific plan. Keeping
    the deterministic fallback minimal prevents mock/local mode from pretending
    that every specialist ran for every symptom.
    """
    return [
        AgentStep(agent="INTERVIEWER", action="Aclarar únicamente los datos que faltan", reason="Entrevista clínica adaptativa", status="completed"),
        AgentStep(agent="SENTINEL", action="Comprobar señales de alarma específicas", reason="Seguridad clínica", status="completed"),
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

    domain_scores = {domain: sum(1 for signal in signals if _normalize(signal) in normalized) for domain, signals in DOMAIN_SIGNALS.items()}
    domain = max(domain_scores, key=domain_scores.get)
    if domain_scores[domain] == 0:
        domain = "general"
    return True, domain


def _question(question_id: str, prompt: str, options: list[str], *, multiple: bool = False, detail: str = "Puedes agregar un detalle") -> dict[str, Any]:
    return {"id": question_id, "prompt": prompt, "options": options, "multiple": multiple, "allow_detail": True, "detail_placeholder": detail}


def question_block(stage: int, domain: str) -> dict[str, Any]:
    """Deterministic safety fallback.

    In guarded Gemini mode this block is replaced by one generated from the
    actual complaint, previous answers and authorized longitudinal context.
    """
    if stage == 1:
        questions = [
            _question("onset", "¿Cuándo comenzó y cómo ha evolucionado?", ["Hoy", "1 a 3 días", "4 a 7 días", "Más de una semana", "No estoy seguro"], detail="Describe el inicio o algún cambio importante"),
            _question("symptoms", "¿Qué síntomas están presentes?", DOMAIN_OPTIONS.get(domain, DOMAIN_OPTIONS["general"]), multiple=True, detail="Agrega cualquier síntoma que no aparezca en la lista"),
            _question("severity", "¿Qué intensidad tiene y cuánto limita tus actividades?", ["Leve", "Moderada", "Intensa", "Me impide actividades habituales", "No puedo valorarlo"], detail="Indica una escala de 0 a 10 si la conoces"),
            _question("red_flags", "En las últimas horas, ¿cuál de estas señales ha ocurrido?", ["Ninguna de las anteriores", "Dificultad marcada para respirar", "Dolor fuerte en el pecho", "Desmayo o confusión", "Debilidad de un lado o dificultad para hablar", "Sangrado importante", "Empeoramiento rápido"], multiple=True, detail="Describe la señal y cuándo ocurrió"),
            _question("medications_allergies", "¿Qué has tomado y qué alergias debemos considerar?", ["No he tomado nada", "Medicamento sin receta", "Medicamento recetado", "Tengo alergias conocidas", "No tengo alergias conocidas", "No estoy seguro"], multiple=True, detail="Escribe nombres, dosis conocidas y alergias"),
        ]
    else:
        associated = {
            "respiratory": ["Placas o pus en garganta", "Ronquera", "Dolor al tragar", "Oídos tapados o dolor", "Contacto con personas enfermas", "Ninguno"],
            "urinary": ["Fiebre o escalofríos", "Dolor en flanco", "Náuseas o vómitos", "Flujo o irritación genital", "Embarazo posible", "Ninguno"],
            "gastrointestinal": ["Fiebre", "Pérdida de apetito", "Distensión", "Dolor localizado", "Alimentos sospechosos", "Ninguno"],
            "neurologic": ["Alteración visual", "Debilidad", "Dificultad para hablar", "Fiebre o rigidez de cuello", "Traumatismo reciente", "Ninguno"],
            "general": ["Fiebre", "Pérdida de apetito", "Cambios urinarios", "Cambios intestinales", "Erupción", "Ninguno"],
        }.get(domain, ["Fiebre", "Cansancio", "Inflamación", "Traumatismo", "Otro síntoma", "Ninguno"])
        questions = [
            _question("modifiers", "¿Qué lo desencadena, empeora o alivia?", ["Actividad", "Alimentos", "Posición o movimiento", "Medicamentos", "Reposo", "No identifico un patrón"], multiple=True, detail="Explica qué ocurre antes o después"),
            _question("associated", "¿Qué otros datos acompañan el problema?", associated, multiple=True, detail="Agrega otros síntomas o exposiciones"),
            _question("history", "¿Qué antecedentes podrían ser relevantes?", ["Ninguno conocido", "Enfermedad crónica", "Cirugía u hospitalización", "Embarazo o puerperio", "Episodio parecido anterior", "Antecedente familiar importante"], multiple=True, detail="Describe el antecedente y cuándo ocurrió"),
            _question("vitals", "¿Qué signos vitales o mediciones están disponibles?", ["No disponibles", "Temperatura", "Presión arterial", "Frecuencia cardiaca", "Oxígeno", "Glucosa"], multiple=True, detail="Escribe los valores y la hora si los tienes"),
            _question("goal", "¿Qué necesitas resolver primero?", ["Saber si es urgente", "Entender posibles explicaciones", "Preparar una consulta", "Organizar tratamiento actual", "Revisar resultados o documentos", "Planificar seguimiento"], multiple=True, detail="Cuéntame qué te preocupa más"),
        ]
    return {
        "stage": stage,
        "title": f"Preguntas para aclarar tu consulta · bloque {stage}",
        "instruction": "Estas preguntas cambian según lo que ya sabemos. Puedes ampliar cualquier respuesta.",
        "questions": questions,
        "submit_label": "Continuar" if stage == 1 else "Revisar lo conversado",
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
    alarms = ("dificultad marcada", "dolor fuerte en el pecho", "desmayo", "confusión", "debilidad de un lado", "sangrado importante", "empeoramiento rápido")
    return any(alarm in values for alarm in alarms)


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
        mission = next((item for item in state.missions if item.id == active.get("mission_id")), None)
        if stage == 1:
            block = question_block(2, domain)
            if mission:
                mission.next_action = "Aclarar únicamente lo que aún falta para orientar el siguiente paso"
            message = ChatMessage(
                role="assistant",
                author="HealthIA",
                content="Gracias. Con eso ya tengo una parte importante. Voy a preguntarte solo lo que todavía falta aclarar.",
                mission_id=mission.id if mission else None,
                agent_plan=_plan(),
                metadata={
                    "intent": "clinical_consultation",
                    "clinical_interview": {
                        "id": active["id"], "mission_id": active.get("mission_id"),
                        "chief_complaint": active.get("chief_complaint", "Consulta de salud"),
                        "domain": domain, "stage": 2, "status": "awaiting_answers",
                        "previous_answers": answer.get("answers", []), "question_block": block,
                    },
                },
            )
            return ChatResponse(message=message, mission=mission)

        previous = active.get("previous_answers", [])
        all_payload = {"answers": [*previous, *answer.get("answers", [])]}
        lines = _answer_lines(all_payload)
        alarm = _has_alarm(all_payload)
        risk = RiskLevel.PRIORITY if alarm else RiskLevel.INFO
        if mission:
            mission.status = MissionStatus.WAITING_PROFESSIONAL
            mission.risk_level = risk
            mission.next_action = "Revisar la síntesis clínica y confirmar el nivel de atención con un profesional"
            mission.closure_evidence = ["adaptive_interview_completed"]
        urgency = (
            "Aparece al menos una señal que requiere valoración humana prioritaria. No esperes una conclusión del chat si el síntoma está activo o empeora."
            if alarm else "No apareció una señal de alarma mayor en tus respuestas, aunque eso no descarta un problema importante."
        )
        content = (
            "### Lo que entendí de tu consulta\n\n"
            f"**Motivo inicial:** {active.get('chief_complaint', 'Consulta de salud')}\n\n"
            + "\n".join(lines) + "\n\n"
            f"**Seguridad:** {urgency}\n\n"
            "Con esto puedo seguir conversando contigo usando lo que ya sabemos y, si hace falta, preparar un resumen para revisión profesional. No confirmaré un diagnóstico ni modificaré tratamiento por mi cuenta."
        )
        message = ChatMessage(
            role="assistant", author="HealthIA", content=content, risk_level=risk,
            mission_id=mission.id if mission else None, agent_plan=_plan(),
            metadata={
                "intent": "clinical_consultation",
                "clinical_interview": {
                    "id": active["id"], "mission_id": active.get("mission_id"),
                    "chief_complaint": active.get("chief_complaint", "Consulta de salud"),
                    "domain": domain, "stage": 2, "status": "completed", "answers": all_payload["answers"],
                },
                "council_status": "completed", "action_target": "missions",
            },
        )
        return ChatResponse(message=message, mission=mission)

    is_consultation, domain = detect_clinical_consultation(patient_text)
    if not is_consultation:
        return None

    interview_id = f"interview_{uuid4().hex[:12]}"
    plan = _plan()
    mission = HealthMission(
        title="Aclarar la consulta clínica del paciente",
        mission_type="clinical_interview",
        status=MissionStatus.WAITING_PATIENT,
        next_action="Responder las preguntas adaptadas al motivo actual",
        agent_plan=plan,
    )
    state.missions.append(mission)
    block = question_block(1, domain)
    message = ChatMessage(
        role="assistant", author="HealthIA",
        content="Entendí el problema. Voy a preguntarte lo que más cambia la orientación y la seguridad, sin hacerte repetir datos que ya estén en tu historia.",
        mission_id=mission.id, agent_plan=plan,
        metadata={
            "intent": "clinical_consultation", "action_target": "clinical_interview",
            "clinical_interview": {
                "id": interview_id, "mission_id": mission.id, "chief_complaint": patient_text,
                "domain": domain, "stage": 1, "status": "awaiting_answers", "question_block": block,
            },
        },
    )
    return ChatResponse(message=message, mission=mission)
