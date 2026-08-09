from pathlib import Path

from healthia_one.config import Settings
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.google_mission_adk import AdkGoogleMissionRuntime, GoogleMissionToolFacade


ADK_SOURCE = Path("healthia_one/google_mission_adk.py").read_text(encoding="utf-8")


def test_adk_tool_surface_contains_no_authorize_grant_oauth_or_raw_google_mutation_tool(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    runtime = AdkGoogleMissionRuntime(Settings(store_backend="memory", llm_backend="mock"), constellation=service)
    names = runtime.tool_names()
    joined = " ".join(names).lower()
    assert "authorize" not in joined
    assert "grant" not in joined
    assert "oauth" not in joined
    assert "gmail_send" not in joined
    assert "calendar_create_event" not in joined
    assert "drive_export" not in joined
    assert "tasks_create" not in joined
    assert "contact_selected_provider" in names
    assert "finalize_selected_appointment" in names


def test_google_mission_adk_uses_same_gemini_json_generation_contract_as_clinical_runtime():
    assert "from google.adk.models.google_llm import Gemini" in ADK_SOURCE
    assert "model=Gemini(" in ADK_SOURCE
    assert "types.HttpRetryOptions(attempts=2)" in ADK_SOURCE
    assert "generate_content_config=types.GenerateContentConfig(" in ADK_SOURCE
    assert 'response_mime_type="application/json"' in ADK_SOURCE
    assert "response_json_schema=MISSION_PLAN_SCHEMA" in ADK_SOURCE
    assert "output_schema=MISSION_PLAN_SCHEMA" not in ADK_SOURCE


def test_navigation_tool_refuses_to_invent_coordinates_or_location(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    facade = GoogleMissionToolFacade(
        constellation=service,
        patient_id="patient_demo",
        authorized_location=None,
        patient_text="Búscame un centro de apoyo",
    )
    result = facade.start_navigation_mission("autism support", "autism support center", location_text="Santiago")
    assert result["ok"] is False
    assert result["state"] == "location_required"
    assert "must not invent latitude/longitude or a place" in result["public_summary"]


def test_navigation_tool_uses_patient_explicit_text_without_claiming_residence(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    facade = GoogleMissionToolFacade(
        constellation=service,
        patient_id="patient_demo",
        authorized_location=None,
        patient_text="Búscame un centro de autismo en Santiago",
    )
    result = facade.start_navigation_mission(
        "autism support",
        "autism support center",
        location_text="Santiago",
    )
    assert result["ok"] is True
    mission = service.load_mission("patient_demo", result["mission_id"])
    assert mission.location["text"] == "Santiago"
    assert mission.location["source"] == "patient_explicit_search_text"
    assert mission.location["is_residence"] is False


def test_navigation_tool_does_not_expand_patient_location_text(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    facade = GoogleMissionToolFacade(
        constellation=service,
        patient_id="patient_demo",
        authorized_location=None,
        patient_text="Busca una clínica en Santiago",
    )
    result = facade.start_navigation_mission(
        "therapy",
        "therapy clinic",
        location_text="Santiago, Dominican Republic",
    )
    assert result["ok"] is False
    assert result["state"] == "location_required"


def test_navigation_tool_uses_only_pre_authorized_location(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    facade = GoogleMissionToolFacade(
        constellation=service,
        patient_id="patient_demo",
        authorized_location={"lat": 19.4517, "lng": -70.6970},
        patient_text="Búscame un centro en Santiago",
    )
    result = facade.start_navigation_mission(
        "autism support",
        "autism support center",
        location_text="Santiago",
    )
    assert result["ok"] is True
    mission = service.load_mission("patient_demo", result["mission_id"])
    assert mission.location["lat"] == 19.4517
    assert mission.location["lng"] == -70.697
    assert mission.location["source"] == "patient_authorized_coordinates"
    assert mission.location["is_residence"] is False
    assert "text" not in mission.location


def test_contact_tool_without_verified_provider_email_cannot_fabricate_destination(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    facade = GoogleMissionToolFacade(
        constellation=service,
        patient_id="patient_demo",
        authorized_location={"lat": 19.4517, "lng": -70.6970},
    )
    started = facade.start_navigation_mission("support", "support center")
    mission = service.load_mission("patient_demo", started["mission_id"])
    mission.provider_email = ""
    service.coordinator.store.save(mission)
    result = facade.contact_selected_provider(mission.id, "Appointment", "Please advise.")
    assert result["ok"] is False
    assert result["next_action"] == "resolve_verified_provider_contact"
