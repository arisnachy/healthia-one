from healthia_one.google_constellation import GrantBundle, GoogleAction, GoogleGrant, GoogleService
from healthia_one.google_connector_runtime import GoogleActionExecutor, MemoryReceiptStore
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
                    "googleMapsUri": "https://maps.google.com/?cid=1",
                }
            ]
        }


class MultiQueryTransport(Transport):
    def call(self, method, url, *, headers=None, body=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "body": body})
        query = str((body or {}).get("textQuery") or "")
        slug = "government" if "government" in query else "community" if "community" in query else "care"
        return {
            "places": [
                {
                    "id": "shared-place",
                    "displayName": {"text": "Shared Resource"},
                    "formattedAddress": "Santiago",
                    "googleMapsUri": "https://maps.google.com/?cid=shared",
                },
                {
                    "id": f"{slug}-place",
                    "displayName": {"text": f"{slug.title()} Resource"},
                    "formattedAddress": "Santiago",
                    "googleMapsUri": f"https://maps.google.com/?cid={slug}",
                },
            ]
        }


def _coordinator(transport):
    maps = HealthIAMapsConnector("maps-key", transport=transport)
    executor = GoogleActionExecutor(
        connectors={GoogleService.MAPS: maps},
        receipt_store=MemoryReceiptStore(),
    )
    return HealthIAGoogleMissionCoordinator(executor, store=MemoryMissionStore())


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


def test_places_text_search_accepts_authorized_coordinate_bias_without_losing_resource_semantics():
    transport = Transport()
    connector = HealthIAMapsConnector("maps-key", transport=transport)
    result = connector.execute(
        GoogleAction.MAPS_TEXT_SEARCH,
        {
            "provider_query": "autism community support organization",
            "location_bias": {"lat": 19.4517, "lng": -70.6970, "radius_m": 12000},
            "page_size": 8,
        },
        idempotency_key="b" * 64,
    )
    call = transport.calls[0]
    assert call["body"]["textQuery"] == "autism community support organization"
    assert call["body"]["locationBias"]["circle"]["center"] == {
        "latitude": 19.4517,
        "longitude": -70.697,
    }
    assert call["body"]["locationBias"]["circle"]["radius"] == 12000.0
    assert result.data["search_location_mode"] == "authorized_coordinates"
    assert result.data["search_location_is_residence"] is False
    assert result.data["location_bias_applied"] is True


def test_text_location_mission_uses_text_search_and_never_promotes_search_context_to_residence():
    transport = Transport()
    coordinator = _coordinator(transport)
    grants = [GoogleGrant(patient_id="patient_demo", bundle=GrantBundle.MAPS_LOCATION)]
    mission = coordinator.create_navigation_mission(
        patient_id="patient_demo",
        condition_or_need="follow-up care",
        provider_query="cardiology clinic",
        location_text="Santiago, Dominican Republic",
    )
    assert mission.location == {
        "text": "Santiago, Dominican Republic",
        "source": "patient_explicit_search_text",
        "is_residence": False,
    }
    assert mission.tool_outputs["resource_queries"] == ["cardiology clinic"]

    mission = coordinator.discover(mission, grants)
    assert mission.state == MissionState.AWAITING_SELECTION
    assert mission.tool_outputs["location_evidence"]["mode"] == "explicit_text"
    assert mission.tool_outputs["location_evidence"]["is_residence"] is False
    assert mission.tool_outputs["place_candidates"][0]["id"] == "place_text_1"
    assert len(transport.calls) == 1


def test_broad_support_mission_auto_expands_to_care_community_and_government_resource_families():
    coordinator = _coordinator(MultiQueryTransport())
    mission = coordinator.create_navigation_mission(
        patient_id="patient_demo",
        condition_or_need="autism support for child",
        provider_query="autism support resources",
        lat=19.4517,
        lng=-70.6970,
    )
    queries = mission.tool_outputs["resource_queries"]
    assert len(queries) == 4
    assert queries[0] == "autism support resources"
    assert any("care clinic therapy specialist" in item for item in queries)
    assert any("community support group foundation nonprofit" in item for item in queries)
    assert any("government disability benefits social services financial assistance" in item for item in queries)


def test_coordinate_resource_bundle_runs_semantic_queries_and_deduplicates_places():
    transport = MultiQueryTransport()
    coordinator = _coordinator(transport)
    grants = [GoogleGrant(patient_id="patient_demo", bundle=GrantBundle.MAPS_LOCATION)]
    mission = coordinator.create_navigation_mission(
        patient_id="patient_demo",
        condition_or_need="autism support for son",
        provider_query="autism care center",
        lat=19.4517,
        lng=-70.6970,
        resource_queries=[
            "autism care center",
            "autism community support group foundation",
            "government disability benefits social services",
        ],
    )

    mission = coordinator.discover(mission, grants, radius_m=15000)
    assert mission.state == MissionState.AWAITING_SELECTION
    assert len(transport.calls) == 3
    assert all(call["body"]["locationBias"]["circle"]["radius"] == 15000.0 for call in transport.calls)
    assert [call["body"]["textQuery"] for call in transport.calls] == [
        "autism care center",
        "autism community support group foundation",
        "government disability benefits social services",
    ]
    candidates = mission.tool_outputs["place_candidates"]
    assert len(candidates) == 4
    assert sum(1 for item in candidates if item["id"] == "shared-place") == 1
    assert {item["healthiaResourceCategory"] for item in candidates} >= {
        "care",
        "community_support",
        "government_or_financial_support",
    }
    assert mission.tool_outputs["location_evidence"]["is_residence"] is False


def test_locale_or_timezone_alone_does_not_create_navigation_location():
    coordinator = HealthIAGoogleMissionCoordinator(
        GoogleActionExecutor(connectors={}, receipt_store=MemoryReceiptStore()),
        store=MemoryMissionStore(),
    )
    mission = coordinator.create_navigation_mission(
        patient_id="patient_demo",
        condition_or_need="follow-up care",
        provider_query="cardiology clinic",
        location_text="",
    )
    assert mission.location == {}
    mission = coordinator.discover(
        mission,
        [GoogleGrant(patient_id="patient_demo", bundle=GrantBundle.MAPS_LOCATION)],
    )
    assert mission.state == MissionState.BLOCKED
    assert mission.public_events[-1].event_type == "maps.location_required"