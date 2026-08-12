from __future__ import annotations

from typing import Any

from healthia_one.google_connector_runtime import ConnectorResult, MapsConnector
from healthia_one.google_constellation import GoogleAction


class HealthIAMapsConnector(MapsConnector):
    """Maps/Places connector for evidence-backed resource navigation.

    Text search accepts either patient-entered locality text or patient-authorized
    coordinates used only as a search bias. Neither form of location evidence is
    promoted to residence/demographic truth.
    """

    TEXT_FIELD_MASK = (
        "places.id,places.displayName,places.formattedAddress,places.location,"
        "places.googleMapsUri,places.websiteUri,places.nationalPhoneNumber,places.primaryType"
    )

    def execute(
        self,
        action: GoogleAction,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> ConnectorResult:
        if action != GoogleAction.MAPS_TEXT_SEARCH:
            return super().execute(action, payload, idempotency_key=idempotency_key)
        if not self.api_key:
            raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured")

        provider_query = str(payload.get("provider_query") or "").strip()
        location_text = str(payload.get("location_text") or "").strip()
        location_bias = payload.get("location_bias") or {}
        if not provider_query:
            raise ValueError("Places text search requires a provider/resource query")
        if not location_text and not isinstance(location_bias, dict):
            raise ValueError("Places text search requires explicit location evidence")

        page_size = min(max(int(payload.get("page_size", 8)), 1), 20)
        field_mask = str(payload.get("field_mask") or self.TEXT_FIELD_MASK)
        text_query = f"{provider_query} in {location_text}" if location_text else provider_query
        body: dict[str, Any] = {
            "textQuery": text_query,
            "pageSize": page_size,
        }

        bias_applied = False
        bias_center: dict[str, float] | None = None
        if not location_text and isinstance(location_bias, dict):
            lat = location_bias.get("lat")
            lng = location_bias.get("lng")
            if lat is not None or lng is not None:
                if lat is None or lng is None:
                    raise ValueError("Places location bias requires both latitude and longitude")
                radius_m = min(max(float(location_bias.get("radius_m", 10000)), 100.0), 50000.0)
                bias_center = {"latitude": float(lat), "longitude": float(lng)}
                body["locationBias"] = {
                    "circle": {
                        "center": bias_center,
                        "radius": radius_m,
                    }
                }
                bias_applied = True

        if not location_text and not bias_applied:
            raise ValueError("Places text search requires explicit location text or authorized coordinates")

        language_code = str(payload.get("language_code") or "").strip()
        if language_code:
            body["languageCode"] = language_code[:16]
        included_type = str(payload.get("included_type") or "").strip()
        if included_type:
            body["includedType"] = included_type[:100]

        result = self.transport.call(
            "POST",
            "https://places.googleapis.com/v1/places:searchText",
            headers={
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": field_mask,
            },
            body=body,
        )
        places = result.get("places") or []
        location_mode = "explicit_text" if location_text else "authorized_coordinates"
        return ConnectorResult(
            safe_summary=(
                f"Found {len(places)} place candidate(s) using patient-authorized search location evidence."
            ),
            data={
                "places": places,
                "field_mask": field_mask,
                "search_location_text": location_text,
                "search_location_mode": location_mode,
                "search_location_is_residence": False,
                "location_bias_applied": bias_applied,
                "location_bias_center": bias_center or {},
                "text_query": text_query,
            },
        )