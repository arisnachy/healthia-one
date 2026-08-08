from __future__ import annotations

import re

SUPPORTED_LANGUAGES = {"en", "es"}


def normalize_locale(value: str | None, *, fallback: str = "en") -> str:
    raw = str(value or "").strip().replace("_", "-")
    if raw:
        language = raw.split("-", 1)[0].lower()
        if language in SUPPORTED_LANGUAGES:
            return language
    return fallback if fallback in SUPPORTED_LANGUAGES else "en"


def detect_text_language(text: str) -> str | None:
    """Conservative English/Spanish detector for choosing response language.

    This is not a clinical NLP classifier. It only decides the patient-facing
    language. Low-confidence text deliberately returns None so the OS/profile
    locale remains the fallback instead of guessing.
    """

    sample = f" {str(text or '').lower()} "
    spanish_tokens = (
        "¿", "¡", "ñ", "á", "é", "í", "ó", "ú",
        " me ", " tengo ", " desde ", " dolor ", " quiero ", " resultados ",
        " presión ", " fiebre ", " orina ", " peso ", " ayuda ", " qué ",
    )
    english_tokens = (
        " i ", " my ", " since ", " pain ", " want ", " results ",
        " blood ", " pressure ", " fever ", " urine ", " weight ", " help ",
        " what ", " please ", " have ",
    )

    def score(tokens: tuple[str, ...]) -> int:
        return sum(1 for token in tokens if token in sample)

    es = score(spanish_tokens)
    en = score(english_tokens)
    # A sentence with clear diacritics/question punctuation is enough; otherwise
    # require at least two lexical signals to avoid misclassifying short inputs.
    if any(char in sample for char in "¿¡ñáéíóú") and es > en:
        return "es"
    if es >= 2 and es > en:
        return "es"
    if en >= 2 and en > es:
        return "en"

    # A final lightweight word-boundary pass helps clear English clinical asks
    # such as "pain today" without treating a single ambiguous word as proof.
    english_hits = re.findall(r"\b(pain|fever|today|please|results?|pressure|weight|help)\b", sample)
    spanish_hits = re.findall(r"\b(dolor|fiebre|hoy|resultados?|presi[oó]n|peso|ayuda)\b", sample)
    if len(english_hits) >= 2 and len(english_hits) > len(spanish_hits):
        return "en"
    if len(spanish_hits) >= 2 and len(spanish_hits) > len(english_hits):
        return "es"
    return None


def resolve_response_locale(
    text: str,
    *,
    requested_locale: str | None = None,
    profile_locale: str | None = None,
) -> str:
    detected = detect_text_language(text)
    if detected:
        return detected
    if requested_locale:
        return normalize_locale(requested_locale)
    return normalize_locale(profile_locale, fallback="en")


def language_instruction(locale: str) -> str:
    language = normalize_locale(locale)
    if language == "es":
        return (
            "Responde al paciente en español claro y natural. Todas las preguntas, "
            "opciones y explicaciones visibles deben estar en español."
        )
    return (
        "Respond to the patient in clear, natural English. Every patient-visible "
        "question, option, explanation, and next step must be in English."
    )
