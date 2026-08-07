from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from healthia_one.models import HealthResult, ResultItem


KNOWN_TESTS = {
    "hba1c": "Refleja el promedio aproximado de glucosa de los últimos meses.",
    "hemoglobina a1c": "Refleja el promedio aproximado de glucosa de los últimos meses.",
    "ldl": "Es una fracción de colesterol relacionada con riesgo cardiovascular; la meta depende del contexto clínico.",
    "creatinina": "Ayuda a valorar función renal junto con edad, sexo, antecedentes y otros cálculos.",
    "hemoglobina": "Transporta oxígeno en la sangre; su interpretación depende del rango del laboratorio y el contexto.",
}


def _coerce_item(raw: dict[str, Any]) -> ResultItem:
    value = raw.get("value", "")
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = str(value)
    return ResultItem(
        name=str(raw.get("name") or raw.get("test") or "Resultado"),
        value=value,
        unit=str(raw.get("unit") or ""),
        reference=str(raw.get("reference") or raw.get("range") or ""),
        flag=str(raw["flag"]) if raw.get("flag") is not None else None,
    )


def parse_result_file(filename: str, content: bytes) -> HealthResult:
    """Parse deterministic result formats before considering a model call."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        payload = json.loads(content.decode("utf-8"))
        rows = payload.get("results", payload if isinstance(payload, list) else [])
        items = [_coerce_item(row) for row in rows]
        return HealthResult(
            filename=filename,
            original_mime_type="application/json",
            panel=payload.get("panel", "Laboratorio") if isinstance(payload, dict) else "Laboratorio",
            artifact_type="laboratory",
            verification_status="document_reported",
            items=items,
        )
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        return HealthResult(
            filename=filename,
            original_mime_type="text/csv",
            panel="Laboratorio CSV",
            artifact_type="laboratory",
            verification_status="document_reported",
            items=[_coerce_item(row) for row in reader],
        )
    if suffix == ".txt":
        lines = [line.strip() for line in content.decode("utf-8").splitlines() if line.strip()]
        items = [ResultItem(name="Texto informado", value=line) for line in lines[:30]]
        return HealthResult(
            filename=filename,
            original_mime_type="text/plain",
            panel="Resultado de texto",
            artifact_type="other",
            verification_status="document_reported",
            items=items,
        )
    return HealthResult(filename=filename, status="pending_multimodal", items=[])


def explain_result(result: HealthResult) -> str:
    if result.status == "pending_multimodal":
        return (
            "El archivo quedó guardado, pero este entorno todavía necesita el agente multimodal "
            "configurado para extraer PDF o imagen. No inventaré valores que no pude leer."
        )
    if not result.items:
        return "No encontré valores estructurados suficientes para explicar este resultado."

    lines = [f"## {result.panel}", "Esta es una explicación educativa, no un diagnóstico."]
    for item in result.items:
        key = item.name.strip().lower()
        description = KNOWN_TESTS.get(key, "Este valor debe interpretarse con el rango del laboratorio y tu historia.")
        display = f"{item.value} {item.unit}".strip()
        reference = f" · referencia: {item.reference}" if item.reference else ""
        flag = f" · marcado como {item.flag}" if item.flag else ""
        lines.append(f"- **{item.name}:** {display}{reference}{flag}. {description}")
    lines.append("\n**Próximo paso:** revisa tendencias, síntomas, medicamentos y objetivos con un profesional antes de cambiar tratamiento.")
    return "\n".join(lines)
