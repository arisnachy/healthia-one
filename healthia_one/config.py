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

    # ONE SAFETY is deliberately off for local/test runs but automatically
    # becomes fail-closed in HEALTHIA_ENV=cloud. Set
    # HEALTHIA_ONE_SAFETY_AUTO_ENABLE_CLOUD=false only for an explicitly
    # controlled recovery deployment.
    one_safety_auto_enable_cloud: bool = True

    # Enterprise AI ingress defense. The deterministic local injection filter
    # is always available. Cloud mode additionally enables Google Model Armor.
    model_armor_enabled: bool = False
    model_armor_fail_closed: bool = True
    model_armor_location: str = "us-central1"
    model_armor_template_id: str = "healthia-one-safety"

    # OpenTelemetry is off locally. Cloud mode automatically exports the same
    # sanitized spans to Google Cloud Trace; callers must never attach PHI.
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

    # Patient identity is secure by default. Tests or an explicitly isolated
    # static demo must opt out; Cloud mode cannot disable this boundary.
    auth_required: bool = True
    allow_registration: bool = True
    accounts_path: Path = Path(".healthia-one/accounts.json")
    session_cookie_name: str = "healthia_session"
    session_hours: int = 12
    login_attempt_limit: int = 5
    login_ip_attempt_limit: int = 12
    login_window_seconds: int = 300
    pairing_attempt_limit: int = 8
    pairing_window_seconds: int = 300

    def model_post_init(self, __context) -> None:
        # Every production Cloud Run deployment already declares
        # HEALTHIA_ENV=cloud. Binding ONE SAFETY to that deployment contract
        # prevents Model Armor/Trace from being silently omitted by an older
        # deploy script or workflow. Local/tests remain network-free by default.
        if self.env.strip().lower() == "cloud":
            self.auth_required = True
        if self.env.strip().lower() == "cloud" and self.one_safety_auto_enable_cloud:
            self.model_armor_enabled = True
            self.otel_enabled = True
            self.cloud_trace_enabled = True
            if not self.model_armor_template_id.strip():
                self.model_armor_template_id = "healthia-one-safety"

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
