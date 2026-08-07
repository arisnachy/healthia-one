from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"migration anchor not found: {label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


root = Path.cwd()

# 1) Settings: Vertex AI uses Google Cloud ADC/project identity, not GEMINI_API_KEY.
config = root / "healthia_one" / "config.py"
replace_once(
    config,
    '''    @property
    def adk_ready(self) -> bool:
        if self.llm_backend == "mock":
            return False
        import os
        return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
''',
    '''    @property
    def vertex_ai_enabled(self) -> bool:
        import os

        return os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in {"1", "true", "yes", "on"}

    @property
    def adk_ready(self) -> bool:
        if self.llm_backend == "mock":
            return False
        import os

        if self.vertex_ai_enabled:
            return bool(os.getenv("GOOGLE_CLOUD_PROJECT"))
        return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
''',
    "config.adk_ready",
)

# 2) Transport adapter: preserve HealthIA's stateless interactions contract while
# routing Vertex calls through generateContent. This keeps clinical safety logic,
# multimodal ingestion and ADK orchestration unchanged.
adapter = root / "healthia_one" / "google_ai_transport.py"
adapter.write_text(
    '''from __future__ import annotations

import base64
import json
import os
from types import SimpleNamespace
from typing import Any


class VertexInteractionsAdapter:
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
''',
    encoding="utf-8",
)

# 3) Gemini boundary: centralize client construction in the dual transport.
gemini = root / "healthia_one" / "gemini.py"
replace_once(
    gemini,
    'from healthia_one.cost_guard import CostGuard, CostGuardBlocked\n',
    'from healthia_one.cost_guard import CostGuard, CostGuardBlocked\nfrom healthia_one.google_ai_transport import build_google_ai_client\n',
    "gemini.transport_import",
)
replace_once(
    gemini,
    '''            else:
                from google import genai

                api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise RuntimeError("GEMINI_API_KEY no está configurada para el proceso actual")
                self._client = genai.Client(api_key=api_key)
''',
    '''            else:
                self._client = build_google_ai_client(self.settings)
''',
    "gemini._get_client",
)
replace_once(
    gemini,
    '"api_key_configured": self.settings.adk_ready,\n',
    '"google_ai_configured": self.settings.adk_ready,\n                "ai_transport": "vertex_ai" if self.settings.vertex_ai_enabled else "developer_api",\n',
    "gemini.cost_status",
)
replace_once(
    gemini,
    'raise CostGuardBlocked("No hay una API key configurada para esta ejecución local.")',
    'raise CostGuardBlocked("Google AI no está configurado para esta ejecución local.")',
    "gemini.local_guard_message",
)

# 4) Taskmaster proof: accept Vertex ADC/project instead of requiring a Gemini key.
proof = root / "scripts" / "live_taskmaster_proof.py"
replace_once(
    proof,
    '''    required = ["GEMINI_API_KEY", "HEALTHIA_SESSION_SECRET", "HEALTHIA_DEVICE_TOKEN_SECRET"]
    if any(not os.getenv(name) for name in required):
        print("HEALTHIA_TASKMASTER_PROOF_BLOCKED: missing required secret environment")
        return 2
''',
    '''    vertex_enabled = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in {"1", "true", "yes", "on"}
    required = ["HEALTHIA_SESSION_SECRET", "HEALTHIA_DEVICE_TOKEN_SECRET"]
    required.append("GOOGLE_CLOUD_PROJECT" if vertex_enabled else "GEMINI_API_KEY")
    if any(not os.getenv(name) for name in required):
        print("HEALTHIA_TASKMASTER_PROOF_BLOCKED: missing required AI/auth environment")
        return 2
''',
    "taskmaster.required_environment",
)
replace_once(
    proof,
    '''        "gemini_request_ceiling": 1,
        "checks": [],
''',
    '''        "gemini_request_ceiling": 1,
        "ai_transport": "vertex_ai" if vertex_enabled else "developer_api",
        "google_cloud_project": os.getenv("GOOGLE_CLOUD_PROJECT", "") if vertex_enabled else "",
        "checks": [],
''',
    "taskmaster.proof_metadata",
)

# 5) Document the preferred Cloud transport without storing credentials.
env_example = root / ".env.example"
replace_once(
    env_example,
    '''# Configure only for an explicit guarded run. Never commit a real key.
GEMINI_API_KEY=
GOOGLE_CLOUD_PROJECT=
HEALTHIA_GCS_BUCKET=
''',
    '''# Configure one Google AI transport for an explicit guarded run. Never commit credentials.
# Gemini Developer API / AI Studio:
GEMINI_API_KEY=
# Vertex AI / Google Cloud ADC (preferred for Cloud deployment):
GOOGLE_GENAI_USE_VERTEXAI=false
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=global
HEALTHIA_GCS_BUCKET=
''',
    ".env.vertex_settings",
)

# 6) Regression contract for transport readiness.
(root / "tests" / "test_vertex_transport.py").write_text(
    '''from __future__ import annotations

from healthia_one.config import Settings


def test_vertex_readiness_uses_project_not_gemini_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "healthia-test-project")
    settings = Settings(llm_backend="gemini_api")
    assert settings.vertex_ai_enabled is True
    assert settings.adk_ready is True


def test_vertex_readiness_fails_closed_without_project(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    settings = Settings(llm_backend="gemini_api")
    assert settings.vertex_ai_enabled is True
    assert settings.adk_ready is False
''',
    encoding="utf-8",
)

print("HEALTHIA_VERTEX_MIGRATION_PATCHED")
