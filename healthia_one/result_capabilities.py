from __future__ import annotations

import json
from pathlib import Path

SUPPORTED = {".json": "local_structured", ".csv": "local_structured", ".txt": "literal_text", ".pdf": "gemini_multimodal", ".png": "gemini_multimodal", ".jpg": "gemini_multimodal", ".jpeg": "gemini_multimodal", ".webp": "gemini_multimodal"}


class UnsupportedClinicalFormat(ValueError):
    def __init__(self, detected_format: str) -> None:
        self.detected_format = detected_format
        super().__init__(f"Formato clínico no implementado: {detected_format}")


def validate_clinical_upload(filename: str, mime_type: str, content: bytes) -> str:
    suffix, mime = Path(filename).suffix.lower(), mime_type.lower().split(";", 1)[0].strip()
    detected = None
    if suffix in {".dcm", ".dicom"} or mime == "application/dicom" or content[128:132] == b"DICM": detected = "dicom"
    elif suffix == ".zip" or mime in {"application/zip", "multipart/related"}: detected = "dicom_series_or_archive"
    elif suffix in {".mp4", ".mov", ".avi", ".cine"} or mime.startswith("video/"): detected = "cine_or_video"
    elif suffix in {".scp", ".edf", ".wfdb"}: detected = "digital_waveform"
    elif suffix in {".hl7", ".oru", ".adt", ".orm", ".cda"} or content.lstrip().startswith(b"MSH|"): detected = "hl7_v2_or_cda"
    elif mime in {"application/fhir+json", "application/fhir+xml"}: detected = "fhir"
    elif suffix == ".json":
        try: payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError): payload = None
        if isinstance(payload, dict) and (payload.get("resourceType") or payload.get("entry")): detected = "fhir"
    if detected: raise UnsupportedClinicalFormat(detected)
    route = SUPPORTED.get(suffix)
    if not route: raise UnsupportedClinicalFormat(suffix.lstrip(".") or "unknown")
    signatures = {".pdf": b"%PDF-", ".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
    if suffix in signatures and not content.startswith(signatures[suffix]): raise UnsupportedClinicalFormat(f"invalid_{suffix.lstrip('.')}")
    if suffix == ".webp" and not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"): raise UnsupportedClinicalFormat("invalid_webp")
    return route


def capability_manifest(max_upload_bytes: int, ai_ready: bool) -> dict:
    return {"version": "result-ingestion-v1", "max_upload_bytes": max_upload_bytes, "supported": [{"extension": ext, "route": route} for ext, route in SUPPORTED.items()], "not_implemented": ["dicom", "dicom_series", "volumetric", "cine", "digital_waveform", "hl7_v2", "fhir", "pacs", "lis"], "multimodal_ai_ready": ai_ready, "clinical_validation": "not_validated_by_specialists", "truth_boundary": "Admisión y extracción no equivalen a diagnóstico ni liberación profesional."}
