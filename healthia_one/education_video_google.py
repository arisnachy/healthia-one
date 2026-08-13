from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import time
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from healthia_one.education_video_models import NarrationAudio
from healthia_one.google_constellation import GoogleAction, GoogleActionRequest, GoogleGrant, GoogleService, GrantBundle
from healthia_one.google_constellation_singleton import get_google_constellation_service
from healthia_one.google_constellation_store import GoogleActionAuthorization, build_action_intent_key, utc_now


_TRUE = {"1", "true", "yes", "on"}


class GoogleEducationMediaProvider:
    """Run patient education media through HealthIA's existing durable Google guard.

    Patient-specific facts may be narrated through private TTS. Veo is stricter:
    it receives only a prevalidated generic education prompt with no PHI.
    """

    def __init__(self, settings) -> None:
        self.settings = settings
        self.constellation = get_google_constellation_service(settings)

    def media_enabled(self) -> bool:
        explicit = os.getenv("HEALTHIA_EDUCATION_MEDIA_ENABLED", "").strip().lower()
        return explicit in _TRUE or (
            str(getattr(self.settings, "cost_mode", "")) == "cloud_demo"
            and bool(getattr(self.settings, "cost_guard_start_enabled", False))
        )

    async def synthesize(self, *, patient_id: str, mission_id: str, text: str, locale: str) -> NarrationAudio:
        if not self.media_enabled():
            raise RuntimeError("HealthIA education media is cost-gated in this deployment")
        grant = GoogleGrant.mission_scoped(
            patient_id=patient_id,
            bundle=GrantBundle.TEXT_TO_SPEECH,
            mission_id=mission_id,
            ttl_minutes=30,
        )
        self.constellation.runtime.grant_store.save(grant)
        request = GoogleActionRequest(
            patient_id=patient_id,
            mission_id=mission_id,
            action=GoogleAction.TEXT_TO_SPEECH_SYNTHESIZE,
            payload={
                "text": text,
                "language_code": "es-US" if locale == "es" else "en-US",
                "audio_encoding": "MP3",
            },
        )
        receipt, outcome = await asyncio.to_thread(self.constellation.runtime.guarded_executor.execute, request)
        if receipt.status != "completed" or outcome is None:
            raise RuntimeError("Text-to-Speech did not produce an authorized narration")
        encoded = str(outcome.data.get("audio_content_base64") or "")
        if not encoded:
            raise RuntimeError("Text-to-Speech returned no narration bytes")
        return NarrationAudio(data=base64.b64decode(encoded), suffix=".mp3", mime_type="audio/mpeg")

    async def maybe_generate_veo_clip(
        self,
        *,
        patient_id: str,
        mission_id: str,
        generic_prompt: str,
    ) -> tuple[bytes | None, str]:
        if os.getenv("HEALTHIA_EDUCATION_VEO_ENABLED", "").strip().lower() not in _TRUE:
            return None, ""
        prompt = str(generic_prompt or "").strip()
        if not prompt:
            return None, ""

        grant = GoogleGrant.mission_scoped(
            patient_id=patient_id,
            bundle=GrantBundle.VEO_GENERATE,
            mission_id=mission_id,
            ttl_minutes=30,
        )
        self.constellation.runtime.grant_store.save(grant)
        storage_key = hashlib.sha256(patient_id.encode("utf-8")).hexdigest()[:16]
        payload = {
            "prompt": prompt,
            "patient_storage_key": storage_key,
            "model": os.getenv("HEALTHIA_EDUCATION_VEO_MODEL", "veo-3.1-fast-generate-001"),
            "duration_seconds": 8,
            "resolution": "720p",
        }
        unsigned = GoogleActionRequest(
            patient_id=patient_id,
            mission_id=mission_id,
            action=GoogleAction.VEO_GENERATE,
            payload=payload,
        )
        authorization = GoogleActionAuthorization(
            patient_id=patient_id,
            mission_id=mission_id,
            action=GoogleAction.VEO_GENERATE,
            intent_key=build_action_intent_key(unsigned),
            one_time=True,
            expires_at=utc_now() + timedelta(minutes=15),
        )
        self.constellation.runtime.authorization_store.save(authorization)
        request = unsigned.model_copy(update={"explicit_authorization_id": authorization.id})
        receipt, outcome = await asyncio.to_thread(self.constellation.runtime.guarded_executor.execute, request)
        if receipt.status != "completed" or outcome is None:
            return None, ""

        operation_name = str(outcome.data.get("operation_name") or "")
        model = str(outcome.data.get("model") or payload["model"])
        if not operation_name:
            return None, ""
        connector = self.constellation.runtime.raw_executor.connectors.get(GoogleService.VEO)
        if connector is None:
            return None, operation_name

        wait_seconds = min(max(int(os.getenv("HEALTHIA_EDUCATION_VEO_WAIT_SECONDS", "45")), 0), 120)
        deadline = time.monotonic() + wait_seconds
        poll_url = (
            f"https://{connector.region}-aiplatform.googleapis.com/v1/projects/{connector.project_id}"
            f"/locations/{connector.region}/publishers/google/models/{model}:fetchPredictOperation"
        )
        result: dict[str, Any] = {}
        while wait_seconds and time.monotonic() < deadline:
            result = await asyncio.to_thread(
                connector.transport.call,
                "POST",
                poll_url,
                headers=connector._headers(),
                body={"operationName": operation_name},
            )
            if bool(result.get("done")):
                break
            await asyncio.sleep(5)
        if not result.get("done"):
            return None, operation_name

        videos = ((result.get("response") or {}).get("videos") or [])
        if not videos:
            return None, operation_name
        gcs_uri = str(videos[0].get("gcsUri") or "")
        if not gcs_uri.startswith("gs://"):
            return None, operation_name
        parsed = urlparse(gcs_uri)

        def download() -> bytes:
            from google.cloud import storage
            client = storage.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
            return client.bucket(parsed.netloc).blob(parsed.path.lstrip("/")).download_as_bytes()

        return await asyncio.to_thread(download), operation_name
