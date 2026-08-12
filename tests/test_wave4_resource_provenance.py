from healthia_one.google_connector_runtime import GoogleActionExecutor, MemoryReceiptStore
from healthia_one.google_constellation import GrantBundle, GoogleGrant, GoogleService
from healthia_one.google_maps_connector import HealthIAMapsConnector
from healthia_one.google_mission_runtime import MemoryMissionStore, MissionState
from healthia_one.google_navigation_coordinator import HealthIAGoogleMissionCoordinator


class OverlappingPlacesTransport:
    def call(self, method, url, *, headers=None, body=None):
        query = str((body or {}).get("textQuery") or "")
        return {
            "places": [
                {
                    "id": "same-real-place",
                    "displayName": {"text": "Synthetic Shared Support Resource"},
                    "formattedAddress": "Santiago de los Caballeros",
                    "googleMapsUri": "https://maps.google.com/?cid=synthetic",
                },
                {
                    "id": f"unique-{abs(hash(query))}",
                    "displayName": {"text": "Synthetic Query-Specific Resource"},
                    "formattedAddress": "Santiago de los Caballeros",
                    "googleMapsUri": "https://maps.google.com/?cid=query",
                },
            ]
        }


def test_deduped_place_keeps_every_semantic_query_and_resource_category() -> None:
    maps = HealthIAMapsConnector("maps-key", transport=OverlappingPlacesTransport())
    coordinator = HealthIAGoogleMissionCoordinator(
        GoogleActionExecutor(
            connectors={GoogleService.MAPS: maps},
            receipt_store=MemoryReceiptStore(),
        ),
        store=MemoryMissionStore(),
    )
    mission = coordinator.create_navigation_mission(
        patient_id="synthetic-patient",
        condition_or_need="autism support resources",
        provider_query="autism support resources",
        location_text="Santiago, Dominican Republic",
        resource_queries=[
            "autism therapy center",
            "autism support organization foundation",
            "disability social services community support",
        ],
    )
    grant = GoogleGrant.mission_scoped(
        patient_id="synthetic-patient",
        bundle=GrantBundle.MAPS_LOCATION,
        mission_id=mission.id,
        ttl_minutes=30,
    )

    mission = coordinator.discover(mission, [grant])

    assert mission.state == MissionState.AWAITING_SELECTION
    shared = next(item for item in mission.tool_outputs["place_candidates"] if item["id"] == "same-real-place")
    assert shared["healthiaResourceQueries"][:3] == [
        "autism therapy center",
        "autism support organization foundation",
        "disability social services community support",
    ]
    assert set(shared["healthiaResourceCategories"]) >= {
        "care",
        "community_support",
        "government_or_financial_support",
    }
    assert sum(1 for item in mission.tool_outputs["place_candidates"] if item["id"] == "same-real-place") == 1
