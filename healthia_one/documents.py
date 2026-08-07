from __future__ import annotations

import re
from pathlib import Path

from healthia_one.models import ClinicalDocument, DocumentCategory, PatientState, new_id


ALLOWED_EXTENSIONS = {".json", ".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
MULTIMODAL_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def safe_filename(filename: str) -> str:
    base = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned[:180] or "documento"


def _filename_tokens(filename: str) -> set[str]:
    stem = Path(filename).stem.lower()
    return {token for token in re.split(r"[^a-záéíóúñ0-9]+", stem) if token}


def category_from_filename(filename: str) -> DocumentCategory:
    text = Path(filename).stem.lower()
    tokens = _filename_tokens(filename)
    if any(word in text for word in ("hemograma", "glucosa", "analitica", "analítica")) or tokens & {"lab", "perfil", "resultado"}:
        return DocumentCategory.LABORATORY
    imaging_long = (
        "radiografia", "radiografía", "tomografia", "tomografía", "resonancia", "imagen",
        "sonografia", "sonografía", "ultrasonido", "ecografia", "ecografía", "electrocard",
    )
    if any(word in text for word in imaging_long) or tokens & {"rx", "tac", "ct", "mri", "rm", "sono", "ultra", "ecg", "ekg", "xray"}:
        return DocumentCategory.IMAGING
    if any(word in text for word in ("receta", "prescripcion", "prescripción", "medicamento")):
        return DocumentCategory.PRESCRIPTION
    if any(word in text for word in ("consulta", "nota", "informe")):
        return DocumentCategory.CONSULTATION
    return DocumentCategory.OTHER


def build_document(
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    category: str | None = None,
    title: str | None = None,
    patient_id: str = "patient_demo",
) -> ClinicalDocument:
    safe = safe_filename(filename)
    suffix = Path(safe).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Tipo de archivo no permitido")
    selected = DocumentCategory(category) if category else category_from_filename(safe)
    document_id = new_id("doc")
    return ClinicalDocument(
        id=document_id,
        patient_id=patient_id,
        title=(title or Path(safe).stem.replace("_", " ").strip() or "Documento clínico"),
        filename=safe,
        category=selected,
        mime_type=content_type or "application/octet-stream",
        size_bytes=size_bytes,
        storage_path=f"uploads/{patient_id}/{document_id}_{safe}",
        status="pending_review" if suffix in MULTIMODAL_EXTENSIONS else "stored",
        summary=(
            "Documento original guardado. El análisis multimodal se ejecuta solo cuando Google AI real está habilitado; HealthIA no inventará contenido no leído."
            if suffix in MULTIMODAL_EXTENSIONS
            else "Documento guardado y disponible para el expediente longitudinal."
        ),
    )


def document_index(state: PatientState) -> dict:
    by_category: dict[str, int] = {}
    for document in state.documents:
        key = str(document.category)
        by_category[key] = by_category.get(key, 0) + 1
    return {
        "total": len(state.documents),
        "by_category": by_category,
        "pending_review": sum(item.status == "pending_review" for item in state.documents),
        "latest": [item.model_dump(mode="json") for item in state.documents[-5:]],
    }
