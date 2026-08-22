from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _cold_boot_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HEALTHIA_ENV": "local",
            "HEALTHIA_LLM_BACKEND": "mock",
            "HEALTHIA_STORE_BACKEND": "memory",
            "HEALTHIA_AUTH_REQUIRED": "false",
            "HEALTHIA_PROACTIVE_ENABLED": "false",
            "HEALTHIA_MODEL_ARMOR_ENABLED": "false",
            "HEALTHIA_OTEL_ENABLED": "false",
            "HEALTHIA_CLOUD_TRACE_ENABLED": "false",
            "HEALTHIA_SESSION_SECRET": "cold-boot-session-secret-0123456789abcdef0123456789abcdef",
            "HEALTHIA_DEVICE_TOKEN_SECRET": "cold-boot-device-secret-0123456789abcdef0123456789abcdef",
        }
    )
    for key in (
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "HEALTHIA_GCS_BUCKET",
    ):
        env.pop(key, None)
    env["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
    return env


def test_production_entrypoint_imports_without_optional_cloud_credentials() -> None:
    """A clean local/mock process must be able to import the production entrypoint.

    This catches import-time regressions before browser, integration and release
    verification. No network access, Google credential or model call is allowed.
    """

    code = r'''
import app.main as main
assert main.app.title == "HealthIA ONE"
routes = {getattr(route, "path", None) for route in main.app.routes}
for required in ("/", "/healthz", "/api/readiness", "/api/chat", "/api/bootstrap"):
    assert required in routes, required
assert main.settings.llm_backend == "mock"
assert main.settings.store_backend == "memory"
assert main.settings.adk_ready is False
print("HEALTHIA_COLD_BOOT_IMPORT_PASS")
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=_cold_boot_env(),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "HEALTHIA_COLD_BOOT_IMPORT_PASS" in completed.stdout


def test_production_entrypoint_survives_clean_process_restart() -> None:
    """Two independent processes must both import the same production entrypoint."""

    code = "import app.main; print('HEALTHIA_RESTART_BOOT_PASS')"
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=_cold_boot_env(),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "HEALTHIA_RESTART_BOOT_PASS" in completed.stdout
