from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import os
import re
import time
import wave
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from healthia_one.education_video_models import NarrationAudio
from healthia_one.google_constellation import GoogleAction, GoogleActionRequest, GoogleGrant, GoogleService, GrantBundle
from healthia_one.google_constellation_singleton import get_google_constellation_service
from healthia_one.google_constellation_store import GoogleActionAuthorization, build_action_intent_key, utc_now
from healthia_one.language import LANGUAGE_NAMES, normalize_locale, tts_locale


_TRUE = {"1", "true", "yes", "on"}


_TTS_STYLE: dict[str, str] = {
    "es": "Narra en español latinoamericano natural. Voz adulta, cálida, serena y cercana, como un profesional de salud que explica con calma y empatía. Ritmo claro y pausado, sin tono comercial ni dramatismo. Pronuncia cifras y términos médicos con precisión.",
    "en": "Narrate in natural English. Use a warm, calm adult voice, like a healthcare professional explaining something important with empathy. Keep a clear, unhurried pace, with no commercial tone or drama. Pronounce medical terms and numbers precisely.",
    "pt": "Narre em português brasileiro natural. Use uma voz adulta, calma, acolhedora e profissional, explicando com empatia. Mantenha um ritmo claro e sem pressa, sem tom comercial ou dramático. Pronuncie números e termos médicos com precisão.",
    "fr": "Narre en français naturel avec une voix adulte, chaleureuse, calme et professionnelle. Explique comme un professionnel de santé, avec empathie et un rythme clair, sans ton commercial ni dramatique. Prononce les chiffres et termes médicaux avec précision.",
    "de": "Sprich in natürlichem Deutsch mit einer erwachsenen, warmen, ruhigen und professionellen Stimme. Erkläre wie eine medizinische Fachperson mit Empathie und klarem, gemächlichem Tempo. Medizinische Begriffe und Zahlen müssen präzise ausgesprochen werden.",
    "it": "Narra in italiano naturale con una voce adulta, calda, calma e professionale. Spiega con empatia e ritmo chiaro e tranquillo, senza tono commerciale o drammatico. Pronuncia con precisione numeri e termini medici.",
}


def _style_prompt(locale: str) -> str:
    language = normalize_locale(locale)
    if language in _TTS_STYLE:
        return _TTS_STYLE[language]
    return (
        f"Narrate entirely in natural {LANGUAGE_NAMES.get(language, 'the requested language')}. "
        "Use a warm, calm adult voice like a healthcare professional explaining important information with empathy. "
        "Keep the pace clear and unhurried, with no commercial tone or drama. Pronounce medical terms and numbers precisely."
    )


def _split_for_tts(text: str, max_bytes: int = 3600) -> list[str]:
    """Split narration at sentence boundaries below Gemini TTS unary limits."""
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return []
    if len(clean.encode("utf-8")) <= max_bytes:
        return [clean]
    sentences = [item.strip() for item in re.split(r"(?<=[.!?。！？])\s+", clean) if item.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences or [clean]:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate.encode("utf-8")) > max_bytes:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
        while len(current.encode("utf-8")) > max_bytes:
            # Last-resort Unicode-safe split for a pathological sentence.
            cut = max(1, int(len(current) * max_bytes / len(current.encode("utf-8"))) - 8)
            part = current[:cut].rstrip()
            while part and len(part.encode("utf-8")) > max_bytes:
                part = part[:-1]
            if not part:
                break
            chunks.append(part)
            current = current[len(part):].lstrip()
    if current:
        chunks.append(current)
    return chunks


def _merge_linear16_wavs(parts: list[bytes]) -> bytes:
    if not parts:
        raise RuntimeError("Gemini TTS produced no WAV parts")
    frames: list[bytes] = []
    params = None
    for data in parts:
        with wave.open(io.BytesIO(data), "rb") as wav:
            current = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype())
            if params is None:
                params = current
            elif params != current:
                raise RuntimeError("Gemini TTS WAV chunks have incompatible audio parameters")
            frames.append(wav.readframes(wav.getnframes()))
    assert params is not None
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(params[0])
        wav.setsampwidth(params[1])
        wav.setframerate(params[2])
        wav.setcomptype(params[3], "not compressed")
        for frame_block in frames:
            wav.writeframes(frame_block)
    return output.getvalue()


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
        chunks = _split_for_tts(text)
        if not chunks:
            raise RuntimeError("HealthIA Explain narration is empty")

        grant = GoogleGrant.mission_scoped(
            patient_id=patient_id,
            bundle=GrantBundle.TEXT_TO_SPEECH,
            mission_id=mission_id,
            ttl_minutes=30,
        )
        self.constellation.runtime.grant_store.save(grant)

        language = normalize_locale(locale)
        model_name = os.getenv("HEALTHIA_EDUCATION_TTS_MODEL", "gemini-2.5-pro-tts").strip()
        voice_name = os.getenv("HEALTHIA_EDUCATION_TTS_VOICE", "Charon").strip()
        wav_parts: list[bytes] = []
        for index, chunk in enumerate(chunks):
            request = GoogleActionRequest(
                patient_id=patient_id,
                mission_id=mission_id,
                action=GoogleAction.TEXT_TO_SPEECH_SYNTHESIZE,
                payload={
                    "text": chunk,
                    "language_code": tts_locale(language),
                    "audio_encoding": "LINEAR16",
                    "sample_rate_hertz": 24000,
                    "model_name": model_name,
                    "voice_name": voice_name,
                    "style_prompt": _style_prompt(language),
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                },
            )
            receipt, outcome = await asyncio.to_thread(self.constellation.runtime.guarded_executor.execute, request)
            if receipt.status != "completed" or outcome is None:
                raise RuntimeError("Gemini Text-to-Speech did not produce an authorized narration")
            encoded = str(outcome.data.get("audio_content_base64") or "")
            if not encoded:
                raise RuntimeError("Gemini Text-to-Speech returned no narration bytes")
            wav_parts.append(base64.b64decode(encoded))

        return NarrationAudio(data=_merge_linear16_wavs(wav_parts), suffix=".wav", mime_type="audio/wav")

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
