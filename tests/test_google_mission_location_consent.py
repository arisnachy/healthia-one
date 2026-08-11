from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from healthia_one.google_constellation import (
    GrantBundle,
    GoogleAction,
    GoogleActionRequest,
    GoogleGrant,
    authorize_google_action,
    utc_now,
)
from healthia_one.google_mission_runtime import MemoryMissionStore, MissionState
from healthia_one.google_navigation_coordinator import HealthIAGoogleMissionCoordinator

ROOT = Path(__file__).resolve().parents[1]


class _MustNotExecute:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("Places connector must not run before mission-scoped location consent")


def _request(mission_id: str) -> GoogleActionRequest:
    return GoogleActionRequest(
        patient_id="patient-a",
        mission_id=mission_id,
        action=GoogleAction.MAPS_TEXT_SEARCH,
        payload={"provider_query": "clinic", "location_text": "Santiago"},
    )


def test_mission_scoped_location_grant_cannot_authorize_another_mission() -> None:
    grant = GoogleGrant.mission_scoped(
        patient_id="patient-a",
        bundle=GrantBundle.MAPS_LOCATION,
        mission_id="mission-a",
        ttl_minutes=30,
    )
    assert authorize_google_action(_request("mission-a"), [grant]).allowed is True
    other = authorize_google_action(_request("mission-b"), [grant])
    assert other.allowed is False
    assert GrantBundle.MAPS_LOCATION in other.missing_grants


def test_expired_mission_location_grant_is_not_active() -> None:
    grant = GoogleGrant.mission_scoped(
        patient_id="patient-a",
        bundle=GrantBundle.MAPS_LOCATION,
        mission_id="mission-a",
        ttl_minutes=30,
    )
    grant.expires_at = utc_now() - timedelta(seconds=1)
    decision = authorize_google_action(_request("mission-a"), [grant])
    assert decision.allowed is False
    assert GrantBundle.MAPS_LOCATION in decision.missing_grants


def test_existing_account_level_grant_remains_backward_compatible() -> None:
    grant = GoogleGrant(patient_id="patient-a", bundle=GrantBundle.MAPS_LOCATION)
    assert authorize_google_action(_request("mission-a"), [grant]).allowed is True
    assert authorize_google_action(_request("mission-b"), [grant]).allowed is True


def test_discovery_stops_before_connector_without_location_consent() -> None:
    store = MemoryMissionStore()
    coordinator = HealthIAGoogleMissionCoordinator(_MustNotExecute(), store=store)
    mission = coordinator.create_navigation_mission(
        patient_id="patient-a",
        condition_or_need="follow-up support",
        provider_query="clinic",
        location_text="Santiago",
    )
    result = coordinator.discover(mission, [])
    assert result.state == MissionState.BLOCKED
    boundary = result.tool_outputs["authorization_boundary"]
    assert boundary["kind"] == "maps_location_for_mission"
    assert boundary["mission_id"] == mission.id
    assert boundary["external_action_performed"] is False
    assert boundary["scope"] == "this_mission_only"
    assert not result.tool_outputs.get("place_candidates")
    assert result.public_events[-1].event_type == "maps.location_consent_required"


def test_authorize_location_api_is_consent_only_not_search_or_external_write() -> None:
    source = (ROOT / "healthia_one/google_constellation_api.py").read_text(encoding="utf-8")
    assert '@router.post("/missions/{mission_id}/authorize-location")' in source
    assert "MissionLocationConsentRequest" in source
    assert "GrantBundle.MAPS_LOCATION" in source
    assert "mission_id=mission_id" in source
    assert "ttl_minutes=payload.ttl_minutes" in source
    assert '"external_action_performed": False' in source
    assert '"search_performed": False' in source
    assert "No Places search" in source


def test_conversational_location_consent_is_explicit_and_not_model_created() -> None:
    source = (ROOT / "healthia_one/google_mission_chat.py").read_text(encoding="utf-8")
    assert "Autorizo ubicación para esta misión" in source
    assert "maps_location_for_mission" in source
    assert 'actor="patient"' in source
    assert 'action="authorize_google_location_for_mission"' in source
    assert "ttl_minutes=30" in source
    assert "Todavía no hice la búsqueda" in source
