from __future__ import annotations

import re
from dataclasses import dataclass

from healthia_one.models import HealthResult, PatientState


STOPWORDS = {
    "mi", "mis", "el", "la", "los", "las", "de", "del", "un", "una", "que", "me", "lo", "por", "para",
    "resultado", "resultados", "estudio", "estudios", "informe", "informes", "imagen", "imagenes", "imágenes",
    "ver", "busca", "buscar", "revisa", "revisar", "habla", "hablar", "sobre", "ultimo", "último",
}

ALIASES = {
    "tac": {"tac", "tc", "ct", "tomografia", "tomografía"},
    "tomografia": {"tac", "tc", "ct", "tomografia", "tomografía"},
    "tomografía": {"tac", "tc", "ct", "tomografia", "tomografía"},
    "resonancia": {"resonancia", "mri", "rm"},
    "mri": {"resonancia", "mri", "rm"},
    "sonografia": {"sonografia", "sonografía", "ecografia", "ecografía", "ultrasonido", "ultrasound"},
    "sonografía": {"sonografia", "sonografía", "ecografia", "ecografía", "ultrasonido", "ultrasound"},
    "ecg": {"ecg", "ekg", "electrocardiograma", "electrocard"},
    "ekg": {"ecg", "ekg", "electrocardiograma", "electrocard"},
    "radiografia": {"radiografia", "radiografía", "rx", "xray", "x-ray"},
    "laboratorio": {"laboratorio", "lab", "analitica", "analítica", "hemograma", "quimica", "química"},
}


@dataclass(frozen=True)
class ResultMatch:
    result: HealthResult
    score: int
    matched_terms: tuple[str, ...]


def _tokens(text: str) -> set[str]:
    raw = {token for token in re.findall(r"[a-záéíóúñ0-9]+", str(text or "").lower()) if len(token) >= 2}
    expanded = set(raw)
    for token in list(raw):
        expanded.update(ALIASES.get(token, set()))
    return {token for token in expanded if token not in STOPWORDS}


def _result_text(result: HealthResult) -> str:
    pieces = [result.filename, result.panel, result.explanation]
    for item in result.items:
        pieces.extend([item.name, str(item.value), item.unit, item.reference, item.flag or ""])
    return " ".join(pieces).lower()


def find_relevant_result(state: PatientState, patient_text: str) -> ResultMatch | None:
    if not state.results:
        return None
    query_terms = _tokens(patient_text)
    if not query_terms:
        return ResultMatch(state.results[-1], 0, tuple())

    ranked: list[ResultMatch] = []
    for index, result in enumerate(state.results):
        searchable = _result_text(result)
        matched = tuple(sorted(term for term in query_terms if term in searchable))
        score = len(matched) * 10
        filename = result.filename.lower()
        panel = result.panel.lower()
        score += sum(8 for term in matched if term in filename)
        score += sum(6 for term in matched if term in panel)
        score += min(index, 5)  # recent evidence wins only when semantic score is similar
        ranked.append(ResultMatch(result=result, score=score, matched_terms=matched))

    best = max(ranked, key=lambda match: match.score)
    if best.score <= 5:
        return ResultMatch(state.results[-1], 0, tuple())
    return best


def original_document_id(state: PatientState, result_id: str) -> str | None:
    document = next((item for item in state.documents if item.related_result_id == result_id), None)
    return document.id if document else None


def conversational_result_context(state: PatientState, patient_text: str) -> dict | None:
    match = find_relevant_result(state, patient_text)
    if match is None:
        return None
    result = match.result
    return {
        "result_id": result.id,
        "filename": result.filename,
        "panel": result.panel,
        "status": result.status,
        "uploaded_at": result.uploaded_at.isoformat(),
        "explanation": result.explanation,
        "items": [item.model_dump(mode="json") for item in result.items[:30]],
        "document_id": original_document_id(state, result.id),
        "matched_terms": list(match.matched_terms),
        "match_score": match.score,
    }
