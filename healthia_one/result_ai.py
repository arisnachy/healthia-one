from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

from healthia_one.cost_guard import CostGuardBlocked
from healthia_one.models import HealthResult, PatientState, ResultItem


RESULT_ANALYSIS_SYSTEM_INSTRUCTION = """
Eres el analizador multimodal de resultados de HealthIA. Tu tarea es identificar qué tipo de evidencia clínica subió el paciente y extraer únicamente lo que es visible o legible en el archivo.

Reglas obligatorias:
- No inventes texto, valores, medidas ni hallazgos que no puedas leer.
- Separa observaciones del archivo de cualquier impresión o interpretación.
- No prescribas ni cambies tratamientos.
- No declares que un diagnóstico está confirmado por una imagen aislada.
- Para radiología, ecografía, ECG y otros estudios, incluye limitaciones de calidad y recomienda revisión profesional cuando corresponda.
- Para laboratorios, conserva valores, unidades, rangos y banderas exactamente cuando sean legibles.
- Sé conciso: no repitas el mismo hallazgo en observations, findings, impression y patient_explanation.
- Devuelve únicamente el objeto JSON solicitado por el esquema de salida; no uses Markdown ni texto exterior.
""".strip()


RESULT_ANALYSIS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "document_type",
        "panel",
        "observations",
        "findings",
        "patient_explanation",
        "requires_professional_review",
    ],
    "properties": {
        "document_type": {
            "type": "string",
            "enum": [
                "laboratory",
                "ct",
                "mri",
                "xray",
                "ultrasound",
                "ecg",
                "pathology",
                "clinical_report",
                "other",
            ],
        },
        "modality": {"type": "string", "maxLength": 80},
        "panel": {"type": "string", "maxLength": 180},
        "anatomical_regions": {
            "type": "array",
            "items": {"type": "string", "maxLength": 100},
            "maxItems": 6,
        },
        "observations": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "value"],
                "properties": {
                    "name": {"type": "string", "maxLength": 120},
                    "value": {
                        "anyOf": [
                            {"type": "string", "maxLength": 180},
                            {"type": "number"},
                            {"type": "null"},
                        ]
                    },
                    "unit": {"type": "string", "maxLength": 60},
                    "reference": {"type": "string", "maxLength": 120},
                    "flag": {
                        "anyOf": [
                            {"type": "string", "maxLength": 60},
                            {"type": "null"},
                        ]
                    },
                },
            },
        },
        "findings": {
            "type": "array",
            "items": {"type": "string", "maxLength": 300},
            "maxItems": 10,
        },
        "impression": {"type": "string", "maxLength": 500},
        "limitations": {
            "type": "array",
            "items": {"type": "string", "maxLength": 240},
            "maxItems": 4,
        },
        "patient_explanation": {"type": "string", "maxLength": 700},
        "requires_professional_review": {"type": "boolean"},
    },
}


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
PDF_SUFFIXES = {".pdf"}
MULTIMODAL_TIMEOUT_SECONDS = 45


def infer_result_kind(filename: str, mime_type: str = "") -> str:
    name = Path(filename).name.lower()
    mime = str(mime_type or "").lower()
    if any(token in name for token in ("ecg", "ekg", "electrocard")):
        return "ecg"
    if any(token in name for token in ("sono", "ultra", "ecografia", "ecografía")):
        return "ultrasound"
    if any(token in name for token in ("tomograf", "tac", "ct_", "ct-")):
        return "ct"
    if any(token in name for token in ("reson", "mri", "rm_", "rm-")):
        return "mri"
    if any(token in name for token in ("radiograf", "xray", "x-ray", "rx_", "rx-")):
        return "xray"
    if any(token in name for token in ("patolog", "biops", "histolog")):
        return "pathology"
    if any(token in name for token in ("lab", "analit", "hemograma", "quimica", "química")):
        return "laboratory"
    if mime.startswith("image/"):
        return "clinical_image"
    if mime == "application/pdf":
        return "clinical_report"
    return "other"


def multimodal_supported(filename: str, mime_type: str) -> bool:
    suffix = Path(filename).suffix.lower()
    mime = str(mime_type or "").lower()
    return mime.startswith("image/") or mime == "application/pdf" or suffix in IMAGE_SUFFIXES | PDF_SUFFIXES


def _media_input(filename: str, mime_type: str, content: bytes) -> dict[str, str]:
    """Build one Gemini 3 Interactions media item with an explicit resolution policy.

    PDFs use low visual resolution because Gemini 3 also supplies native PDF
    text at that level; this cuts visual-media tokens and latency for routine
    reports/labs. Clinical images retain high resolution because small visual
    details can matter and HealthIA must prefer fidelity over speed there.
    """

    mime = str(mime_type or "").lower()
    suffix = Path(filename).suffix.lower()
    if mime == "application/pdf" or suffix == ".pdf":
        media_type = "document"
        mime = "application/pdf"
        resolution = "low"
    else:
        media_type = "image"
        resolution = "high"
        if not mime.startswith("image/"):
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(suffix, "image/jpeg")
    return {
        "type": media_type,
        "data": base64.b64encode(content).decode("utf-8"),
        "mime_type": mime,
        "resolution": resolution,
    }


def _generate_analysis(responder, state: PatientState, filename: str, mime_type: str, content: bytes) -> dict[str, Any]:
    prompt = {
        "task": "identify_and_extract_uploaded_clinical_result",
        "filename": Path(filename).name,
        "hinted_kind": infer_result_kind(filename, mime_type),
        "patient_context": {
            "confirmed_conditions": state.profile.confirmed_conditions[:6],
            "allergies": state.profile.allergies[:6],
            "recent_result_panels": [item.panel for item in state.results[-5:]],
        },
        "truth_boundary": "Use only what is visible or legible in this upload. Do not infer missing measurements.",
        "output_policy": (
            "Return a compact clinical extraction. Do not repeat facts across fields; omit optional fields "
            "when they add no new information."
        ),
    }
    generation_config: dict[str, Any] = {
        "max_output_tokens": min(responder.cost_guard.max_output_tokens, 1400),
        "thinking_level": "minimal",
    }
    # Vertex supports controlled JSON generation. Enforce it at the transport
    # boundary rather than repairing malformed model text after the fact.
    if responder.settings.vertex_ai_enabled:
        generation_config.update(
            {
                "response_mime_type": "application/json",
                "response_json_schema": RESULT_ANALYSIS_JSON_SCHEMA,
            }
        )

    interaction = responder._get_client().interactions.create(
        model=responder.settings.model,
        input=[
            {"type": "text", "text": json.dumps(prompt, ensure_ascii=False)},
            _media_input(filename, mime_type, content),
        ],
        system_instruction=RESULT_ANALYSIS_SYSTEM_INSTRUCTION,
        generation_config=generation_config,
        store=False,
    )
    text = responder._interaction_text(interaction)
    if not text:
        raise RuntimeError("Gemini devolvió un análisis multimodal vacío")
    return responder._json_object(text)


def _multimodal_timeout_seconds(responder) -> int:
    """Use a document-specific ceiling without slowing the interactive chat path."""

    return max(int(responder.settings.llm_timeout_seconds), MULTIMODAL_TIMEOUT_SECONDS)


async def analyze_uploaded_result(responder, state: PatientState, filename: str, mime_type: str, content: bytes) -> dict[str, Any]:
    if not multimodal_supported(filename, mime_type):
        return {"status": "unsupported", "detail": "El formato no está habilitado para análisis multimodal."}
    if responder.settings.llm_backend != "gemini_api" or not responder.settings.adk_ready:
        return {"status": "pending", "detail": "Gemini multimodal no está configurado en esta ejecución."}
    try:
        request_number = responder.cost_guard.authorize("multimodal_result_interpretation")
    except CostGuardBlocked as exc:
        return {"status": "pending", "detail": str(exc), "cost_guard": responder.cost_guard.snapshot()}
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(_generate_analysis, responder, state, filename, mime_type, content),
            timeout=_multimodal_timeout_seconds(responder),
        )
    except Exception as exc:
        return {
            "status": "pending",
            "detail": f"{type(exc).__name__}: {exc}"[:500],
            "request_number": request_number,
            "cost_guard": responder.cost_guard.snapshot(),
        }
    payload["status"] = "parsed"
    payload["request_number"] = request_number
    payload["cost_guard"] = responder.cost_guard.snapshot()
    return payload


def apply_multimodal_analysis(result: HealthResult, analysis: dict[str, Any]) -> HealthResult:
    if analysis.get("status") != "parsed":
        result.status = "pending_multimodal"
        detail = str(analysis.get("detail") or "Análisis multimodal pendiente.").strip()
        result.explanation = (
            "El archivo original quedó guardado. La interpretación multimodal todavía no se completó y HealthIA no inventará hallazgos. "
            + detail
        )
        result.explained = False
        return result

    panel = str(analysis.get("panel") or analysis.get("modality") or "Resultado multimodal").strip()
    result.panel = panel[:220] or "Resultado multimodal"
    items: list[ResultItem] = []
    for raw in analysis.get("observations") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "Observación").strip()
        value = raw.get("value", "")
        if value in (None, ""):
            continue
        items.append(
            ResultItem(
                name=name[:160],
                value=value if isinstance(value, (int, float)) else str(value)[:500],
                unit=str(raw.get("unit") or "")[:80],
                reference=str(raw.get("reference") or "")[:160],
                flag=str(raw.get("flag"))[:80] if raw.get("flag") not in (None, "") else None,
            )
        )
    for region in (analysis.get("anatomical_regions") or [])[:8]:
        if str(region).strip():
            items.append(ResultItem(name="Región anatómica", value=str(region).strip()[:300]))
    for finding in (analysis.get("findings") or [])[:16]:
        if str(finding).strip():
            items.append(ResultItem(name="Hallazgo", value=str(finding).strip()[:500]))
    impression = str(analysis.get("impression") or "").strip()
    if impression:
        items.append(ResultItem(name="Impresión", value=impression[:700]))
    result.items = items
    explanation = str(analysis.get("patient_explanation") or "").strip()
    limitations = [str(item).strip() for item in analysis.get("limitations") or [] if str(item).strip()]
    lines = [explanation] if explanation else []
    if limitations:
        lines.append("Limitaciones: " + "; ".join(limitations[:6]))
    if analysis.get("requires_professional_review", True):
        lines.append("Este análisis organiza la evidencia subida y debe correlacionarse con el informe original y la evaluación profesional.")
    result.explanation = "\n\n".join(lines) or "Resultado multimodal extraído sin explicación adicional."
    result.status = "parsed"
    result.explained = True
    return result
