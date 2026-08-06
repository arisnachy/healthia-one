from __future__ import annotations

import re
from pathlib import Path

from healthia_one.models import ClinicalDocument, DocumentCategory, PatientState, new_id


ALLOWED_EXTENSIONS = {".json", ".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg"}


def safe_filename(filename: str) -> str:
    base = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned[:180] or "documento"


def category_from_filename(filename: str) -> DocumentCategory:
    text = filename.lower()
    if any(word in text for word in ("lab", "hemograma", "glucosa", "perfil", "resultado")):
        return DocumentCategory.LABORATORY
    if any(word in text for word in ("rx", "radiografia", "tomografia", "resonancia", "imagen")):
        return DocumentCategory.IMAGING
    if any(word in text for word in ("receta", "prescripcion", "medicamento")):
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
) -> ClinicalDocument:
    safe = safe_filename(filename)
    suffix = Path(safe).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Tipo de archivo no permitido")
    selected = DocumentCategory(category) if category else category_from_filename(safe)
    document_id = new_id("doc")
    return ClinicalDocument(
        id=document_id,
        title=(title or Path(safe).stem.replace("_", " ").strip() or "Documento clínico"),
        filename=safe,
        category=selected,
        mime_type=content_type or "application/octet-stream",
        size_bytes=size_bytes,
        storage_path=f"uploads/patient_demo/{document_id}_{safe}",
        status="pending_review" if suffix in {".pdf", ".png", ".jpg", ".jpeg"} else "stored",
        summary=(
            "Documento guardado y organizado. La extracción multimodal requiere Gemini configurado; "
            "HealthIA no inventará contenido que no haya podido leer."
            if suffix in {".pdf", ".png", ".jpg", ".jpeg"}
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
