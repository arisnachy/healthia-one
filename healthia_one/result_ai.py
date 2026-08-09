from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

from healthia_one.cost_guard import CostGuardBlocked
from healthia_one.language import current_requested_locale, language_instruction, normalize_locale
from healthia_one.models import HealthResult, PatientState, ResultItem


RESULT_ANALYSIS_SYSTEM_INSTRUCTION = """
You are HealthIA's multimodal clinical-result analyzer. Identify what kind of clinical evidence the patient uploaded and extract only what is visible or legible in the file.

Mandatory rules:
- Never invent text, values, measurements, or findings that you cannot read.
- Separate file observations from any impression or interpretation.
- Do not prescribe or change treatment.
- Do not claim that an isolated image confirms a diagnosis.
- For radiology, ultrasound, ECG, and other studies, include relevant quality limitations and professional-review boundaries.
- For laboratories, preserve legible values, units, reference ranges, and flags exactly.
- Be concise: do not repeat the same fact across observations, findings, impression, and patient_explanation.
- Preserve literal clinical labels from the source when useful, but write patient-facing explanatory prose in the requested response language.
- Return only the JSON object required by the output schema; no Markdown and no surrounding text.
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


def _result_locale(state: PatientState | None = None, analysis: dict[str, Any] | None = None) -> str:
    """Resolve patient-facing result language without rewriting legacy payloads.

    A locale explicitly carried by the analysis wins, then the current request,
    then the patient profile. Only when none exists do we infer a conservative
    fallback from the already-produced payload. This lets older Spanish result
    objects remain Spanish while an English browser request remains English end
    to end.
    """

    explicit = str((analysis or {}).get("response_locale") or "").strip()
    if explicit:
        return normalize_locale(explicit, fallback="en")

    requested = current_requested_locale()
    if requested:
        return normalize_locale(requested, fallback="en")

    profile_locale = state.profile.locale if state is not None else None
    if profile_locale:
        return normalize_locale(profile_locale, fallback="en")

    payload = analysis or {}
    sample_parts: list[str] = [
        str(payload.get("panel") or ""),
        str(payload.get("modality") or ""),
        str(payload.get("patient_explanation") or ""),
        str(payload.get("impression") or ""),
    ]
    sample_parts.extend(str(item) for item in payload.get("anatomical_regions") or [])
    sample_parts.extend(str(item) for item in payload.get("findings") or [])
    sample_parts.extend(str(item) for item in payload.get("limitations") or [])
    sample = " ".join(sample_parts).lower()
    if any(char in sample for char in "¿¡ñáéíóú"):
        return "es"
    return "en"


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
    response_locale = _result_locale(state)
    prompt = {
        "task": "identify_and_extract_uploaded_clinical_result",
        "filename": Path(filename).name,
        "hinted_kind": infer_result_kind(filename, mime_type),
        "response_locale": response_locale,
        "patient_context": {
            "confirmed_conditions": state.profile.confirmed_conditions[:6],
            "allergies": state.profile.allergies[:6],
            "recent_result_panels": [item.panel for item in state.results[-5:]],
        },
        "truth_boundary": "Use only what is visible or legible in this upload. Do not infer missing measurements.",
        "output_policy": (
            "Return a compact clinical extraction. Do not repeat facts across fields; omit optional fields "
            "when they add no new information. Patient-facing explanatory prose must follow response_locale."
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
        system_instruction=f"{RESULT_ANALYSIS_SYSTEM_INSTRUCTION}\n\n{language_instruction(response_locale)}",
        generation_config=generation_config,
        store=False,
    )
    text = responder._interaction_text(interaction)
    if not text:
        raise RuntimeError("Gemini returned an empty multimodal analysis")
    payload = responder._json_object(text)
    payload["response_locale"] = response_locale
    return payload


def _multimodal_timeout_seconds(responder) -> int:
    """Use a document-specific ceiling without slowing the interactive chat path."""

    return max(int(responder.settings.llm_timeout_seconds), MULTIMODAL_TIMEOUT_SECONDS)


async def analyze_uploaded_result(responder, state: PatientState, filename: str, mime_type: str, content: bytes) -> dict[str, Any]:
    locale = _result_locale(state)
    if not multimodal_supported(filename, mime_type):
        return {
            "status": "unsupported",
            "detail": "This format is not enabled for multimodal analysis." if locale == "en" else "El formato no está habilitado para análisis multimodal.",
            "response_locale": locale,
        }
    if responder.settings.llm_backend != "gemini_api" or not responder.settings.adk_ready:
        return {
            "status": "pending",
            "detail": "Gemini multimodal is not configured for this run." if locale == "en" else "Gemini multimodal no está configurado en esta ejecución.",
            "response_locale": locale,
        }
    try:
        request_number = responder.cost_guard.authorize("multimodal_result_interpretation")
    except CostGuardBlocked as exc:
        return {"status": "pending", "detail": str(exc), "response_locale": locale, "cost_guard": responder.cost_guard.snapshot()}
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(_generate_analysis, responder, state, filename, mime_type, content),
            timeout=_multimodal_timeout_seconds(responder),
        )
    except Exception as exc:
        return {
            "status": "pending",
            "detail": f"{type(exc).__name__}: {exc}"[:500],
            "response_locale": locale,
            "request_number": request_number,
            "cost_guard": responder.cost_guard.snapshot(),
        }
    payload["status"] = "parsed"
    payload["response_locale"] = str(payload.get("response_locale") or locale)
    payload["request_number"] = request_number
    payload["cost_guard"] = responder.cost_guard.snapshot()
    return payload


def apply_multimodal_analysis(result: HealthResult, analysis: dict[str, Any]) -> HealthResult:
    locale = _result_locale(analysis=analysis)
    if analysis.get("status") != "parsed":
        result.status = "pending_multimodal"
        detail = str(analysis.get("detail") or ("Multimodal analysis is pending." if locale == "en" else "Análisis multimodal pendiente.")).strip()
        result.explanation = (
            "The original file is saved. Multimodal interpretation has not completed yet, and HealthIA will not invent findings. "
            if locale == "en"
            else "El archivo original quedó guardado. La interpretación multimodal todavía no se completó y HealthIA no inventará hallazgos. "
        ) + detail
        result.explained = False
        return result

    panel_fallback = "Multimodal result" if locale == "en" else "Resultado multimodal"
    panel = str(analysis.get("panel") or analysis.get("modality") or panel_fallback).strip()
    result.panel = panel[:220] or panel_fallback
    items: list[ResultItem] = []
    for raw in analysis.get("observations") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or ("Observation" if locale == "en" else "Observación")).strip()
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
            items.append(ResultItem(name="Anatomical region" if locale == "en" else "Región anatómica", value=str(region).strip()[:300]))
    for finding in (analysis.get("findings") or [])[:16]:
        if str(finding).strip():
            items.append(ResultItem(name="Finding" if locale == "en" else "Hallazgo", value=str(finding).strip()[:500]))
    impression = str(analysis.get("impression") or "").strip()
    if impression:
        items.append(ResultItem(name="Impression" if locale == "en" else "Impresión", value=impression[:700]))
    result.items = items
    explanation = str(analysis.get("patient_explanation") or "").strip()
    limitations = [str(item).strip() for item in analysis.get("limitations") or [] if str(item).strip()]
    lines = [explanation] if explanation else []
    if limitations:
        lines.append(("Limitations: " if locale == "en" else "Limitaciones: ") + "; ".join(limitations[:6]))
    if analysis.get("requires_professional_review", True):
        lines.append(
            "This analysis organizes the uploaded evidence and should be correlated with the original report and professional evaluation."
            if locale == "en"
            else "Este análisis organiza la evidencia subida y debe correlacionarse con el informe original y la evaluación profesional."
        )
    result.explanation = "\n\n".join(lines) or (
        "Multimodal result extracted without an additional explanation."
        if locale == "en"
        else "Resultado multimodal extraído sin explicación adicional."
    )
    result.status = "parsed"
    result.explained = True
    return result
