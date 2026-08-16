from __future__ import annotations

from healthia_one.google_constellation import GrantBundle, GoogleAction, active_grant_bundles
from healthia_one.google_mission_runtime import (
    GoogleHealthMission,
    GoogleHealthMissionCoordinator,
    MissionKind,
    MissionState,
    MissionTransitionError,
)


def _clean_queries(values: list[str] | None, fallback: str) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in [*(values or []), fallback]:
        value = " ".join(str(raw or "").split()).strip()[:180]
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= 4:
            break
    return output or [fallback]


def _broad_support_intent(condition_or_need: str, provider_query: str) -> bool:
    """Expand only explicit umbrella-resource intent, not every ordinary support-center lookup."""
    value = f"{condition_or_need} {provider_query}".lower()
    signals = (
        "resources", "resource options", "assistance", "community", "foundation", "benefit", "social service",
        "government help", "government support", "financial aid", "financial assistance", "nonprofit", "ngo",
        "recursos", "opciones de ayuda", "ayudas", "comunidad", "fundacion", "fundación", "beneficio",
        "servicio social", "ayuda estatal", "ayuda econom", "ayuda económ", "gobierno",
    )
    return any(token in value for token in signals)


def _default_resource_queries(condition_or_need: str, provider_query: str) -> list[str]:
    """Expand a broad support mission; keep a simple clinic/center lookup as one query."""
    if not _broad_support_intent(condition_or_need, provider_query):
        return [provider_query]
    subject = " ".join(str(condition_or_need or provider_query).split()).strip()[:110]
    return _clean_queries(
        [
            provider_query,
            f"{subject} care clinic therapy specialist",
            f"{subject} community support group foundation nonprofit",
            f"{subject} government disability benefits social services financial assistance",
        ],
        provider_query,
    )


def _resource_category(query: str) -> str:
    value = str(query or "").lower()
    if any(token in value for token in ("government", "benefit", "social service", "estatal", "gobierno", "ayuda econom", "financial")):
        return "government_or_financial_support"
    if any(token in value for token in ("support group", "community", "foundation", "fundacion", "fundación", "grupo", "nonprofit", "ngo", "support organization")):
        return "community_support"
    if any(token in value for token in ("clinic", "hospital", "therapy", "therap", "care", "specialist", "centro", "clinica", "clínica")):
        return "care"
    return "support_resource"


class HealthIAGoogleMissionCoordinator(GoogleHealthMissionCoordinator):
    """Navigation coordinator that never invents location or resource evidence.

    A simple coordinate-based provider lookup keeps the established Places Nearby
    path. Broad support missions use semantic Places Text Search with the same
    authorized coordinates as a bounded location bias so category meaning is not
    lost. Explicit patient-entered location text always remains search context,
    never residence/demographic truth.
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
        resource_queries: list[str] | None = None,
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
        mission.tool_outputs["resource_queries"] = (
            _clean_queries(resource_queries, provider_query)
            if resource_queries is not None
            else _default_resource_queries(condition_or_need, provider_query)
        )
        mission.record(
            "mission.created",
            "HealthIA created a patient-scoped resource-navigation mission without inferring residence from locale/language.",
        )
        self.store.save(mission)
        return mission

    def _block_for_location_consent(self, mission: GoogleHealthMission) -> GoogleHealthMission:
        mission.state = MissionState.BLOCKED
        mission.tool_outputs["authorization_boundary"] = {
            "kind": "maps_location_for_mission",
            "mission_id": mission.id,
            "missing_grants": [str(GrantBundle.MAPS_LOCATION)],
            "external_action_performed": False,
            "scope": "this_mission_only",
        }
        mission.record(
            "maps.location_consent_required",
            "Places lookup is paused until the patient explicitly grants location lookup for this mission; no search was performed.",
        )
        self.store.save(mission)
        return mission

    def discover(self, mission, grants, *, radius_m: int = 10000):
        if mission.state not in {MissionState.RECEIVED, MissionState.DISCOVERING, MissionState.BLOCKED}:
            raise MissionTransitionError(f"Cannot discover providers from {mission.state}")
        mission.state = MissionState.DISCOVERING

        has_coordinates = mission.location.get("lat") is not None and mission.location.get("lng") is not None
        has_text = bool(str(mission.location.get("text") or "").strip())
        if not has_coordinates and not has_text:
            mission.state = MissionState.BLOCKED
            mission.tool_outputs["authorization_boundary"] = {
                "kind": "location_evidence_required",
                "mission_id": mission.id,
                "external_action_performed": False,
            }
            mission.record(
                "maps.location_required",
                "Navigation needs patient-authorized coordinates or explicit location text; locale/timezone were not used as location.",
            )
            self.store.save(mission)
            return mission

        active = active_grant_bundles(grants, mission.patient_id, mission.id)
        if GrantBundle.MAPS_LOCATION not in active:
            return self._block_for_location_consent(mission)

        mission.tool_outputs.pop("authorization_boundary", None)
        queries = _clean_queries(
            mission.tool_outputs.get("resource_queries") if isinstance(mission.tool_outputs.get("resource_queries"), list) else None,
            mission.provider_query,
        )
        candidates: list[dict] = []
        candidate_index: dict[str, int] = {}
        executed_queries: list[str] = []
        receipts: list[str] = []
        simple_coordinate_nearby = has_coordinates and len(queries) == 1

        for query in queries:
            if simple_coordinate_nearby:
                action = GoogleAction.MAPS_SEARCH_NEARBY
                payload = {
                    "lat": mission.location["lat"],
                    "lng": mission.location["lng"],
                    "radius_m": min(max(int(radius_m), 100), 50000),
                    "max_results": 8,
                }
            else:
                action = GoogleAction.MAPS_TEXT_SEARCH
                payload = {
                    "provider_query": query,
                    "page_size": 8 if len(queries) == 1 else 4,
                }
                if has_coordinates:
                    payload["location_bias"] = {
                        "lat": mission.location["lat"],
                        "lng": mission.location["lng"],
                        "radius_m": radius_m,
                    }
                else:
                    payload["location_text"] = str(mission.location["text"])

            receipt, outcome = self._execute(mission, grants, action, payload)
            receipts.append(receipt.id)
            if receipt.status != "completed" or outcome is None:
                continue
            executed_queries.append(query)
            category = _resource_category(query)
            for raw in outcome.data.get("places") or []:
                if not isinstance(raw, dict):
                    continue
                place_id = str(raw.get("id") or "").strip()
                dedupe_key = place_id or "|".join(
                    (
                        str((raw.get("displayName") or {}).get("text") or "").strip().lower(),
                        str(raw.get("formattedAddress") or "").strip().lower(),
                    )
                )
                if not dedupe_key:
                    continue

                if dedupe_key in candidate_index:
                    # A real place can satisfy more than one semantic search. Keep
                    # one visible candidate, but preserve every verified query and
                    # resource family that returned it instead of discarding that
                    # provenance during deduplication.
                    existing = candidates[candidate_index[dedupe_key]]
                    resource_queries = list(existing.get("healthiaResourceQueries") or [])
                    resource_categories = list(existing.get("healthiaResourceCategories") or [])
                    if query not in resource_queries:
                        resource_queries.append(query)
                    if category not in resource_categories:
                        resource_categories.append(category)
                    existing["healthiaResourceQueries"] = resource_queries
                    existing["healthiaResourceCategories"] = resource_categories
                    continue

                item = dict(raw)
                item["healthiaResourceQuery"] = query
                item["healthiaResourceCategory"] = category
                item["healthiaResourceQueries"] = [query]
                item["healthiaResourceCategories"] = [category]
                candidate_index[dedupe_key] = len(candidates)
                candidates.append(item)
                if len(candidates) >= 12:
                    break
            if len(candidates) >= 12:
                break

        mission.tool_outputs["place_candidates"] = candidates
        mission.tool_outputs["resource_search_queries"] = executed_queries
        mission.tool_outputs["resource_search_receipt_ids"] = receipts
        mission.tool_outputs["location_evidence"] = {
            "mode": "authorized_coordinates" if has_coordinates else "explicit_text",
            "value": (
                {"lat": mission.location.get("lat"), "lng": mission.location.get("lng")}
                if has_coordinates
                else mission.location.get("text")
            ),
            "is_residence": False,
        }
        mission.state = MissionState.AWAITING_SELECTION if candidates else MissionState.BLOCKED
        mission.record(
            "mission.awaiting_selection" if candidates else "mission.discovery_no_candidates",
            (
                f"{len(candidates)} deduplicated resource candidate(s) are ready from {len(executed_queries)} verified Places search(es)."
                if candidates
                else "Authorized Places searches completed without a verifiable candidate; HealthIA did not invent one."
            ),
        )
        self.store.save(mission)
        return mission