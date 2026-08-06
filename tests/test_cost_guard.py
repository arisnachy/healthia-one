import pytest

from healthia_one.config import Settings
from healthia_one.cost_guard import CostGuard, CostGuardBlocked


def test_settings_default_to_zero_spend_local_mode() -> None:
    settings = Settings()
    assert settings.llm_backend == "mock"
    assert settings.cost_mode == "local"
    assert settings.ai_request_limit == 0
    assert settings.cost_guard_start_enabled is False


def test_local_mode_cannot_issue_or_enable_model_requests() -> None:
    guard = CostGuard(mode="local", request_limit=10, start_enabled=True)
    assert guard.snapshot()["enabled"] is False
    assert guard.snapshot()["can_enable"] is False
    with pytest.raises(CostGuardBlocked):
        guard.authorize("test")
    with pytest.raises(CostGuardBlocked):
        guard.set_enabled(True)


def test_guarded_mode_counts_attempts_and_turns_off_at_the_ceiling() -> None:
    guard = CostGuard(mode="guarded", request_limit=2, start_enabled=False, max_output_tokens=500)
    guard.set_enabled(True)
    assert guard.authorize("first") == 1
    assert guard.snapshot()["enabled"] is True
    assert guard.authorize("second") == 2
    snapshot = guard.snapshot()
    assert snapshot["enabled"] is False
    assert snapshot["requests_used"] == 2
    assert snapshot["requests_remaining"] == 0
    assert snapshot["max_output_tokens"] == 500
    assert snapshot["estimated_spend_usd"] is None
    with pytest.raises(CostGuardBlocked):
        guard.authorize("third")


def test_guarded_mode_can_be_switched_off_immediately() -> None:
    guard = CostGuard(mode="guarded", request_limit=5, start_enabled=True)
    guard.set_enabled(False)
    assert guard.snapshot()["enabled"] is False
    with pytest.raises(CostGuardBlocked):
        guard.authorize("blocked")


def test_cloud_demo_mode_is_fixed_by_deployment_not_browser() -> None:
    guard = CostGuard(mode="cloud_demo", request_limit=4, start_enabled=True)
    assert guard.snapshot()["enabled"] is True
    assert guard.snapshot()["mutable"] is False
    with pytest.raises(CostGuardBlocked):
        guard.set_enabled(False)
