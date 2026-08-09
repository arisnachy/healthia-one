from __future__ import annotations

from healthia_one.google_constellation import GoogleAction
from healthia_one.google_mission_runtime import (
    GoogleHealthMission,
    GoogleHealthMissionCoordinator,
    MissionKind,
    MissionState,
    MissionTransitionError,
)


class HealthIAGoogleMissionCoordinator(GoogleHealthMissionCoordinator):
    """Navigation coordinator that never invents location evidence.

    Authorized coordinates use Places Nearby. Explicit patient-provided location
    text uses Places Text Search. Locale, language and timezone are never
    converted into a location or residence assertion.
    """

    def create_navigation_mission(
        self,
        *,
        patient_id: str,
        condition_or_need: str,
        provider_query: str,
        lat: float | None = None,
        lng: float | None = None,
        location_text: str = "",
        title: str = "Find support and arrange care",
        kind: MissionKind = MissionKind.CARE_NAVIGATION,
    ) -> GoogleHealthMission:
        location: dict = {}
        if lat is not None or lng is not None:
            if lat is None or lng is None:
                raise ValueError("Both latitude and longitude are required together")
            location = {
                "lat": float(lat),
                "lng": float(lng),
                "source": "patient_authorized_coordinates",
                "is_residence": False,
            }
        else:
            explicit_text = str(location_text or "").strip()
            if explicit_text:
                location = {
                    "text": explicit_text[:240],
                    "source": "patient_explicit_search_text",
                    "is_residence": False,
                }

        mission = GoogleHealthMission(
            patient_id=patient_id,
            kind=kind,
            title=title,
            condition_or_need=condition_or_need,
            provider_query=provider_query,
            location=location,
        )
        mission.record(
            "mission.created",
            "HealthIA created a patient-scoped navigation mission without inferring residence from locale/language.",
        )
        self.store.save(mission)
        return mission

    def discover(self, mission, grants, *, radius_m: int = 10000):
        if mission.state not in {MissionState.RECEIVED, MissionState.DISCOVERING, MissionState.BLOCKED}:
            raise MissionTransitionError(f"Cannot discover providers from {mission.state}")
        mission.state = MissionState.DISCOVERING

        if mission.location.get("lat") is not None and mission.location.get("lng") is not None:
            action = GoogleAction.MAPS_SEARCH_NEARBY
            payload = {
                "lat": mission.location["lat"],
                "lng": mission.location["lng"],
                "radius_m": radius_m,
                "max_results": 8,
            }
            location_mode = "authorized_coordinates"
        elif str(mission.location.get("text") or "").strip():
            action = GoogleAction.MAPS_TEXT_SEARCH
            payload = {
                "provider_query": mission.provider_query,
                "location_text": str(mission.location["text"]),
                "page_size": 8,
            }
            location_mode = "explicit_text"
        else:
            mission.state = MissionState.BLOCKED
            mission.record(
                "maps.location_required",
                "Navigation needs patient-authorized coordinates or explicit location text; locale/timezone were not used as location.",
            )
            self.store.save(mission)
            return mission

        receipt, outcome = self._execute(mission, grants, action, payload)
        if receipt.status != "completed" or outcome is None:
            mission.state = MissionState.BLOCKED
            self.store.save(mission)
            return mission

        mission.tool_outputs["place_candidates"] = outcome.data.get("places") or []
        mission.tool_outputs["location_evidence"] = {
            "mode": location_mode,
            "value": mission.location.get("text") or {
                "lat": mission.location.get("lat"),
                "lng": mission.location.get("lng"),
            },
            "is_residence": False,
        }
        mission.state = MissionState.AWAITING_SELECTION
        mission.record(
            "mission.awaiting_selection",
            "Place candidates are ready from explicit location evidence; proximity/search match is not a clinical referral.",
        )
        self.store.save(mission)
        return mission
