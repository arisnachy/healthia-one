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
CANDIDATE_CAP = 12


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


def write_report(report: dict) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run() -> dict:
    report: dict = {
        "status": "FAIL",
        "proof": "WAVE4_REAL_GOOGLE_PLACES_RESOURCE_NAVIGATION",
        "synthetic_only": True,
        "same_mission_resumed_after_consent": False,
        "preconsent_external_search_calls": None,
        "postconsent_external_search_calls": None,
        "external_mutation_performed": False,
        "candidate_count": 0,
        "google_maps_uri_count": 0,
        "secret_material_exposed": False,
        "truth_boundary": "Google Places candidates are public resource-discovery results, not clinical referrals or program-eligibility determinations.",
    }
    maps: CountingMapsConnector | None = None
    try:
        api_key = str(os.environ.get("GOOGLE_MAPS_API_KEY") or "").lstrip("\ufeff").strip()
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
        planned_queries = list(mission.tool_outputs.get("resource_queries") or [])
        # create_navigation_mission intentionally appends the base provider query
        # when it is not already present. That fourth query is part of the product
        # plan and must remain bounded, not silently ignored by the proof.
        require(planned_queries[: len(RESOURCE_QUERIES)] == RESOURCE_QUERIES, "target resource-query order changed")
        require(1 <= len(planned_queries) <= 4, "resource-query plan exceeded the bounded mission contract")
        report["planned_query_count"] = len(planned_queries)

        # Gate 1: no mission-scoped location consent means no Places request at all.
        blocked = coordinator.discover(mission, [])
        report["preconsent_external_search_calls"] = maps.external_search_calls
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
        report["same_mission_resumed_after_consent"] = resumed.id == blocked.id
        report["postconsent_external_search_calls"] = maps.external_search_calls
        report["mission_state"] = str(resumed.state)
        require(resumed.id == blocked.id, "consent created a different mission instead of resuming the same one")
        require(resumed.state == MissionState.AWAITING_SELECTION, "authorized resource discovery did not reach candidate selection")

        candidates = list(resumed.tool_outputs.get("place_candidates") or [])
        executed_queries = list(resumed.tool_outputs.get("resource_search_queries") or [])
        call_count = maps.external_search_calls
        report["executed_query_count"] = len(executed_queries)
        report["candidate_count"] = len(candidates)
        report["bounded_early_stop"] = call_count < len(planned_queries)

        require(1 <= call_count <= len(planned_queries), "Places search count escaped the bounded query plan")
        require(len(executed_queries) == call_count, "a Places call failed to produce a completed query receipt")
        require(executed_queries == planned_queries[:call_count], "executed resource queries diverged from the planned prefix")
        if call_count < len(planned_queries):
            require(
                len(candidates) >= CANDIDATE_CAP,
                "resource discovery stopped early without reaching the durable candidate cap",
            )

        require(bool(candidates), "real Google Places resource discovery returned no candidates")
        maps_uri_count = sum(bool(str(item.get("googleMapsUri") or "").strip()) for item in candidates)
        report["google_maps_uri_count"] = maps_uri_count
        require(maps_uri_count > 0, "real candidates did not include a Google Maps URI")

        categories = sorted(
            {
                str(item.get("healthiaResourceCategory") or "")
                for item in candidates
                if item.get("healthiaResourceCategory")
            }
        )
        # If all three targeted semantic searches executed, the resulting durable
        # candidates must preserve all three categories. If the cap stopped the
        # plan earlier, only categories from the executed prefix are required.
        expected_categories = []
        for query in executed_queries:
            lower = query.lower()
            if "therapy" in lower or "clinic" in lower or "care" in lower:
                expected_categories.append("care")
            elif "foundation" in lower or "support organization" in lower:
                expected_categories.append("community_support")
            elif "social services" in lower or "government" in lower or "financial" in lower:
                expected_categories.append("government_or_financial_support")
        require(set(expected_categories).issubset(set(categories)), "durable candidates lost their semantic resource categories")

        report.update(
            {
                "status": "PASS",
                "website_uri_count": sum(bool(str(item.get("websiteUri") or "").strip()) for item in candidates),
                "phone_count": sum(bool(str(item.get("nationalPhoneNumber") or "").strip()) for item in candidates),
                "resource_categories": categories,
                "resource_search_queries": executed_queries,
                "candidate_fingerprints": [safe_candidate_fingerprint(item) for item in candidates[:8]],
            }
        )
        write_report(report)
        print(
            "HEALTHIA_WAVE4_LIVE_RESOURCE_PASS "
            f"candidates={report['candidate_count']} maps_uri={report['google_maps_uri_count']} "
            f"search_calls={report['postconsent_external_search_calls']} early_stop={report['bounded_early_stop']}"
        )
        return report
    except Exception as exc:
        if maps is not None:
            report["postconsent_external_search_calls"] = maps.external_search_calls
        report["failure_type"] = type(exc).__name__
        report["failure_reason"] = str(exc)[:300]
        write_report(report)
        raise


if __name__ == "__main__":
    run()
