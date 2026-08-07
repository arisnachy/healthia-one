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
    llm_timeout_seconds: int = 18

    # Cost safety defaults: no billable request unless explicitly enabled.
    cost_mode: str = "local"
    ai_request_limit: int = 0
    cost_guard_start_enabled: bool = False
    cost_control_ui: bool = True
    ai_max_output_tokens: int = 700

    @property
    def adk_ready(self) -> bool:
        if self.llm_backend == "mock":
            return False
        import os
        return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


settings = Settings()
