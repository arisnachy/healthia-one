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



def test_conversational_location_consent_immediately_resumes_safe_places_discovery() -> None:
    import asyncio

    from healthia_one.google_connector_runtime import ConnectorResult
    from healthia_one.google_constellation import GoogleGrant, build_google_receipt
    from healthia_one.google_mission_chat import GoogleMissionConversationRouter
    from healthia_one.models import ChatMessage, PatientState

    class _PlacesExecutor:
        def execute(self, request, _grants):
            places = [
                {"id": "place-a", "displayName": {"text": "Clinic A"}, "formattedAddress": "Synthetic A"},
                {"id": "place-b", "displayName": {"text": "Clinic B"}, "formattedAddress": "Synthetic B"},
            ]
            receipt = build_google_receipt(
                request,
                status="completed",
                safe_summary="Found 2 synthetic place candidates.",
            )
            return receipt, ConnectorResult(safe_summary=receipt.safe_summary, data={"places": places})

    class _Constellation:
        def __init__(self, patient_id: str):
            self.store = MemoryMissionStore()
            self.coordinator = HealthIAGoogleMissionCoordinator(_PlacesExecutor(), store=self.store)
            self._grants = []
            self.patient_id = patient_id

        def load_mission(self, patient_id: str, mission_id: str):
            assert patient_id == self.patient_id
            mission = self.store.load(patient_id, mission_id)
            if mission is None:
                raise KeyError(mission_id)
            return mission

        def grant(self, patient_id: str, bundle, *, enabled=True, mission_id="", ttl_minutes=None):
            assert patient_id == self.patient_id
            grant = GoogleGrant.mission_scoped(
                patient_id=patient_id,
                bundle=bundle,
                mission_id=mission_id,
                ttl_minutes=ttl_minutes or 30,
            )
            grant.enabled = enabled
            self._grants.append(grant)
            return grant

        def grants(self, patient_id: str):
            assert patient_id == self.patient_id
            return [item.model_copy(deep=True) for item in self._grants]

    class _AdkMustNotInterpretConsent:
        ready = True

        async def run(self, **_kwargs):
            raise AssertionError("Exact location consent must deterministically resume the safe ADK Places tool")

    state = PatientState()
    constellation = _Constellation(state.profile.id)
    mission = constellation.coordinator.create_navigation_mission(
        patient_id=state.profile.id,
        condition_or_need="follow-up care",
        provider_query="clinic",
        location_text="Santiago de los Caballeros, Dominican Republic",
    )
    mission = constellation.coordinator.discover(mission, [])
    assert mission.state == MissionState.BLOCKED
    assert mission.tool_outputs["authorization_boundary"]["kind"] == "maps_location_for_mission"

    state.messages.append(
        ChatMessage(
            role="assistant",
            author="HealthIA",
            content="Location permission is required.",
            metadata={"google_mission_id": mission.id, "authorization_kind": "maps_location_for_mission"},
        )
    )
    router = GoogleMissionConversationRouter.__new__(GoogleMissionConversationRouter)
    router.settings = None
    router.constellation = constellation
    router.adk = _AdkMustNotInterpretConsent()

    response = asyncio.run(router.respond(state, "I authorize my location for this mission."))
    persisted = constellation.load_mission(state.profile.id, mission.id)
    candidates = persisted.tool_outputs.get("place_candidates") or []

    assert persisted.state == MissionState.AWAITING_SELECTION
    assert "authorization_boundary" not in persisted.tool_outputs
    assert len(candidates) == 2
    assert response.message.metadata["google_mission_state"] == "awaiting_selection"
    assert response.message.metadata["google_mission_next_action"] == "patient_or_context_selects_candidate"
    assert response.message.metadata["requires_human_authorization"] is False
    assert response.message.metadata["external_action_executed"] is True
    assert response.message.metadata["external_mutation_performed"] is False
    assert response.message.metadata["policy_executed_tool"] == "discover_care_options"
    receipt = response.message.metadata["public_action_receipt"]
    assert receipt["tool_count"] == 1
    assert any("ubicación" in step.lower() for step in receipt["executed_steps"])
    assert any("places" in step.lower() for step in receipt["executed_steps"])
