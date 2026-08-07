from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from healthia_one.config import Settings
from healthia_one.models import AgenticEvent


class CloudEventPublisher:
    """Small Pub/Sub publisher used only when durable cloud dispatch is enabled."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None
        self._topic_path = ""

    @property
    def enabled(self) -> bool:
        return self.settings.event_dispatch_backend == "pubsub"

    def _ensure_client(self) -> tuple[Any, str]:
        if self._client is None:
            project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
            if not project:
                raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Pub/Sub dispatch")
            from google.cloud import pubsub_v1

            self._client = pubsub_v1.PublisherClient()
            self._topic_path = self._client.topic_path(project, self.settings.pubsub_topic)
        return self._client, self._topic_path

    async def publish(self, event: AgenticEvent) -> str:
        if not self.enabled:
            raise RuntimeError("Pub/Sub dispatch is disabled")
        client, topic_path = self._ensure_client()
        payload = event.model_dump_json().encode("utf-8")
        future = client.publish(
            topic_path,
            payload,
            event_type=event.event_type,
            patient_id=event.patient_id,
            source_id=event.source_id or "none",
        )
        return await asyncio.to_thread(future.result, timeout=15)


def decode_pubsub_push(payload: dict[str, Any]) -> AgenticEvent:
    """Decode a Pub/Sub push envelope into the typed HealthIA event contract."""

    import base64

    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        raise ValueError("Pub/Sub push is missing message")
    encoded = message.get("data")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("Pub/Sub push is missing message.data")
    try:
        raw = base64.b64decode(encoded, validate=True).decode("utf-8")
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Pub/Sub message.data is not a valid HealthIA event") from exc
    return AgenticEvent.model_validate(data)
