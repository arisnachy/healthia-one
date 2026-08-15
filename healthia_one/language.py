from __future__ import annotations

import re
import unicodedata
from contextvars import ContextVar, Token

# Patient-facing content can follow the language used by the patient even when
# the browser/OS interface uses a different locale. Keep this list explicit so
# unsupported languages fail to a known interface language instead of silently
# inventing a locale tag.
SUPPORTED_LANGUAGES = {
    "ar", "de", "en", "es", "fr", "hi", "id", "it", "ja", "ko", "nl",
    "pl", "pt", "ro", "ru", "tr", "uk", "vi", "zh",
}

# Canonical BCP-47 locale used by Gemini TTS for each content language. These
# are intentionally independent from the browser locale: e.g. an es-DO browser
# can still receive an English video when the patient writes in English.
TTS_LOCALES = {
    "ar": "ar-EG",
    "de": "de-DE",
    "en": "en-US",
    "es": "es-419",
    "fr": "fr-FR",
    "hi": "hi-IN",
    "id": "id-ID",
    "it": "it-IT",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "nl": "nl-NL",
    "pl": "pl-PL",
    "pt": "pt-BR",
    "ro": "ro-RO",
    "ru": "ru-RU",
    "tr": "tr-TR",
    "uk": "uk-UA",
    "vi": "vi-VN",
    "zh": "cmn-CN",
}

LANGUAGE_NAMES = {
    "ar": "Arabic",
    "de": "German",
    "en": "English",
    "es": "Latin American Spanish",
    "fr": "French",
    "hi": "Hindi",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Brazilian Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "zh": "Mandarin Chinese",
}

_REQUESTED_LOCALE: ContextVar[str | None] = ContextVar("healthia_requested_locale", default=None)


def _base_language(value: str | None) -> str:
    raw = str(value or "").strip().replace("_", "-")
    if not raw:
        return ""
    language = raw.split("-", 1)[0].lower()
    # Browser Chinese locale tags use zh while Gemini TTS exposes cmn-CN.
    if language == "cmn":
        return "zh"
    return language


def normalize_locale(value: str | None, *, fallback: str = "en") -> str:
    language = _base_language(value)
    if language in SUPPORTED_LANGUAGES:
        return language
    fallback_language = _base_language(fallback)
    return fallback_language if fallback_language in SUPPORTED_LANGUAGES else "en"


def tts_locale(value: str | None, *, fallback: str = "en") -> str:
    return TTS_LOCALES[normalize_locale(value, fallback=fallback)]


def bind_requested_locale(value: str | None) -> Token:
    return _REQUESTED_LOCALE.set(normalize_locale(value) if value else None)


def reset_requested_locale(token: Token) -> None:
    _REQUESTED_LOCALE.reset(token)


def current_requested_locale() -> str | None:
    return _REQUESTED_LOCALE.get()


def _latin_normalized(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _token_score(sample: str, tokens: tuple[str, ...]) -> int:
    return sum(1 for token in tokens if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", sample))


def detect_text_language(text: str) -> str | None:
    """Conservatively detect the language used in the current patient turn.

    This detector is deliberately bounded: it chooses response/video language,
    never clinical meaning. Script-based languages are reliable from Unicode;
    closely related Latin-script languages require multiple lexical signals.
    Low-confidence text returns None so the browser/profile locale stays the
    fallback instead of guessing from a short answer like "ok".
    """

    raw = str(text or "").strip()
    if not raw:
        return None

    # High-confidence script detection.
    if re.search(r"[\u3040-\u30ff]", raw):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", raw):
        return "ko"
    if re.search(r"[\u4e00-\u9fff]", raw):
        return "zh"
    if re.search(r"[\u0600-\u06ff]", raw):
        return "ar"
    if re.search(r"[\u0900-\u097f]", raw):
        return "hi"
    if re.search(r"[\u0400-\u04ff]", raw):
        lowered = raw.casefold()
        ukrainian_marks = ("і", "ї", "є", "ґ")
        return "uk" if any(mark in lowered for mark in ukrainian_marks) else "ru"

    sample = _latin_normalized(raw)
    lexicons: dict[str, tuple[str, ...]] = {
        "es": ("que", "como", "tengo", "dolor", "quiero", "explica", "presion", "fiebre", "ayuda", "resultado", "medicamento", "gracias"),
        "en": ("what", "how", "have", "pain", "want", "explain", "pressure", "fever", "help", "result", "medicine", "please"),
        "pt": ("que", "como", "tenho", "dor", "quero", "explica", "pressao", "febre", "ajuda", "resultado", "medicamento", "obrigado"),
        "fr": ("quoi", "comment", "douleur", "veux", "explique", "pression", "fievre", "aide", "resultat", "medicament", "merci"),
        "de": ("was", "wie", "habe", "schmerz", "mochte", "erklar", "blutdruck", "fieber", "hilfe", "ergebnis", "medikament", "danke"),
        "it": ("cosa", "come", "dolore", "voglio", "spiega", "pressione", "febbre", "aiuto", "risultato", "farmaco", "grazie"),
        "nl": ("wat", "hoe", "pijn", "wil", "leg", "bloeddruk", "koorts", "hulp", "uitslag", "medicijn", "dank"),
        "pl": ("co", "jak", "bol", "chce", "wyjasnij", "cisnienie", "goraczka", "pomoc", "wynik", "lek", "dziekuje"),
        "ro": ("ce", "cum", "durere", "vreau", "explica", "tensiune", "febra", "ajutor", "rezultat", "medicament", "multumesc"),
        "tr": ("ne", "nasil", "agri", "istiyorum", "acikla", "tansiyon", "ates", "yardim", "sonuc", "ilac", "tesekkur"),
        "id": ("apa", "bagaimana", "sakit", "ingin", "jelaskan", "tekanan", "demam", "bantu", "hasil", "obat", "terima"),
        "vi": ("gi", "the", "dau", "muon", "giai", "huyet", "sot", "giup", "ket", "thuoc", "cam"),
    }
    scores = {language: _token_score(sample, words) for language, words in lexicons.items()}
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_language, best_score = ranked[0]
    second_score = ranked[1][1]

    # Orthographic hints can make Spanish/French/Portuguese confident with one
    # lexical signal, otherwise require at least two independent words.
    if best_language == "es" and any(ch in raw.casefold() for ch in "¿¡ñ") and best_score >= 1:
        return "es"
    if best_language in {"fr", "pt"} and best_score >= 1 and re.search(r"[çãõêôàèùâîû]", raw.casefold()):
        return best_language
    if best_score >= 2 and best_score > second_score:
        return best_language
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
            "Responde al paciente en español latinoamericano claro y natural. Todas las preguntas, "
            "opciones, explicaciones y próximos pasos visibles deben estar en español. Conserva nombres "
            "de medicamentos, cifras y unidades exactamente cuando procedan del expediente."
        )
    if language == "en":
        return (
            "Respond to the patient in clear, natural English. Every patient-visible question, option, "
            "explanation, and next step must be in English. Preserve medication names, values, and units "
            "exactly when they come from the patient record."
        )
    name = LANGUAGE_NAMES[language]
    return (
        f"Respond to the patient entirely in natural {name}. Every patient-visible question, option, "
        f"explanation, and next step must be in {name}. Do not mix in English or Spanish except for proper "
        "names that should not be translated. Preserve medication names, numerical values, units, and "
        "quoted clinical evidence exactly when they come from the patient record."
    )
