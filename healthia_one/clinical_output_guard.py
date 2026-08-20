from __future__ import annotations

import re
import unicodedata


FORBIDDEN_CLINICAL_DIRECTIVES = (
    "suspende ",
    "suspenda ",
    "empieza a tomar ",
    "comienza a tomar ",
    "deja de tomar ",
    "debe tomar ",
    "debes tomar ",
    "te recomiendo tomar ",
    "aumenta la dosis",
    "aumente la dosis",
    "reduce la dosis",
    "reduzca la dosis",
    "disminuye la dosis",
    "disminuya la dosis",
    "diagnostico confirmado",
    "definitivamente tienes",
    "stop taking ",
    "discontinue ",
    "start taking ",
    "you should take ",
    "increase the dose",
    "decrease the dose",
    "reduce the dose",
    "confirmed diagnosis",
    "you definitely have",
)


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value).lower())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


def contains_forbidden_clinical_directive(value: str) -> bool:
    """Fail closed on patient-visible diagnosis or treatment commands."""
    normalized = _normalize(value)
    if any(directive in normalized for directive in FORBIDDEN_CLINICAL_DIRECTIVES):
        return True
    for fragment in re.split(r"[.!;\n]+", normalized):
        clause = fragment.strip()
        if not clause or "?" in clause or clause.startswith("¿"):
            continue
        command = clause.lstrip("¡!:- ")
        if re.match(r"^(?:por favor\s+)?(?:no\s+)?(?:toma|tome)\s+", command):
            return True
        if re.match(r"^(?:please\s+)?(?:do not\s+|don't\s+)?take\s+", command):
            return True
    return False
