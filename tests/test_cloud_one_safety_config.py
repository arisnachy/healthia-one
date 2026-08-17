from healthia_one.config import Settings


def test_one_safety_stays_off_by_default_for_local_test_runs():
    settings = Settings(_env_file=None, env="local")
    assert settings.model_armor_enabled is False
    assert settings.otel_enabled is False
    assert settings.cloud_trace_enabled is False
    assert settings.model_armor_template_id == "healthia-one-safety"


def test_one_safety_auto_enables_for_cloud_run_contract():
    settings = Settings(_env_file=None, env="cloud")
    assert settings.model_armor_enabled is True
    assert settings.model_armor_fail_closed is True
    assert settings.model_armor_location == "us-central1"
    assert settings.model_armor_template_id == "healthia-one-safety"
    assert settings.otel_enabled is True
    assert settings.cloud_trace_enabled is True


def test_explicit_cloud_recovery_switch_can_disable_auto_enable():
    settings = Settings(
        _env_file=None,
        env="cloud",
        one_safety_auto_enable_cloud=False,
        model_armor_enabled=False,
        otel_enabled=False,
        cloud_trace_enabled=False,
    )
    assert settings.model_armor_enabled is False
    assert settings.otel_enabled is False
    assert settings.cloud_trace_enabled is False
