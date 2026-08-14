from healthia_one.gemini_tts_connector import GeminiTextToSpeechConnector


def test_gemini_tts_uses_long_form_http_timeout():
    connector = GeminiTextToSpeechConnector(token_provider=object())
    assert connector.transport.timeout_seconds >= 90
