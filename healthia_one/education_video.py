from __future__ import annotations

import asyncio
import io
import json
import re
import wave
from typing import Any, Awaitable, Callable, Protocol

from healthia_one.control import audit
from healthia_one.education_video_google import GoogleEducationMediaProvider
from healthia_one.education_video_models import (
    EducationFact,
    EducationVideoPlan,
    NarrationAudio,
    collect_topic_facts,
    compose_narration,
    is_acceptance,
    is_english,
    is_explanation_request,
    is_rejection,
    is_video_request,
    latest_offer,
    normalize,
    requested_duration_seconds,
    topic_from_text,
    validate_plan,
)
from healthia_one.education_video_renderer import EducationVideoRenderer, GeneratedEducationMediaStore
from healthia_one.models import ChatMessage, ChatResponse, HealthMission, MissionStatus, PatientState, RiskLevel, new_id
from healthia_one.safety import assess_text


class EducationMediaProvider(Protocol):
    async def synthesize(self, *, patient_id: str, mission_id: str, text: str, locale: str) -> NarrationAudio: ...
    async def maybe_generate_veo_clip(self, *, patient_id: str, mission_id: str, generic_prompt: str) -> tuple[bytes | None, str]: ...


Planner = Callable[[PatientState, str, str, int, list[EducationFact]], Awaitable[EducationVideoPlan]]


def _education_system_instruction(locale: str) -> str:
    language = "Spanish" if locale == "es" else "English"
    return f"""
You are the clinical education director inside HealthIA ONE.
Create a patient-facing educational video plan in {language}. Return JSON only.

Safety and truth rules:
- Do not diagnose a new disease, prescribe, change doses, tell the patient to stop medication, or claim certainty not present in the allowed facts.
- The only patient-specific information you may use is in allowed_patient_facts.
- Keep patient-specific facts separate from general medical education.
- Do not copy patient-specific values into Veo prompts.
- Veo prompts must be generic medical education imagery: no names, ages, locations, dates, medication names, laboratory values, measurements, identifiers, text overlays, or PHI.
- Prefer controlled cards for exact values, medication names, numbers, warning signs, and clinical labels.
- Use at most ONE scene with visual_kind="veo"; all other scenes are controlled cards.
- Do not use a talking doctor avatar or person generation.
- Keep narration within the requested duration.

JSON shape:
{{
  "title": "...",
  "summary": "...",
  "patient_fact_keys": ["only keys from allowed_patient_facts that truly help"],
  "scenes": [
    {{"heading":"...","body":"...","narration":"...","visual_kind":"card|veo","veo_prompt":"generic prompt only for veo"}}
  ]
}}
""".strip()


def _json_object(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Gemini did not return a JSON education video plan")
    return json.loads(text[start : end + 1])


def _silent_narration(seconds: int) -> NarrationAudio:
    """Safe visual-only fallback when private TTS is unavailable."""
    sample_rate = 8000
    frames = b"\x00\x00" * sample_rate * min(max(seconds, 12), 300)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return NarrationAudio(data=buffer.getvalue(), suffix=".wav", mime_type="audio/wav")


class PatientEducationVideoRouter:
    """Chat-first HealthIA Explain mission: explain -> offer -> consent -> private video."""

    def __init__(
        self,
        settings,
        *,
        client_provider: Callable[[], Any] | None = None,
        cost_guard: Any | None = None,
        planner: Planner | None = None,
        media_provider: EducationMediaProvider | None = None,
        renderer: EducationVideoRenderer | None = None,
        media_store: GeneratedEducationMediaStore | None = None,
    ) -> None:
        self.settings = settings
        self.client_provider = client_provider
        self.cost_guard = cost_guard
        self._planner = planner
        self.media_provider = media_provider or GoogleEducationMediaProvider(settings)
        self.renderer = renderer or EducationVideoRenderer()
        self.media_store = media_store or GeneratedEducationMediaStore()

    async def _gemini_plan(
        self,
        state: PatientState,
        topic: str,
        locale: str,
        duration_seconds: int,
        facts: list[EducationFact],
    ) -> EducationVideoPlan:
        if self.client_provider is None or self.cost_guard is None:
            raise RuntimeError("HealthIA Explain Gemini planner is not configured")
        if getattr(self.settings, "llm_backend", "mock") != "gemini_api" or not getattr(self.settings, "adk_ready", False):
            raise RuntimeError("Gemini is not configured for HealthIA Explain")
        self.cost_guard.authorize("patient_education_video_plan")
        payload = {
            "task": "build_evidence_grounded_patient_education_video",
            "topic": topic,
            "requested_duration_seconds": duration_seconds,
            "target_total_narration_words": min(max(int(duration_seconds * 2.0), 90), 650),
            "allowed_patient_facts": [item.model_dump(mode="json") for item in facts],
            "rules": {
                "patient_specific_values_only_from_allowed_facts": True,
                "veo_must_be_generic_and_phi_free": True,
                "max_veo_scenes": 1,
                "exact_values_belong_on_controlled_cards": True,
            },
        }
        interaction = self.client_provider().interactions.create(
            model=self.settings.model,
            input=json.dumps(payload, ensure_ascii=False, default=str),
            system_instruction=_education_system_instruction(locale),
            generation_config={
                "max_output_tokens": min(int(self.cost_guard.max_output_tokens), 1400),
                "thinking_level": "minimal",
                "response_mime_type": "application/json",
            },
            store=False,
        )
        return EducationVideoPlan.model_validate(_json_object(str(getattr(interaction, "output_text", "") or "")))

    async def _plan(self, state: PatientState, topic: str, locale: str, duration_seconds: int, facts: list[EducationFact]) -> EducationVideoPlan:
        planner = self._planner or self._gemini_plan
        plan = await planner(state, topic, locale, duration_seconds, facts)
        return validate_plan(plan, facts, state.profile.display_name)

    def maybe_attach_offer(self, state: PatientState, patient_text: str, response: ChatResponse) -> ChatResponse:
        if is_video_request(patient_text) or not is_explanation_request(patient_text):
            return response
        if response.message.risk_level == RiskLevel.URGENT:
            return response
        interview = (response.message.metadata or {}).get("clinical_interview")
        if isinstance(interview, dict) and interview.get("status") in {"awaiting_answers", "ready_for_synthesis"}:
            return response
        topic = topic_from_text(patient_text)
        if not topic:
            topic = "este tema" if not is_english(patient_text) else "this topic"
        locale = "en" if is_english(patient_text) else "es"
        offer = {"topic": topic, "duration_seconds": 90, "locale": locale, "requires_confirmation": True}
        response.message.metadata["education_video_offer"] = offer
        response.message.metadata["ui_action"] = {
            "type": "offer_education_video", "topic": topic,
            "label_es": "Crear video", "label_en": "Create video",
        }
        sentence = (
            f"If it helps, I can prepare a short private video explaining **{topic}**. Want me to create it?"
            if locale == "en" else
            f"Si te ayuda, puedo prepararte un video corto y privado explicando **{topic}**. ¿Quieres que lo cree?"
        )
        if sentence not in response.message.content:
            response.message.content = f"{response.message.content.rstrip()}\n\n{sentence}"
        return response

    async def respond(self, state: PatientState, patient_text: str) -> ChatResponse | None:
        if assess_text(patient_text).must_stop_normal_flow:
            return None
        offer = latest_offer(state)
        accepted_offer = bool(offer and is_acceptance(patient_text))
        if offer and is_rejection(patient_text):
            return ChatResponse(message=ChatMessage(
                patient_id=state.profile.id, role="assistant", author="HealthIA",
                content="Perfecto, seguimos por aquí." if not is_english(patient_text) else "No problem, we can keep it here.",
                metadata={"education_video_offer_declined": True},
            ))
        if not is_video_request(patient_text) and not accepted_offer:
            return None

        locale = str(offer.get("locale") or "es") if accepted_offer and offer else ("en" if is_english(patient_text) else "es")
        topic = str(offer.get("topic") or "") if accepted_offer and offer else topic_from_text(patient_text)
        duration_seconds = int(offer.get("duration_seconds") or 90) if accepted_offer and offer else requested_duration_seconds(patient_text)
        if not topic or normalize(topic) in {"eso", "esto", "that", "this", "it"}:
            content = (
                "Tell me what condition, result, or health topic you want the video to explain."
                if locale == "en" else
                "Dime qué patología, resultado o tema de salud quieres que explique en el video."
            )
            return ChatResponse(message=ChatMessage(
                patient_id=state.profile.id, role="assistant", author="HealthIA", content=content,
                metadata={"education_video_needs_topic": True},
            ))

        facts = collect_topic_facts(state, topic)
        mission = HealthMission(
            patient_id=state.profile.id,
            title=f"Explicar {topic} en video" if locale == "es" else f"Explain {topic} in a video",
            mission_type="patient_education_video",
            status=MissionStatus.ACTIVE,
            risk_level=RiskLevel.INFO,
            next_action="Crear guion basado en evidencia y renderizar video privado",
            evidence_ids=[item.source_id for item in facts],
        )
        state.missions.append(mission)
        audit(
            state, actor="patient", action="authorize_patient_education_video",
            resource_type="health_mission", resource_id=mission.id,
            details={
                "topic": topic, "duration_seconds": duration_seconds,
                "consent_source": "accepted_offer" if accepted_offer else "direct_patient_request",
                "patient_fact_count": len(facts), "veo_optional": True,
            },
        )

        try:
            plan = await self._plan(state, topic, locale, duration_seconds, facts)
            narration_text = compose_narration(plan, facts, locale)
            narration_status = "google_tts"
            try:
                narration = await self.media_provider.synthesize(
                    patient_id=state.profile.id, mission_id=mission.id, text=narration_text, locale=locale,
                )
            except Exception:
                narration = _silent_narration(duration_seconds)
                narration_status = "visual_only_fallback"

            veo_scene = next((scene for scene in plan.scenes if scene.visual_kind == "veo"), None)
            veo_clip: bytes | None = None
            veo_operation = ""
            if veo_scene is not None:
                try:
                    veo_clip, veo_operation = await self.media_provider.maybe_generate_veo_clip(
                        patient_id=state.profile.id, mission_id=mission.id, generic_prompt=veo_scene.veo_prompt,
                    )
                except Exception:
                    veo_clip, veo_operation = None, ""

            selected_keys = set(plan.patient_fact_keys)
            media_bytes = await asyncio.to_thread(
                self.renderer.render,
                title=plan.title, topic=topic,
                facts=[fact for fact in facts if fact.key in selected_keys],
                plan=plan, narration=narration,
                target_duration_seconds=duration_seconds, veo_clip=veo_clip,
            )
            video_id = new_id("video")
            storage_path = await self.media_store.persist(
                patient_id=state.profile.id, video_id=video_id, content=media_bytes,
            )
            public_path = f"/api/education/videos/{video_id}"
        except Exception as exc:
            mission.next_action = "Reintentar la generación cuando el runtime de medios esté disponible"
            audit(
                state, actor="healthia", action="generate_patient_education_video",
                resource_type="health_mission", resource_id=mission.id, outcome="failed",
                details={"error_type": type(exc).__name__, "no_fake_video": True},
            )
            content = (
                "I couldn't complete the video in this run, so I won't show you a fake or incomplete file. The request remains saved and can be retried."
                if locale == "en" else
                "No pude completar el video en esta ejecución, así que no voy a mostrarte un archivo falso o incompleto. La solicitud quedó guardada y se puede reintentar."
            )
            return ChatResponse(
                message=ChatMessage(
                    patient_id=state.profile.id, role="assistant", author="HealthIA", content=content,
                    mission_id=mission.id,
                    metadata={"education_video": {"status": "generation_failed", "topic": topic, "private": True, "error_type": type(exc).__name__}},
                ), mission=mission,
            )

        mission.status = MissionStatus.COMPLETED
        mission.next_action = "Ver el video y anotar dudas para la próxima conversación o consulta"
        mission.closure_evidence.extend([f"education_video:{video_id}", *[f"source:{item.source_id}" for item in facts]])
        audit(
            state, actor="healthia", action="generate_patient_education_video",
            resource_type="health_mission", resource_id=mission.id,
            details={
                "video_id": video_id, "byte_size": len(media_bytes), "private_storage": True,
                "patient_fact_count": len(facts), "veo_enhanced": bool(veo_clip),
                "veo_operation_recorded": bool(veo_operation), "narration_status": narration_status,
                "treatment_changed": False,
            },
        )
        visible = (
            f"Listo. Preparé **{plan.title}**.\n\n[▶ Ver video]({public_path})\n\nTus datos aparecen separados de la explicación general; el video no cambia tu tratamiento."
            if locale == "es" else
            f"Done. I prepared **{plan.title}**.\n\n[▶ Watch video]({public_path})\n\nYour recorded information is separated from general education; the video does not change your treatment."
        )
        return ChatResponse(
            message=ChatMessage(
                patient_id=state.profile.id, role="assistant", author="HealthIA", content=visible,
                mission_id=mission.id,
                metadata={
                    "education_video": {
                        "status": "completed", "video_id": video_id, "topic": topic, "title": plan.title,
                        "duration_seconds": duration_seconds, "url": public_path, "storage_path": storage_path,
                        "private": True, "patient_fact_source_ids": [item.source_id for item in facts],
                        "veo_enhanced": bool(veo_clip), "veo_operation_name": veo_operation,
                        "narration_status": narration_status,
                    },
                    "ui_action": {"type": "open_education_video", "url": public_path, "label_es": "Ver video", "label_en": "Watch video"},
                    "external_action_executed": True, "external_mutation_performed": True,
                },
            ), mission=mission,
        )
