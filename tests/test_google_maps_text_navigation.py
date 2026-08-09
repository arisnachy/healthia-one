from healthia_one.google_constellation import GrantBundle, GoogleAction, GoogleGrant, GoogleService
from healthia_one.google_connector_runtime import ConnectorResult, GoogleActionExecutor, MemoryReceiptStore
from healthia_one.google_maps_connector import HealthIAMapsConnector
from healthia_one.google_navigation_coordinator import HealthIAGoogleMissionCoordinator
from healthia_one.google_mission_runtime import MemoryMissionStore, MissionState


class Transport:
    def __init__(self):
        self.calls = []

    def call(self, method, url, *, headers=None, body=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "body": body})
        return {
            "places": [
                {
                    "id": "place_text_1",
                    "displayName": {"text": "Centro de Apoyo"},
                    "formattedAddress": "Santiago de los Caballeros",
                }
            ]
        }


def test_places_text_search_uses_current_page_size_and_explicit_field_mask():
    transport = Transport()
    connector = HealthIAMapsConnector("maps-key", transport=transport)
    result = connector.execute(
        GoogleAction.MAPS_TEXT_SEARCH,
        {
            "provider_query": "autism support center",
            "location_text": "Santiago, Dominican Republic",
            "page_size": 99,
        },
        idempotency_key="a" * 64,
    )
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/places:searchText")
    assert call["body"]["textQuery"] == "autism support center in Santiago, Dominican Republic"
    assert call["body"]["pageSize"] == 20
    assert "maxResultCount" not in call["body"]
    assert call["headers"]["X-Goog-FieldMask"].startswith("places.id,places.displayName")
    assert result.data["search_location_text"] == "Santiago, Dominican Republic"
    assert result.data["search_location_is_residence"] is False


def test_text_location_mission_uses_text_search_and_never_promotes_search_context_to_residence():
    transport = Transport()
    maps = HealthIAMapsConnector("maps-key", transport=transport)
    executor = GoogleActionExecutor(
        connectors={GoogleService.MAPS: maps},
        receipt_store=MemoryReceiptStore(),
    )
    coordinator = HealthIAGoogleMissionCoordinator(executor, store=MemoryMissionStore())
    grants = [GoogleGrant(patient_id="patient_demo", bundle=GrantBundle.MAPS_LOCATION)]
    mission = coordinator.create_navigation_mission(
        patient_id="patient_demo",
        condition_or_need="autism support for son",
        provider_query="autism support center",
        location_text="Santiago, Dominican Republic",
    )
    assert mission.location == {
        "text": "Santiago, Dominican Republic",
        "source": "patient_explicit_search_text",
        "is_residence": False,
    }

    mission = coordinator.discover(mission, grants)
    assert mission.state == MissionState.AWAITING_SELECTION
    assert mission.tool_outputs["location_evidence"]["mode"] == "explicit_text"
    assert mission.tool_outputs["location_evidence"]["is_residence"] is False
    assert mission.tool_outputs["place_candidates"][0]["id"] == "place_text_1"


def test_locale_or_timezone_alone_does_not_create_navigation_location():
    coordinator = HealthIAGoogleMissionCoordinator(
        GoogleActionExecutor(connectors={}, receipt_store=MemoryReceiptStore()),
        store=MemoryMissionStore(),
    )
    mission = coordinator.create_navigation_mission(
        patient_id="patient_demo",
        condition_or_need="support",
        provider_query="support center",
        location_text="",
    )
    # No API receives locale/timezone here; the coordinator cannot infer RD or Santiago.
    assert mission.location == {}
    mission = coordinator.discover(
        mission,
        [GoogleGrant(patient_id="patient_demo", bundle=GrantBundle.MAPS_LOCATION)],
    )
    assert mission.state == MissionState.BLOCKED
    assert mission.public_events[-1].event_type == "maps.location_required"
