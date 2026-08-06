from __future__ import annotations

import re
from collections import defaultdict

from healthia_one.models import AgentStep, FamilyMember, PatientState, ProactiveFinding, RiskLevel


def normalize_condition(value: str) -> str:
    text = re.sub(r"[^a-záéíóúñ0-9 ]+", " ", value.lower())
    aliases = {
        "hta": "hipertensión arterial",
        "hipertension": "hipertensión arterial",
        "diabetes mellitus": "diabetes",
        "dm2": "diabetes",
        "cancer de mama": "cáncer de mama",
        "cáncer mama": "cáncer de mama",
    }
    compact = " ".join(text.split())
    return aliases.get(compact, compact)


def family_summary(state: PatientState) -> dict:
    conditions: dict[str, list[dict]] = defaultdict(list)
    for member in state.family_members:
        if not member.biological_relative:
            continue
        for condition in member.conditions:
            key = normalize_condition(condition.name)
            conditions[key].append(
                {
                    "member_id": member.id,
                    "name": member.display_name,
                    "relation": member.relation,
                    "lineage": member.lineage,
                    "age_at_diagnosis": condition.age_at_diagnosis,
                    "confirmed": condition.confirmed,
                }
            )
    clusters = []
    for condition, relatives in sorted(conditions.items()):
        early = [item for item in relatives if item["age_at_diagnosis"] is not None and item["age_at_diagnosis"] < 50]
        if len(relatives) >= 2 or early:
            clusters.append(
                {
                    "condition": condition,
                    "relatives": relatives,
                    "relative_count": len(relatives),
                    "early_onset_count": len(early),
                }
            )
    return {
        "member_count": len(state.family_members),
        "biological_member_count": sum(item.biological_relative for item in state.family_members),
        "clusters": clusters,
        "truth_boundary": (
            "Los patrones familiares aportan contexto y preguntas de prevención; no determinan que el paciente tenga o desarrollará una enfermedad."
        ),
    }


def evaluate_family_history(state: PatientState) -> list[ProactiveFinding]:
    if "family_history" not in state.profile.consented_signal_types:
        return []
    summary = family_summary(state)
    findings: list[ProactiveFinding] = []
    for cluster in summary["clusters"]:
        relations = ", ".join(item["relation"] for item in cluster["relatives"][:4])
        key = f"family_cluster:{cluster['condition']}:{cluster['relative_count']}:{cluster['early_onset_count']}"
        findings.append(
            ProactiveFinding(
                key=key,
                title=f"Patrón familiar para contextualizar: {cluster['condition']}",
                risk_level=RiskLevel.INFO,
                summary=(
                    f"El genograma registra {cluster['relative_count']} familiares biológicos con "
                    f"{cluster['condition']} ({relations})."
                ),
                why_it_matters=(
                    "La agregación familiar puede ayudar a priorizar antecedentes, hábitos y preguntas de prevención, "
                    "pero no confirma una enfermedad ni sustituye una evaluación profesional."
                ),
                next_action=(
                    "Revisa si las edades de diagnóstico y la procedencia están correctas. HealthIA puede preparar "
                    "preguntas de prevención para tu próxima consulta."
                ),
                evidence_ids=[item["member_id"] for item in cluster["relatives"]],
                agent_plan=[
                    AgentStep(agent="HEREDITAS", action="Agrupar antecedentes familiares", reason="Línea biológica autorizada"),
                    AgentStep(agent="HISTORIA", action="Conectar con el expediente", reason="Contexto longitudinal"),
                    AgentStep(agent="SENTINEL", action="Aplicar límite de no diagnóstico", reason="Seguridad clínica"),
                    AgentStep(agent="KIRA", action="Preparar preguntas preventivas", reason="Continuidad del paciente"),
                ],
            )
        )
    return findings


def describe_genogram(members: list[FamilyMember]) -> str:
    if not members:
        return "No hay familiares registrados todavía. Puedes añadir parentesco, línea materna o paterna y patologías conocidas."
    lines = [f"El genograma contiene **{len(members)} familiares**."]
    for member in sorted(members, key=lambda item: (item.generation, item.lineage, item.relation)):
        conditions = ", ".join(condition.name for condition in member.conditions) or "sin patologías registradas"
        lines.append(f"- **{member.relation} ({member.display_name}):** {conditions}.")
    lines.append("\nLos antecedentes familiares orientan preguntas y prevención; no predicen por sí solos una enfermedad.")
    return "\n".join(lines)
