from __future__ import annotations

import asyncio
import json
import mimetypes
import re
from datetime import date
from pathlib import Path
from typing import Any

from healthia_one.cost_guard import CostGuardBlocked
from healthia_one.models import HealthResult, PatientState, ResultItem, SourceRef


INLINE_MEDIA_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

ARTIFACT_TYPES = {
    "laboratory", "radiology_report", "xray_image", "ct_image", "mri_image",
    "ultrasound_image", "ecg", "pathology", "other",
}
VERIFICATION_TYPES = {"document_reported", "ai_observed_unverified", "mixed_unverified"}
CONFIDENCE_TYPES = {"low", "medium", "high"}

RESULT_ANALYSIS_PROMPT = """
You are HealthIA Result Intelligence. Inspect one patient-uploaded health artifact and return ONLY JSON.

Goal: identify what was uploaded and extract only what is actually visible or explicitly reported. The artifact may be a laboratory result, radiology report, radiograph/CT/MRI/ultrasound image, ECG/EKG image, pathology report, or another health document.

Safety and provenance rules:
- Never convert an AI inference into a confirmed diagnosis.
- Distinguish text that is explicitly reported in the artifact from your visual observation.
- If the artifact is an image without a signed report, describe visible features conservatively and mark them ai_observed_unverified.
- Do not prescribe, change medication, or declare an emergency diagnosis.
- If quality is insufficient, say so rather than guessing.
- Preserve units and reference ranges exactly when readable.
- For ECG/EKG images, describe readable rate/rhythm/interval or waveform features only when visible; do not claim a definitive interpretation when uncertain.
- For radiology images, identify modality/anatomic region only when supported by the artifact and separate reported impression from AI observation.

Return exactly this JSON shape:
{
  "artifact_type": "laboratory|radiology_report|xray_image|ct_image|mri_image|ultrasound_image|ecg|pathology|other",
  "panel": "short patient-facing label",
  "modality": "",
  "anatomical_region": "",
  "exam_date": "YYYY-MM-DD when explicitly visible, otherwise empty",
  "summary": "short factual summary",
  "reported_impression": "text explicitly present in the uploaded report, or empty",
  "ai_observations": ["observation 1"],
  "measurements": [
    {"name":"", "value":"", "unit":"", "reference":"", "flag":""}
  ],
  "safety_flags": ["only concrete concerns supported by the artifact"],
  "quality_limitations": ["limitation"],
  "confidence": "low|medium|high",
  "verification_status": "document_reported|ai_observed_unverified|mixed_unverified"
}
""".strip()


def normalized_mime_type(filename: str, content_type: str | None) -> str:
    supplied = (content_type or "").split(";", 1)[0].strip().lower()
    if supplied and supplied != "application/octet-stream":
        return supplied
    guessed, _ = mimetypes.guess_type(filename)
    return (guessed or "application/octet-stream").lower()


def result_storage_path(patient_id: str, result_id: str, filename: str) -> Path:
    safe_patient = re.sub(r"[^A-Za-z0-9._-]+", "_", patient_id)[:160] or "patient"
    suffix = Path(filename).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        suffix = ".bin"
    return Path("uploads") / "results" / safe_patient / f"{result_id}{suffix}"


def supports_inline_multimodal(mime_type: str) -> bool:
    return mime_type in INLINE_MEDIA_TYPES


def _clean_string(value: Any, limit: int = 1000) -> str:
    return str(value or "").strip()[:limit]


def _clean_list(value: Any, limit: int = 700, count: int = 40) -> list[str]:
    if not isinstance(value, list):
        return []
    return [cleaned for item in value[:count] if (cleaned := _clean_string(item, limit))]


def _exam_date(value: Any) -> date | None:
    text = _clean_string(value, 40)
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _enum_value(value: Any, allowed: set[str], fallback: str) -> str:
    candidate = _clean_string(value, 80).lower()
    return candidate if candidate in allowed else fallback


def _measurement_items(payload: dict[str, Any]) -> list[ResultItem]:
    items: list[ResultItem] = []
    for raw in payload.get("measurements") or []:
        if not isinstance(raw, dict):
            continue
        name = _clean_string(raw.get("name"), 180)
        if not name:
            continue
        value: float | str = _clean_string(raw.get("value"), 180)
        try:
            value = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            pass
        items.append(
            ResultItem(
                name=name,
                value=value,
                unit=_clean_string(raw.get("unit"), 60),
                reference=_clean_string(raw.get("reference"), 180),
                flag=_clean_string(raw.get("flag"), 80) or None,
            )
        )
    return items[:120]


def _render_explanation(payload: dict[str, Any], *, filename: str) -> str:
    artifact_type = _enum_value(payload.get("artifact_type"), ARTIFACT_TYPES, "other")
    modality = _clean_string(payload.get("modality"), 100)
    region = _clean_string(payload.get("anatomical_region"), 160)
    exam_date = _clean_string(payload.get("exam_date"), 80)
    summary = _clean_string(payload.get("summary"), 1600)
    reported = _clean_string(payload.get("reported_impression"), 1800)
    observations = _clean_list(payload.get("ai_observations"))
    safety = _clean_list(payload.get("safety_flags"))
    limitations = _clean_list(payload.get("quality_limitations"))
    confidence = _enum_value(payload.get("confidence"), CONFIDENCE_TYPES, "low")
    verification = _enum_value(payload.get("verification_status"), VERIFICATION_TYPES, "ai_observed_unverified")

    details = [f"**Tipo identificado:** {artifact_type}"]
    if modality:
        details.append(f"**Modalidad:** {modality}")
    if region:
        details.append(f"**Región:** {region}")
    if exam_date:
        details.append(f"**Fecha visible del estudio:** {exam_date}")

    lines = ["### Qué subiste", f"Archivo: **{filename}**", *details]
    if summary:
        lines.extend(["", "### Resumen extraído", summary])
    if reported:
        lines.extend(["", "### Impresión escrita en el documento", reported])
    if observations:
        lines.extend(["", "### Observaciones de IA no verificadas", *[f"- {item}" for item in observations]])
    if safety:
        lines.extend(["", "### Datos que merecen revisión", *[f"- {item}" for item in safety]])
    if limitations:
        lines.extend(["", "### Limitaciones", *[f"- {item}" for item in limitations]])
    lines.extend(
        [
            "",
            f"**Procedencia:** {verification} · confianza {confidence}.",
            "La extracción de IA queda separada de un diagnóstico confirmado. El archivo original se conserva para poder revisarlo nuevamente.",
        ]
    )
    return "\n".join(lines)


def apply_analysis_payload(result: HealthResult, payload: dict[str, Any], *, request_number: int) -> HealthResult:
    result.panel = _clean_string(payload.get("panel"), 180) or "Resultado multimodal"
    result.artifact_type = _enum_value(payload.get("artifact_type"), ARTIFACT_TYPES, "other")  # type: ignore[assignment]
    result.modality = _clean_string(payload.get("modality"), 120)
    result.anatomical_region = _clean_string(payload.get("anatomical_region"), 180)
    result.exam_date = _exam_date(payload.get("exam_date"))
    result.reported_impression = _clean_string(payload.get("reported_impression"), 4000)
    result.ai_observations = _clean_list(payload.get("ai_observations"), 1000, 50)
    result.safety_flags = _clean_list(payload.get("safety_flags"), 1000, 30)
    result.quality_limitations = _clean_list(payload.get("quality_limitations"), 1000, 30)
    result.ai_confidence = _enum_value(payload.get("confidence"), CONFIDENCE_TYPES, "low")  # type: ignore[assignment]
    result.verification_status = _enum_value(
        payload.get("verification_status"), VERIFICATION_TYPES, "ai_observed_unverified"
    )  # type: ignore[assignment]
    result.items = _measurement_items(payload)
    result.status = "parsed"
    result.explained = True
    result.explanation = _render_explanation(payload, filename=result.filename)
    result.source = SourceRef(source_type="AI_extraction", source_id=f"gemini_multimodal:{request_number}", verified=False)
    return result


async def analyze_uploaded_result(
    responder: Any,
    state: PatientState,
    result: HealthResult,
    *,
    content: bytes,
    mime_type: str,
) -> HealthResult:
    """Use one guarded Gemini request only when deterministic parsing is insufficient."""
    result.original_mime_type = mime_type
    if result.status != "pending_multimodal":
        return result
    if not supports_inline_multimodal(mime_type):
        result.explanation = (
            f"El archivo original se conservó, pero el tipo {mime_type} no está habilitado para análisis multimodal directo. "
            "No inventaré una interpretación."
        )
        return result
    if responder.settings.llm_backend != "gemini_api" or not responder.settings.adk_ready:
        result.explanation = (
            "El archivo original quedó guardado. La interpretación multimodal se ejecutará solamente cuando Gemini esté "
            "habilitado explícitamente; en este modo no se consume una llamada de IA."
        )
        return result

    try:
        request_number = responder.cost_guard.authorize("multimodal_result_ingestion")
    except CostGuardBlocked as exc:
        result.explanation = f"Archivo guardado sin análisis de IA porque el control de gasto lo bloqueó: {exc}"
        return result

    from google.genai import types

    context = {
        "task": "classify_and_extract_patient_uploaded_health_result",
        "filename": result.filename,
        "mime_type": mime_type,
        "authorized_patient_context": {
            "confirmed_conditions": state.profile.confirmed_conditions[:8],
            "allergies": state.profile.allergies[:8],
            "active_medications": [item.name for item in state.medication_plans if item.active][:10],
        },
        "provenance_requirement": "AI observations remain unverified and must never silently become confirmed facts.",
    }

    def call() -> dict[str, Any]:
        client = responder._get_client()
        response = client.models.generate_content(
            model=responder.settings.model,
            contents=[
                types.Part.from_bytes(data=content, mime_type=mime_type),
                RESULT_ANALYSIS_PROMPT,
                json.dumps(context, ensure_ascii=False),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=min(max(responder.cost_guard.max_output_tokens, 700), 1400),
            ),
        )
        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise RuntimeError("Gemini returned an empty multimodal result analysis")
        return responder._json_object(text)

    try:
        payload = await asyncio.wait_for(asyncio.to_thread(call), timeout=max(responder.settings.llm_timeout_seconds, 30))
    except Exception as exc:
        result.explanation = (
            "El archivo original quedó guardado, pero la interpretación multimodal falló de forma segura. "
            f"No se convirtió ninguna inferencia en hecho clínico. ({type(exc).__name__})"
        )
        responder.last_status = "result_multimodal_fallback"
        responder.last_error = f"{type(exc).__name__}: {exc}"[:500]
        return result

    apply_analysis_payload(result, payload, request_number=request_number)
    responder.last_status = "result_multimodal_completed"
    responder.last_error = ""
    return result
