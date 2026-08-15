from __future__ import annotations

import os

from healthia_one.google_connector_runtime import GoogleActionExecutor, MemoryReceiptStore
from healthia_one.google_constellation import GrantBundle, GoogleGrant, GoogleService
from healthia_one.google_maps_connector import HealthIAMapsConnector
from healthia_one.google_mission_runtime import MemoryMissionStore, MissionState
from healthia_one.google_navigation_coordinator import HealthIAGoogleMissionCoordinator

import record_v7_functional_demo as v7


LOCALITY = "Santiago de los Caballeros, Dominican Republic"
_ENGINES: dict[str, HealthIAGoogleMissionCoordinator] = {}


def _is_local(item: dict) -> bool:
    address = str(item.get("formattedAddress") or "").lower()
    return "dominican republic" in address and "santiago" in address


def _is_medical(item: dict) -> bool:
    primary = str(item.get("primaryType") or "").lower().replace("-", "_")
    display = item.get("displayName") or {}
    name = str(display.get("text") if isinstance(display, dict) else display).lower()
    if any(token in primary for token in ("medical", "hospital", "clinic", "lab", "doctor")):
        return True
    return any(
        token in name
        for token in (
            "laboratorio",
            "laboratory",
            "clínica",
            "clinica",
            "clinic",
            "hospital",
            "centro médico",
            "centro medico",
            "diagnóstico",
            "diagnostico",
        )
    )


def _mission_dict(mission) -> dict:
    return {
        **mission.model_dump(mode="json"),
        "private_reasoning": None,
        "truth_boundary": (
            "This demo invokes HealthIA's shipped navigation coordinator and real Google Places connector. "
            "Location consent is mission-scoped; returned places are resource candidates, not clinical referrals."
        ),
    }


def create_navigation_mission_engine(
    page,
    *,
    condition_or_need: str,
    provider_query: str,
    title: str,
    radius_m: int,
):
    api_key = str(os.environ.get("GOOGLE_MAPS_API_KEY") or "").lstrip("\ufeff").strip()
    v7.base.require(bool(api_key), "GOOGLE_MAPS_API_KEY is unavailable")
    if "creatinine" in condition_or_need.lower() or "laboratory" in provider_query.lower():
        provider_query = "laboratorio clínico análisis de sangre creatinina"

    maps = HealthIAMapsConnector(api_key)
    coordinator = HealthIAGoogleMissionCoordinator(
        GoogleActionExecutor(
            connectors={GoogleService.MAPS: maps},
            receipt_store=MemoryReceiptStore(),
        ),
        store=MemoryMissionStore(),
    )
    mission = coordinator.create_navigation_mission(
        patient_id="synthetic-v8-video-patient",
        condition_or_need=condition_or_need,
        provider_query=provider_query,
        location_text=LOCALITY,
        title=title,
    )

    # Prove the consent boundary before any location search.
    blocked = coordinator.discover(mission, [], radius_m=radius_m)
    v7.base.require(blocked.state == MissionState.BLOCKED, "mission did not stop before location consent")
    v7.base.require(
        (blocked.tool_outputs.get("authorization_boundary") or {}).get("external_action_performed") is False,
        "consent boundary falsely claimed external execution",
    )
    grant = GoogleGrant.mission_scoped(
        patient_id=blocked.patient_id,
        bundle=GrantBundle.MAPS_LOCATION,
        mission_id=blocked.id,
        ttl_minutes=30,
    )
    discovered = coordinator.discover(blocked, [grant], radius_m=radius_m)
    candidates = list(discovered.tool_outputs.get("place_candidates") or [])
    local = [item for item in candidates if _is_local(item)]
    if "creatinine" in condition_or_need.lower() or "laboratory" in provider_query.lower():
        medical = [item for item in local if _is_medical(item)]
        if medical:
            local = medical
    v7.base.require(bool(local), "no locality-validated Santiago candidates remained after real Google Places search")
    discovered.tool_outputs["place_candidates"] = local[:8]
    coordinator.store.save(discovered)
    _ENGINES[discovered.id] = coordinator
    return _mission_dict(discovered)


def select_second_candidate_engine(page, mission: dict) -> dict:
    mission_id = str(mission.get("id") or "")
    coordinator = _ENGINES.get(mission_id)
    v7.base.require(coordinator is not None, "navigation engine for mission was not retained")
    loaded = coordinator.store.load("synthetic-v8-video-patient", mission_id)
    v7.base.require(loaded is not None, "mission was not available in the active HealthIA navigation engine")
    candidates = list(loaded.tool_outputs.get("place_candidates") or [])
    v7.base.require(len(candidates) >= 2, "not enough local candidates for exact second selection")
    selected = coordinator.select_provider(loaded, place=candidates[1], provider_email="")
    v7.base.require(
        str((selected.selected_place or {}).get("id") or "") == str(candidates[1].get("id") or ""),
        "the exact second Google candidate was not selected",
    )
    return _mission_dict(selected)


# Keep V7's stricter scientific relevance and branch-comparison UI, but replace
# only navigation with the locality-aware shipped HealthIA mission engine.
v7.base.create_navigation_mission = create_navigation_mission_engine
v7.base.select_second_candidate = select_second_candidate_engine


if __name__ == "__main__":
    v7.base.run()
