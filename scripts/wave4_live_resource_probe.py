from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from healthia_one.google_connector_runtime import GoogleActionExecutor, MemoryReceiptStore
from healthia_one.google_constellation import GrantBundle, GoogleAction, GoogleGrant, GoogleService
from healthia_one.google_maps_connector import HealthIAMapsConnector
from healthia_one.google_mission_runtime import MemoryMissionStore, MissionState
from healthia_one.google_navigation_coordinator import HealthIAGoogleMissionCoordinator


OUTPUT = Path("dist/wave4-live-resource-proof/report.json")
PATIENT_ID = "synthetic_wave4_resource_patient"
LOCATION_TEXT = "Santiago de los Caballeros, Dominican Republic"
RESOURCE_QUERIES = [
    "autism therapy center",
    "autism support organization foundation",
    "disability social services community support",
]


class CountingMapsConnector(HealthIAMapsConnector):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key)
        self.external_search_calls = 0

    def execute(self, action, payload, *, idempotency_key):
        if action in {GoogleAction.MAPS_TEXT_SEARCH, GoogleAction.MAPS_SEARCH_NEARBY}:
            self.external_search_calls += 1
        return super().execute(action, payload, idempotency_key=idempotency_key)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def safe_candidate_fingerprint(candidate: dict) -> str:
    material = "|".join(
        (
            str(candidate.get("id") or ""),
            str(candidate.get("formattedAddress") or ""),
            str(candidate.get("googleMapsUri") or ""),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def run() -> dict:
    api_key = str(os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    require(bool(api_key), "GOOGLE_MAPS_API_KEY is unavailable")

    maps = CountingMapsConnector(api_key)
    executor = GoogleActionExecutor(
        connectors={GoogleService.MAPS: maps},
        receipt_store=MemoryReceiptStore(),
    )
    coordinator = HealthIAGoogleMissionCoordinator(executor, store=MemoryMissionStore())
    mission = coordinator.create_navigation_mission(
        patient_id=PATIENT_ID,
        condition_or_need="autism and disability support resources for a synthetic family scenario",
        provider_query="autism support resources",
        location_text=LOCATION_TEXT,
        resource_queries=RESOURCE_QUERIES,
        title="Find verified support resources",
    )

    # Gate 1: no mission-scoped location consent means no Places request at all.
    blocked = coordinator.discover(mission, [])
    require(blocked.state == MissionState.BLOCKED, "mission did not stop at the location-consent boundary")
    boundary = dict(blocked.tool_outputs.get("authorization_boundary") or {})
    require(boundary.get("kind") == "maps_location_for_mission", "location-consent boundary was not durable")
    require(boundary.get("external_action_performed") is False, "boundary falsely claims an external action")
    require(maps.external_search_calls == 0, "Places search ran before mission-scoped consent")

    # Gate 2: an expiring grant for exactly this mission resumes the same durable mission.
    grant = GoogleGrant.mission_scoped(
        patient_id=PATIENT_ID,
        bundle=GrantBundle.MAPS_LOCATION,
        mission_id=blocked.id,
        ttl_minutes=30,
    )
    resumed = coordinator.discover(blocked, [grant], radius_m=15000)
    require(resumed.id == blocked.id, "consent created a different mission instead of resuming the same one")
    require(resumed.state == MissionState.AWAITING_SELECTION, "authorized resource discovery did not reach candidate selection")
    require(maps.external_search_calls == len(RESOURCE_QUERIES), "unexpected number of bounded Places search calls")

    candidates = list(resumed.tool_outputs.get("place_candidates") or [])
    require(bool(candidates), "real Google Places resource discovery returned no candidates")
    maps_uri_count = sum(bool(str(item.get("googleMapsUri") or "").strip()) for item in candidates)
    require(maps_uri_count > 0, "real candidates did not include a Google Maps URI")
    executed_queries = list(resumed.tool_outputs.get("resource_search_queries") or [])
    require(executed_queries == RESOURCE_QUERIES, "the semantic resource queries were not preserved")

    report = {
        "status": "PASS",
        "proof": "WAVE4_REAL_GOOGLE_PLACES_RESOURCE_NAVIGATION",
        "synthetic_only": True,
        "same_mission_resumed_after_consent": True,
        "preconsent_external_search_calls": 0,
        "postconsent_external_search_calls": maps.external_search_calls,
        "external_mutation_performed": False,
        "mission_state": str(resumed.state),
        "candidate_count": len(candidates),
        "google_maps_uri_count": maps_uri_count,
        "website_uri_count": sum(bool(str(item.get("websiteUri") or "").strip()) for item in candidates),
        "phone_count": sum(bool(str(item.get("nationalPhoneNumber") or "").strip()) for item in candidates),
        "resource_categories": sorted({str(item.get("healthiaResourceCategory") or "") for item in candidates if item.get("healthiaResourceCategory")}),
        "resource_search_queries": RESOURCE_QUERIES,
        "candidate_fingerprints": [safe_candidate_fingerprint(item) for item in candidates[:8]],
        "secret_material_exposed": False,
        "truth_boundary": "Google Places candidates are public resource-discovery results, not clinical referrals or program-eligibility determinations.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "HEALTHIA_WAVE4_LIVE_RESOURCE_PASS "
        f"candidates={report['candidate_count']} maps_uri={report['google_maps_uri_count']} "
        f"search_calls={report['postconsent_external_search_calls']}"
    )
    return report


if __name__ == "__main__":
    run()
