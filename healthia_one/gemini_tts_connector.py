from __future__ import annotations

import os
from typing import Any

from healthia_one.google_clinical_cloud_connectors import AdcConnectorBase
from healthia_one.google_connector_runtime import ConnectorResult, GoogleConnectorError
from healthia_one.google_constellation import GoogleAction, GoogleService


class GeminiTextToSpeechConnector(AdcConnectorBase):
    """Cloud Text-to-Speech connector with optional Gemini TTS controls.

    It preserves the existing HealthIA GoogleAction / grant / receipt boundary.
    Callers that do not request a Gemini model continue to receive ordinary
    Cloud TTS behavior, while HealthIA Explain can select a promptable Gemini
    TTS model and a prebuilt voice.
    """

    service = GoogleService.TEXT_TO_SPEECH

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action != GoogleAction.TEXT_TO_SPEECH_SYNTHESIZE:
            raise GoogleConnectorError(f"Unsupported Text-to-Speech action: {action}")

        text = str(payload.get("text") or "").strip()
        if not text:
            raise GoogleConnectorError("Text-to-Speech input is empty")
        # Gemini TTS currently allows 4,000 bytes in each text/prompt field.
        if len(text.encode("utf-8")) > 4000:
            raise GoogleConnectorError("Gemini Text-to-Speech text exceeds the 4000-byte unary limit")

        language_code = str(payload.get("language_code") or "en-US").strip()[:32]
        audio_encoding = str(payload.get("audio_encoding") or "MP3").strip().upper()
        model_name = str(payload.get("model_name") or "").strip()
        voice_name = str(payload.get("voice_name") or "").strip()
        style_prompt = str(payload.get("style_prompt") or "").strip()
        if len(style_prompt.encode("utf-8")) > 4000:
            raise GoogleConnectorError("Gemini Text-to-Speech style prompt exceeds the 4000-byte unary limit")

        synthesis_input: dict[str, Any] = {"text": text}
        voice: dict[str, Any] = {"languageCode": language_code}
        if model_name:
            if not model_name.startswith("gemini-") or not model_name.endswith("-tts"):
                raise GoogleConnectorError("Unsupported Gemini TTS model name")
            voice["modelName"] = model_name
            voice["name"] = voice_name or "Charon"
            if style_prompt:
                synthesis_input["prompt"] = style_prompt
        elif voice_name:
            voice["name"] = voice_name

        audio_config: dict[str, Any] = {"audioEncoding": audio_encoding}
        if payload.get("sample_rate_hertz"):
            audio_config["sampleRateHertz"] = int(payload["sample_rate_hertz"])

        headers = self._headers()
        project_id = str(os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
        if project_id:
            headers["x-goog-user-project"] = project_id

        body = {"input": synthesis_input, "voice": voice, "audioConfig": audio_config}
        result = self.transport.call(
            "POST",
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            headers=headers,
            body=body,
        )
        audio_content = str(result.get("audioContent") or "")
        if not audio_content:
            raise GoogleConnectorError("Text-to-Speech returned no audio content")
        return ConnectorResult(
            safe_summary="Synthesized one private patient-facing audio response.",
            data={
                "audio_content_base64": audio_content,
                "audio_encoding": audio_encoding,
                "language_code": language_code,
                "model_name": model_name,
                "voice_name": voice.get("name", ""),
            },
        )
