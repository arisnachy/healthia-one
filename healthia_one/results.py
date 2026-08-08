from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from healthia_one.language import current_requested_locale, normalize_locale
from healthia_one.models import HealthResult, ResultItem


KNOWN_TESTS = {
    "hba1c": {
        "en": "Reflects the approximate average glucose level over the past few months.",
        "es": "Refleja el promedio aproximado de glucosa de los últimos meses.",
    },
    "hemoglobina a1c": {
        "en": "Reflects the approximate average glucose level over the past few months.",
        "es": "Refleja el promedio aproximado de glucosa de los últimos meses.",
    },
    "ldl": {
        "en": "A cholesterol fraction related to cardiovascular risk; the target depends on clinical context.",
        "es": "Es una fracción de colesterol relacionada con riesgo cardiovascular; la meta depende del contexto clínico.",
    },
    "creatinina": {
        "en": "Helps assess kidney function together with age, sex, history, and other calculations.",
        "es": "Ayuda a valorar función renal junto con edad, sexo, antecedentes y otros cálculos.",
    },
    "creatinine": {
        "en": "Helps assess kidney function together with age, sex, history, and other calculations.",
        "es": "Ayuda a valorar función renal junto con edad, sexo, antecedentes y otros cálculos.",
    },
    "hemoglobina": {
        "en": "Carries oxygen in the blood; interpretation depends on the laboratory range and clinical context.",
        "es": "Transporta oxígeno en la sangre; su interpretación depende del rango del laboratorio y el contexto.",
    },
    "hemoglobin": {
        "en": "Carries oxygen in the blood; interpretation depends on the laboratory range and clinical context.",
        "es": "Transporta oxígeno en la sangre; su interpretación depende del rango del laboratorio y el contexto.",
    },
}


def _locale() -> str:
    return normalize_locale(current_requested_locale(), fallback="en")


def _text(en: str, es: str) -> str:
    return es if _locale() == "es" else en


def _coerce_item(raw: dict[str, Any]) -> ResultItem:
    value = raw.get("value", "")
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = str(value)
    return ResultItem(
        name=str(raw.get("name") or raw.get("test") or _text("Result", "Resultado")),
        value=value,
        unit=str(raw.get("unit") or ""),
        reference=str(raw.get("reference") or raw.get("range") or ""),
        flag=str(raw["flag"]) if raw.get("flag") is not None else None,
    )


def parse_result_file(filename: str, content: bytes) -> HealthResult:
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        payload = json.loads(content.decode("utf-8"))
        rows = payload.get("results", payload if isinstance(payload, list) else [])
        items = [_coerce_item(row) for row in rows]
        default_panel = _text("Laboratory", "Laboratorio")
        return HealthResult(filename=filename, panel=payload.get("panel", default_panel) if isinstance(payload, dict) else default_panel, items=items)
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        return HealthResult(filename=filename, panel=_text("Laboratory CSV", "Laboratorio CSV"), items=[_coerce_item(row) for row in reader])
    if suffix == ".txt":
        lines = [line.strip() for line in content.decode("utf-8").splitlines() if line.strip()]
        items = [ResultItem(name=_text("Reported text", "Texto informado"), value=line) for line in lines[:30]]
        return HealthResult(filename=filename, panel=_text("Text result", "Resultado de texto"), items=items)
    return HealthResult(filename=filename, status="pending_multimodal", items=[])


def explain_result(result: HealthResult) -> str:
    locale = _locale()
    if result.status == "pending_multimodal":
        return (
            "The original file is saved, but this environment still needs the configured multimodal agent to extract a PDF or image. I will not invent values I could not read."
            if locale == "en"
            else "El archivo quedó guardado, pero este entorno todavía necesita el agente multimodal configurado para extraer PDF o imagen. No inventaré valores que no pude leer."
        )
    if not result.items:
        return (
            "I did not find enough structured values to explain this result."
            if locale == "en"
            else "No encontré valores estructurados suficientes para explicar este resultado."
        )

    lines = [
        f"## {result.panel}",
        "This is an educational explanation, not a diagnosis." if locale == "en" else "Esta es una explicación educativa, no un diagnóstico.",
    ]
    for item in result.items:
        key = item.name.strip().lower()
        entry = KNOWN_TESTS.get(key)
        description = (
            entry[locale]
            if entry
            else (
                "This value should be interpreted with the laboratory reference range and your health history."
                if locale == "en"
                else "Este valor debe interpretarse con el rango del laboratorio y tu historia."
            )
        )
        display = f"{item.value} {item.unit}".strip()
        reference = (
            f" · reference: {item.reference}" if locale == "en" else f" · referencia: {item.reference}"
        ) if item.reference else ""
        flag = (
            f" · flagged as {item.flag}" if locale == "en" else f" · marcado como {item.flag}"
        ) if item.flag else ""
        lines.append(f"- **{item.name}:** {display}{reference}{flag}. {description}")
    lines.append(
        "\n**Next step:** review trends, symptoms, medications, and goals with a professional before changing treatment."
        if locale == "en"
        else "\n**Próximo paso:** revisa tendencias, síntomas, medicamentos y objetivos con un profesional antes de cambiar tratamiento."
    )
    return "\n".join(lines)