from __future__ import annotations

import re

from healthia_one.continuity import build_timeline, consultation_brief, medication_summary
from healthia_one.devices import device_summary
from healthia_one.family import describe_genogram, family_summary
from healthia_one.models import (
    AgentStep,
    ChatMessage,
    ChatResponse,
    HealthMission,
    MissionStatus,
    PatientState,
    RiskLevel,
)
from healthia_one.result_search import conversational_result_context
from healthia_one.safety import assess_text


_RESULT_PHRASES = (
    "resultado", "laboratorio", "analítica", "analitica", "análisis", "analisis",
    "tomografía", "tomografia", "resonancia", "sonografía", "sonografia",
    "ecografía", "ecografia", "ultrasonido", "electrocardiograma",
    "radiografía", "radiografia", "biopsia",
)
_RESULT_TOKENS = {"tac", "tc", "ct", "mri", "rm", "ecg", "ekg", "rx", "xray"}


def _plan(*steps: tuple[str, str, str]) -> list[AgentStep]:
    return [AgentStep(agent=agent, action=action, reason=reason, status="completed") for agent, action, reason in steps]


def _mentions_result(text: str) -> bool:
    lower = text.lower()
    if any(phrase in lower for phrase in _RESULT_PHRASES):
        return True
    tokens = set(re.findall(r"[a-záéíóúñ0-9]+", lower))
    return bool(tokens & _RESULT_TOKENS)


def respond(state: PatientState, patient_text: str) -> ChatResponse:
    safety = assess_text(patient_text)
    if safety.must_stop_normal_flow:
        plan = _plan(
            ("SENTINEL", "Detectar lenguaje urgente", "Seguridad inmediata"),
            ("BASTION", "Bloquear flujo rutinario", "No retrasar atención"),
            ("KIRA", "Escalar al humano", "La IA no gestiona emergencias"),
        )
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                author="KIRA Health",
                content=safety.message,
                risk_level=RiskLevel.URGENT,
                agent_plan=plan,
            )
        )

    lower = patient_text.lower()
    profile = state.profile
    mission: HealthMission | None = None
    action_target: str | None = None

    if any(word in lower for word in ("medicamento", "medicación", "medicina", "pastilla", "tratamiento", "dosis", "toma")):
        plan = _plan(
            ("MEDSAFE", "Revisar tratamiento registrado y tomas reportadas", "Seguridad farmacológica"),
            ("HISTORIA", "Relacionar con síntomas y mediciones", "Contexto longitudinal"),
            ("SENTINEL", "Bloquear cambios de dosis", "Requiere criterio profesional"),
            ("KIRA", "Preparar preguntas y seguimiento", "Continuidad"),
        )
        summary = medication_summary(state)
        if summary["active_plans"]:
            labels = ", ".join(
                f"{item['name']} {item['strength']} ({item['schedule']})".strip()
                for item in summary["active_plans"]
            )
            adherence = summary["reported_adherence_percent"]
            content = f"Tienes registrado: **{labels}**. "
            if adherence is not None:
                content += f"En los registros recientes, la adherencia reportada es **{adherence:.1f}%**. "
            content += (
                "Este dato depende de lo informado por ti. No cambies, dupliques ni suspendas dosis desde el chat; "
                "puedo registrar una toma, una omisión o preparar una pregunta para tu profesional."
            )
            evidence = [item["id"] for item in summary["active_plans"]]
        else:
            content = "No hay tratamientos estructurados. Puedes añadir uno exactamente como fue indicado por tu profesional."
            evidence = []
        mission = HealthMission(
            title="Organizar tratamiento y adherencia",
            mission_type="medication_management",
            status=MissionStatus.WAITING_PATIENT,
            next_action="Registrar toma, omisión o duda sin modificar el esquema",
            evidence_ids=evidence,
            agent_plan=plan,
        )
        action_target = "treatment"
    elif any(word in lower for word in ("cita", "consulta", "médico", "medico", "especialista", "preparar consulta")):
        plan = _plan(
            ("ADVOCATE", "Preparar la voz del paciente", "Priorizar dudas y objetivos"),
            ("HISTORIA", "Resumir cambios recientes", "No empezar desde cero"),
            ("ARCHIVUM", "Reunir documentos", "Evitar información faltante"),
            ("NAVIGATOR", "Mantener cita y seguimiento", "Continuidad"),
        )
        brief = consultation_brief(state)
        appointment = brief["appointment"]
        if appointment:
            content = (
                f"Tu próxima cita es **{appointment['title']}**. Preparé un resumen con condiciones confirmadas, "
                f"tratamiento, mediciones, resultados, antecedentes familiares y **{len(brief['questions'])} preguntas**. "
                "Revísalo antes de compartirlo."
            )
            evidence = [appointment["id"]]
        else:
            content = "No veo una cita programada. Puedo registrar una y preparar el paquete de consulta."
            evidence = []
        mission = HealthMission(
            title="Preparar próxima consulta",
            mission_type="consultation_preparation",
            next_action="Revisar el resumen y confirmar documentos y preguntas",
            evidence_ids=evidence,
            agent_plan=plan,
        )
        action_target = "appointments"
    elif any(word in lower for word in ("línea de tiempo", "linea de tiempo", "cronología", "cronologia", "historia completa")):
        plan = _plan(
            ("HISTORIA", "Construir cronología unificada", "Continuidad longitudinal"),
            ("ARCHIVUM", "Integrar documentos y resultados", "Procedencia"),
            ("NAVIGATOR", "Conectar eventos y misiones", "Siguiente paso"),
        )
        events = build_timeline(state)
        latest = events[:5]
        content = f"Tu línea de salud contiene **{len(events)} eventos**. Los más recientes son:\n" + "\n".join(
            f"- **{item['title']}** — {item['detail']}" for item in latest
        )
        mission = HealthMission(
            title="Revisar línea de salud",
            mission_type="timeline_review",
            next_action="Abrir la cronología y seleccionar un evento",
            evidence_ids=[item["id"] for item in latest],
            agent_plan=plan,
        )
        action_target = "timeline"
    elif any(word in lower for word in ("familia", "familiar", "genograma", "herencia", "hereditario", "antecedente familiar")):
        plan = _plan(
            ("HEREDITAS", "Leer el genograma autorizado", "Contexto familiar"),
            ("HISTORIA", "Conectar familia y expediente", "Continuidad longitudinal"),
            ("SENTINEL", "Bloquear inferencias diagnósticas", "Seguridad clínica"),
            ("KIRA", "Preparar preguntas preventivas", "Próximo paso útil"),
        )
        summary = family_summary(state)
        content = describe_genogram(state.family_members)
        if summary["clusters"]:
            cluster_names = ", ".join(item["condition"] for item in summary["clusters"][:4])
            content += f"\n\n**Patrones que conviene contextualizar:** {cluster_names}. Esto no confirma riesgo individual."
        mission = HealthMission(
            title="Revisar historia familiar",
            mission_type="family_history",
            status=MissionStatus.WAITING_PATIENT,
            next_action="Confirmar parentescos, patologías y edades de diagnóstico",
            evidence_ids=[item.id for item in state.family_members],
            agent_plan=plan,
        )
        action_target = "family"
    elif any(word in lower for word in (
        "dispositivo", "reloj", "health connect", "báscula", "bascula", "tensiómetro",
        "tensiometro", "oxímetro", "oximetro", "wearable", "galaxy watch",
    )):
        summary = device_summary(state)
        active = [item for item in summary["connections"] if item["status"] == "connected"]
        plan = _plan(
            ("NAVIGATOR", "Revisar conexiones y permisos", "Control del paciente"),
            ("HISTORIA", "Comprobar datos sincronizados y procedencia", "Continuidad"),
            ("SENTINEL", "Mantener límites clínicos del sensor", "Seguridad"),
        )
        if active:
            connection = active[-1]
            granted = connection.get("permissions") or []
            permission_text = ", ".join(item.replace("_", " ") for item in granted) or "sin permisos informados"
            content = (
                f"Veo **{len(active)} conexión(es) activa(s)** y **{summary['record_count']} registros**. "
                f"La conexión más reciente es **{connection['display_name']}**; tipos autorizados: **{permission_text}**. "
                "Puedo abrir Dispositivos para revisar la última sincronización o desconectarla. "
                "El puente autentica el teléfono, pero no certifica clínicamente el sensor ni garantiza transmisión en tiempo real."
            )
            evidence = [connection["id"]]
            next_action = "Abrir Dispositivos, revisar permisos, actualizar o desconectar"
        else:
            content = (
                "No veo un dispositivo conectado. Abre **Dispositivos → Conectar dispositivo**, vincula el puente "
                "Android con el código temporal y concede solo los tipos que quieras compartir en Health Connect. "
                "Samsung, relojes, básculas o tensiómetros funcionan por esta vía únicamente si escriben sus datos en Health Connect."
            )
            evidence = []
            next_action = "Abrir Dispositivos y generar un código temporal"
        mission = HealthMission(
            title="Conectar y revisar dispositivo de salud",
            mission_type="device_connection",
            status=MissionStatus.WAITING_PATIENT,
            next_action=next_action,
            evidence_ids=evidence,
            agent_plan=plan,
        )
        action_target = "devices"
    elif _mentions_result(patient_text):
        plan = _plan(
            ("LUMEN", "Recuperar y explicar la evidencia solicitada", "Conversación anclada al resultado persistido"),
            ("HISTORIA", "Relacionar con la línea de tiempo y el gemelo", "Evitar interpretación aislada"),
            ("ARCHIVUM", "Conservar vínculo con el archivo original", "Procedencia verificable"),
            ("KIRA", "Cerrar o mantener abierta la misión según la evidencia", "Continuidad verificable"),
        )
        context = conversational_result_context(state, patient_text)
        if context:
            content = (
                f"Encontré **{context['panel']}** (`{context['filename']}`), cargado el **{context['uploaded_at'][:10]}**.\n\n"
                f"{context['explanation'] or 'El resultado está guardado, pero todavía no tiene una explicación verificable.'}"
            )
            if context["document_id"]:
                content += "\n\nEl archivo original sigue vinculado a este resultado y puede volver a abrirse desde Resultados."
            evidence = [context["result_id"]]
            closure_evidence = ["persisted_result_retrieved", "patient_explanation_returned"]
            if context["document_id"]:
                evidence.append(context["document_id"])
                closure_evidence.append("original_evidence_link_resolved")
            mission_status = MissionStatus.COMPLETED
            next_action = "Misión cerrada: resultado recuperado, explicado y vinculado a su evidencia persistida"
        else:
            content = "No veo resultados cargados todavía. Puedes adjuntar un JSON, CSV, TXT, PDF o imagen."
            evidence = []
            closure_evidence = []
            mission_status = MissionStatus.ACTIVE
            next_action = "Cargar el resultado que quieres revisar"
        mission = HealthMission(
            title="Comprender resultado de salud",
            mission_type="result_explanation",
            status=mission_status,
            next_action=next_action,
            evidence_ids=evidence,
            agent_plan=plan,
            closure_evidence=closure_evidence,
        )
        action_target = "results"
    elif any(word in lower for word in ("documento", "archivo", "expediente", "papel", "informe", "receta")):
        plan = _plan(
            ("ARCHIVUM", "Indexar documentación clínica", "Encontrar y organizar"),
            ("HISTORIA", "Relacionar con la línea de tiempo", "Evitar documentos aislados"),
            ("LUMEN", "Preparar explicación si aplica", "Lenguaje comprensible"),
            ("KIRA", "Definir siguiente acción", "Continuidad"),
        )
        if state.documents:
            content = f"Tu expediente tiene **{len(state.documents)} documentos organizados**. Puedo abrir el archivo o ayudarte a cargar uno nuevo."
            evidence = [item.id for item in state.documents[-5:]]
        else:
            content = "Todavía no hay documentos organizados. Puedes cargar laboratorios, imágenes, recetas, informes o notas."
            evidence = []
        mission = HealthMission(
            title="Organizar documentación del paciente",
            mission_type="document_management",
            next_action="Cargar o seleccionar el documento que necesitas",
            evidence_ids=evidence,
            agent_plan=plan,
        )
        action_target = "documents"
    elif any(word in lower for word in ("peso", "engord", "adelgaz")):
        plan = _plan(
            ("HISTORIA", "Revisar tendencia de peso", "Contexto longitudinal"),
            ("SENTINEL", "Comprobar síntomas de prioridad", "Seguridad"),
            ("VITA", "Explorar hábitos y barreras", "Plan realista"),
        )
        latest = state.weights[-1].weight_kg if state.weights else None
        content = (f"Tu último peso registrado es **{latest:.1f} kg**. " if latest is not None else "No veo un peso registrado. ") + (
            "Necesito saber si usaste la misma balanza y si hubo cambios de alimentación, actividad, hinchazón o falta de aire."
        )
        mission = HealthMission(
            title="Entender cambio de peso",
            mission_type="weight_followup",
            status=MissionStatus.WAITING_PATIENT,
            next_action="Registrar peso y responder preguntas de contexto",
            agent_plan=plan,
        )
        action_target = "measurements"
    elif any(word in lower for word in ("presión", "tension", "tensión")):
        plan = _plan(
            ("SENTINEL", "Revisar presión y síntomas", "Umbrales de seguridad"),
            ("NAVIGATOR", "Guiar técnica de medición", "Calidad del dato"),
            ("KIRA", "Mantener seguimiento", "Serie longitudinal"),
        )
        content = (
            "Registra la presión después de cinco minutos de reposo, espalda y brazo apoyados, y toma dos mediciones. "
            "Ante dolor de pecho, falta de aire, debilidad de un lado o dificultad para hablar, busca atención urgente."
        )
        mission = HealthMission(
            title="Seguimiento de presión arterial",
            mission_type="blood_pressure",
            status=MissionStatus.WAITING_PATIENT,
            next_action="Recibir dos mediciones y síntomas asociados",
            agent_plan=plan,
        )
        action_target = "measurements"
    elif any(word in lower for word in ("actividad", "caminar", "ejercicio", "pasos")):
        plan = _plan(
            ("VITA", "Revisar actividad y barreras", "Plan sostenible"),
            ("HISTORIA", "Comparar con registros previos", "Tendencia"),
            ("KIRA", "Proponer microobjetivo", "Evitar recomendaciones genéricas"),
        )
        recent = state.activity[-3:]
        content = (
            "Veo pocos registros de actividad. " if len(recent) < 3 else f"Tus últimos registros promedian **{sum(item.steps for item in recent)/len(recent):.0f} pasos**. "
        ) + "¿Qué barrera pesa más ahora: dolor, cansancio, tiempo, clima o ánimo?"
        mission = HealthMission(
            title="Plan de actividad realista",
            mission_type="activity_plan",
            status=MissionStatus.WAITING_PATIENT,
            next_action="Identificar barrera y acordar una meta pequeña",
            agent_plan=plan,
        )
        action_target = "measurements"
    else:
        plan = _plan(
            ("HISTORIA", "Recuperar contexto autorizado", "No empezar desde cero"),
            ("SENTINEL", "Comprobar señales de prioridad", "Seguridad"),
            ("KIRA", "Elegir el equipo mínimo", "Evitar agentes innecesarios"),
        )
        content = (
            f"Estoy contigo, {profile.display_name.split()[0]}. Puedo revisar tu historia, tratamiento, citas, familia, "
            "documentos, mediciones, resultados y misiones desde este chat. Cuéntame qué cambió y qué te preocupa más."
        )

    if mission:
        state.missions.append(mission)
    message = ChatMessage(
        role="assistant",
        author="KIRA Health",
        content=content,
        risk_level=RiskLevel.INFO,
        mission_id=mission.id if mission else None,
        agent_plan=plan,
        metadata={"action_target": action_target, "mission_type": mission.mission_type if mission else None},
    )
    return ChatResponse(message=message, mission=mission)
