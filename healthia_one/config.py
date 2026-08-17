from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HEALTHIA_", env_file=".env", extra="ignore")

    env: str = "local"
    # Hackathon final model: Gemini 3.5 Flash or newer is required.
    model: str = "gemini-3.5-flash"
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

    # Enterprise AI ingress defense. The local deterministic injection filter is
    # always available; Google Model Armor is opt-in and fails closed once
    # enabled unless the deployment explicitly chooses otherwise.
    model_armor_enabled: bool = False
    model_armor_fail_closed: bool = True
    model_armor_location: str = "us-central1"
    model_armor_template_id: str = ""

    # OpenTelemetry is opt-in locally. Cloud deployments can export the same
    # sanitized spans to Google Cloud Trace without placing PHI in attributes.
    otel_enabled: bool = False
    cloud_trace_enabled: bool = False
    otel_service_name: str = "healthia-one"

    # Explicit, bounded, synthetic-only evaluation capability. Disabled unless
    # the deployment owner deliberately enables it and supplies an access key.
    evaluation_enabled: bool = False
    evaluation_access_key: str = ""
    evaluation_session_minutes: int = 30
    evaluation_max_sessions: int = 2
    evaluation_max_runs: int = 2
    release_sha: str = "local"

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
    def google_cloud_project(self) -> str:
        import os

        return os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()

    @property
    def adk_ready(self) -> bool:
        if self.llm_backend == "mock":
            return False
        import os

        if self.vertex_ai_enabled:
            return bool(os.getenv("GOOGLE_CLOUD_PROJECT"))
        return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


settings = Settings()