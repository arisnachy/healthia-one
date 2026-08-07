from __future__ import annotations

import base64
import json
import os
from types import SimpleNamespace
from typing import Any


class VertexInteractionsAdapter:
    """Adapt HealthIA's stateless Interactions-style boundary to Vertex generateContent.

    The adapter preserves the controls HealthIA depends on instead of silently
    dropping them: output-token ceiling, thinking level, temperature and JSON
    structured-output constraints.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    @staticmethod
    def _contents(value: Any) -> Any:
        from google.genai import types

        if not isinstance(value, list):
            return value
        parts: list[Any] = []
        for item in value:
            if isinstance(item, str):
                parts.append(types.Part.from_text(text=item))
                continue
            if not isinstance(item, dict):
                parts.append(item)
                continue
            kind = str(item.get("type") or "").lower()
            if kind == "text":
                parts.append(types.Part.from_text(text=str(item.get("text") or "")))
                continue
            if kind in {"image", "document"}:
                encoded = str(item.get("data") or "")
                mime_type = str(item.get("mime_type") or "application/octet-stream")
                parts.append(types.Part.from_bytes(data=base64.b64decode(encoded), mime_type=mime_type))
                continue
            parts.append(types.Part.from_text(text=json.dumps(item, ensure_ascii=False, default=str)))
        return [types.Content(role="user", parts=parts)]

    def create(
        self,
        *,
        model: str,
        input: Any,
        system_instruction: str | None = None,
        generation_config: dict[str, Any] | None = None,
        store: bool | None = None,
        **_kwargs: Any,
    ) -> Any:
        from google.genai import types

        raw = dict(generation_config or {})
        kwargs: dict[str, Any] = {}
        if system_instruction:
            kwargs["system_instruction"] = system_instruction
        if raw.get("max_output_tokens") is not None:
            kwargs["max_output_tokens"] = int(raw["max_output_tokens"])
        if raw.get("temperature") is not None:
            kwargs["temperature"] = float(raw["temperature"])
        if raw.get("thinking_level"):
            kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=str(raw["thinking_level"]).lower()
            )
        if raw.get("response_mime_type"):
            kwargs["response_mime_type"] = str(raw["response_mime_type"])
        if raw.get("response_json_schema") is not None:
            kwargs["response_json_schema"] = raw["response_json_schema"]
        elif raw.get("response_schema") is not None:
            kwargs["response_schema"] = raw["response_schema"]

        response = self._client.models.generate_content(
            model=model,
            contents=self._contents(input),
            config=types.GenerateContentConfig(**kwargs),
        )
        return SimpleNamespace(output_text=str(response.text or ""), raw=response, store=False)


class VertexClientAdapter:
    def __init__(self, client: Any) -> None:
        self._client = client
        self.models = client.models
        self.interactions = VertexInteractionsAdapter(client)


def build_google_ai_client(settings: Any) -> Any:
    from google import genai

    if settings.vertex_ai_enabled:
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT no está configurado para Vertex AI")
        return VertexClientAdapter(genai.Client(vertexai=True, project=project, location=location))

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY no está configurada para el proceso actual")
    return genai.Client(api_key=api_key)
