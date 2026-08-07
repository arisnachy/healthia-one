from __future__ import annotations

import re
import unicodedata
from typing import Any

from healthia_one.models import HealthResult, PatientState


STOPWORDS = {
    "que", "qué", "como", "cómo", "cuando", "cuándo", "donde", "dónde", "para", "por",
    "con", "sin", "una", "uno", "unos", "unas", "del", "las", "los", "mis", "me", "mi",
    "esto", "esta", "ese", "esa", "fue", "era", "dice", "decia", "decía", "subi", "subí",
    "resultado", "resultados", "archivo", "estudio",
}

RESULT_REFERENCE_TERMS = (
    "resultado", "laboratorio", "analitica", "analisis", "reporte", "informe", "estudio",
    "tomografia", "tac", "ct", "resonancia", "mri", "radiografia", "rayos x", "rx",
    "ecg", "ekg", "electrocardiograma", "ultrasonido", "sonografia", "imagen", "pdf",
    "lo que subi", "lo que te subi", "archivo que subi", "estudio que subi",
)


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(char for char in value if not unicodedata.combining(char))


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", _normalize(text))
        if token not in STOPWORDS
    }


def _result_text(result: HealthResult) -> str:
    items = " ".join(f"{item.name} {item.value} {item.unit} {item.flag or ''}" for item in result.items[:40])
    return " ".join([result.filename, result.panel, result.explanation, items])


def relevant_results(state: PatientState, query: str, *, limit: int = 3) -> list[HealthResult]:
    """Retrieve result artifacts deterministically before spending a model call.

    This is context retrieval, not an intent router. It never decides a diagnosis;
    it only chooses which already-persisted result records are relevant enough to
    include in the conversational context.
    """
    if not state.results:
        return []
    query_tokens = _tokens(query)
    normalized_query = _normalize(query)
    scored: list[tuple[int, int, HealthResult]] = []
    total = len(state.results)
    for index, result in enumerate(state.results):
        result_tokens = _tokens(_result_text(result))
        overlap = len(query_tokens & result_tokens)
        phrase_bonus = 0
        panel = _normalize(result.panel)
        filename = _normalize(result.filename)
        if panel and len(panel) > 4 and panel in normalized_query:
            phrase_bonus += 6
        stem = filename.rsplit(".", 1)[0]
        if stem and len(stem) > 4 and stem in normalized_query:
            phrase_bonus += 6
        recency = index - total
        scored.append((overlap * 3 + phrase_bonus, recency, result))

    matched = [item for score, _, item in sorted(scored, key=lambda row: (row[0], row[1]), reverse=True) if score > 0]
    if matched:
        return matched[:limit]

    # Generic references such as "¿qué decía la tomografía que subí?" may not
    # overlap a filename. Only then fall back to recent result artifacts; unrelated
    # conversation receives no result context and therefore spends fewer tokens.
    if any(term in normalized_query for term in RESULT_REFERENCE_TERMS):
        return list(reversed(state.results[-limit:]))
    return []


def compile_query_context(state: PatientState, query: str) -> dict[str, Any]:
    results = relevant_results(state, query)
    return {
        "relevant_results": [
            {
                "id": item.id,
                "filename": item.filename,
                "panel": item.panel,
                "status": item.status,
                "explanation": item.explanation,
                "source": item.source.model_dump(mode="json"),
                "items": [entry.model_dump(mode="json") for entry in item.items[:30]],
            }
            for item in results
        ],
        "latest_vitals": [item.model_dump(mode="json") for item in state.vitals[-5:]],
        "latest_weights": [item.model_dump(mode="json") for item in state.weights[-5:]],
        "latest_activity": [item.model_dump(mode="json") for item in state.activity[-7:]],
        "active_medications": [
            {
                "name": item.name,
                "strength": item.strength,
                "schedule": item.schedule,
                "purpose": item.purpose,
                "verification_status": item.verification_status,
            }
            for item in state.medication_plans
            if item.active
        ][:12],
    }


def compact_context_markdown(context: dict[str, Any]) -> str:
    results = context.get("relevant_results") or []
    if not results:
        return ""
    lines = ["Contexto longitudinal recuperado para esta pregunta:"]
    for item in results:
        lines.append(f"- Resultado {item['panel']} ({item['filename']}): {item['explanation']}")
    lines.append("Mantener la procedencia y no convertir una extracción de IA en diagnóstico confirmado.")
    return "\n".join(lines)
