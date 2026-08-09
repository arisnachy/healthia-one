from __future__ import annotations

from typing import Any

from healthia_one.google_connector_runtime import ConnectorResult, MapsConnector
from healthia_one.google_constellation import GoogleAction


class HealthIAMapsConnector(MapsConnector):
    """Maps/Places connector with explicit text-location navigation support.

    A free-text locality is search context only. It is never promoted to the
    patient's legal residence or stored as demographic truth merely because a
    Places query used it.
    """

    TEXT_FIELD_MASK = (
        "places.id,places.displayName,places.formattedAddress,places.location,"
        "places.googleMapsUri,places.websiteUri,places.nationalPhoneNumber"
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
        if not provider_query:
            raise ValueError("Places text search requires a provider/resource query")
        if not location_text:
            raise ValueError("Places text search requires explicit location text")

        page_size = min(max(int(payload.get("page_size", 8)), 1), 20)
        field_mask = str(payload.get("field_mask") or self.TEXT_FIELD_MASK)
        text_query = f"{provider_query} in {location_text}"
        body: dict[str, Any] = {
            "textQuery": text_query,
            "pageSize": page_size,
        }
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
        return ConnectorResult(
            safe_summary=(
                f"Found {len(places)} place candidate(s) using the patient's explicit search location text."
            ),
            data={
                "places": places,
                "field_mask": field_mask,
                "search_location_text": location_text,
                "search_location_is_residence": False,
                "text_query": text_query,
            },
        )
