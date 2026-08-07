from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HEALTHIA_", env_file=".env", extra="ignore")

    env: str = "local"
    model: str = "gemini-3.6-flash"
    llm_backend: str = "mock"
    store_backend: str = "json"
    data_path: Path = Path(".healthia-one/state.json")
    # Demand-driven by default: no periodic agent wake-up loop.
    proactive_interval_seconds: int = 20
    proactive_enabled: bool = False
    max_upload_bytes: int = 5 * 1024 * 1024
    llm_timeout_seconds: int = 30

    # Cost safety defaults: no billable request unless explicitly enabled.
    cost_mode: str = "local"
    ai_request_limit: int = 0
    cost_guard_start_enabled: bool = False
    cost_control_ui: bool = True
    ai_max_output_tokens: int = 1400

    # Patient account boundary. Tests and static demo can leave auth disabled;
    # the secure local launcher and Cloud deployment enable it explicitly.
    auth_required: bool = False
    allow_registration: bool = True
    accounts_path: Path = Path(".healthia-one/accounts.json")
    session_cookie_name: str = "healthia_session"
    session_hours: int = 12

    @property
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


settings = Settings()