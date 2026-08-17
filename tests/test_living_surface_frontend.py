from pathlib import Path


SOURCE = Path(__file__).parents[1] / "web" / "living-surface.js"


def test_main_living_surface_uses_patient_bootstrap_and_google_mission_route_only() -> None:
    script = SOURCE.read_text(encoding="utf-8")

    assert "healthia:state-updated" in script
    assert "/api/google-constellation/missions/" in script
    assert "public_events" in script
    assert "/api/evaluation" not in script
    assert "X-HealthIA-Evaluation-Key" not in script
    assert "private_reasoning" not in script
    assert "item.actor" not in script


def test_main_living_surface_never_renders_google_private_payload_fields() -> None:
    script = SOURCE.read_text(encoding="utf-8")

    for field in ("tool_outputs", "action_authorizations", "provider_email", "gmail_thread_id"):
        assert f"mission.{field}" not in script
