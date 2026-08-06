from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any


MIN_GOOGLE_GENAI_MAJOR = 2


def interaction_text(interaction: Any) -> str:
    direct = getattr(interaction, "output_text", "")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    outputs = getattr(interaction, "outputs", None) or []
    for output in reversed(outputs):
        text = getattr(output, "text", "")
        if isinstance(text, str) and text.strip():
            return text.strip()
        if isinstance(output, dict):
            text = output.get("text", "")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def classify_error(exc: Exception) -> str:
    message = str(exc).lower()
    if any(token in message for token in ("api key", "unauthenticated", "permission denied", "401", "403")):
        return "auth"
    if any(token in message for token in ("quota", "resource exhausted", "429", "rate limit")):
        return "quota"
    if any(token in message for token in ("model", "not found", "404")):
        return "model"
    if any(token in message for token in ("interaction", "attributeerror", "version")):
        return "sdk"
    return "network_or_service"


def verify() -> int:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model_name = os.getenv("HEALTHIA_MODEL", "gemini-3.6-flash").strip()
    if not api_key:
        print("HEALTHIA_GOOGLE_AI_ERROR category=auth detail=missing_api_key", file=sys.stderr)
        return 2

    try:
        sdk_version = version("google-genai")
    except PackageNotFoundError:
        print("HEALTHIA_GOOGLE_AI_ERROR category=sdk detail=google_genai_not_installed", file=sys.stderr)
        return 3

    try:
        major = int(sdk_version.split(".", 1)[0])
    except (TypeError, ValueError):
        print(
            f"HEALTHIA_GOOGLE_AI_ERROR category=sdk detail=invalid_sdk_version value={sdk_version}",
            file=sys.stderr,
        )
        return 3

    if major < MIN_GOOGLE_GENAI_MAJOR:
        print(
            f"HEALTHIA_GOOGLE_AI_ERROR category=sdk detail=incompatible_sdk version={sdk_version}",
            file=sys.stderr,
        )
        return 3

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        if not hasattr(client, "interactions"):
            raise RuntimeError("Interactions API is unavailable in the installed google-genai SDK")
        interaction = client.interactions.create(
            model=model_name,
            input="Reply only with HEALTHIA_OK",
            system_instruction="Minimal technical readiness check. Return no other text.",
            store=False,
        )
        text = interaction_text(interaction)
        if not text:
            raise RuntimeError("Gemini returned no usable text")
    except Exception as exc:
        category = classify_error(exc)
        detail = f"{type(exc).__name__}:{exc}".replace("\r", " ").replace("\n", " ")[:360]
        print(f"HEALTHIA_GOOGLE_AI_ERROR category={category} detail={detail}", file=sys.stderr)
        return 4

    print(
        "HEALTHIA_GOOGLE_AI_READY "
        f"model={model_name} sdk={sdk_version} stateless=true response={text[:32].replace(' ', '_')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(verify())
