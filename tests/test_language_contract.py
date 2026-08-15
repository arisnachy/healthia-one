from __future__ import annotations

from healthia_one.language import (
    bind_requested_locale,
    current_requested_locale,
    detect_text_language,
    language_instruction,
    normalize_locale,
    reset_requested_locale,
    resolve_response_locale,
)


def test_locale_normalization_supports_shipped_multilingual_content_locales() -> None:
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("es-DO") == "es"
    assert normalize_locale("fr-FR") == "fr"
    assert normalize_locale("pt-BR") == "pt"
    assert normalize_locale("ja-JP") == "ja"
    # Truly unsupported locales still fail closed to the known fallback.
    assert normalize_locale("sv-SE") == "en"


def test_input_language_overrides_operating_system_locale() -> None:
    assert resolve_response_locale(
        "Desde ayer tengo dolor al orinar y quiero saber qué hacer",
        requested_locale="en-US",
        profile_locale="en-US",
    ) == "es"
    assert resolve_response_locale(
        "I have had pain since yesterday and I want help understanding it",
        requested_locale="es-DO",
        profile_locale="es-DO",
    ) == "en"
    assert resolve_response_locale(
        "Tenho dor e quero ajuda para entender este resultado",
        requested_locale="en-US",
        profile_locale="en-US",
    ) == "pt"


def test_low_confidence_input_falls_back_to_requested_os_language() -> None:
    assert detect_text_language("126/78") is None
    assert resolve_response_locale("126/78", requested_locale="es-DO", profile_locale="en-US") == "es"
    assert resolve_response_locale("126/78", requested_locale="en-US", profile_locale="es-DO") == "en"
    assert resolve_response_locale("126/78", requested_locale="fr-FR", profile_locale="en-US") == "fr"


def test_request_locale_context_is_resettable() -> None:
    before = current_requested_locale()
    token = bind_requested_locale("es-DO")
    try:
        assert current_requested_locale() == "es"
    finally:
        reset_requested_locale(token)
    assert current_requested_locale() == before


def test_model_language_instruction_is_explicit() -> None:
    assert "English" in language_instruction("en")
    assert "español" in language_instruction("es")
    assert "French" in language_instruction("fr")
    assert "Brazilian Portuguese" in language_instruction("pt")
    assert "German" in language_instruction("de")
