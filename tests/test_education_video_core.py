from types import SimpleNamespace

import pytest

from healthia_one.education_video import PatientEducationVideoRouter
from healthia_one.education_video_models import EducationScene, EducationVideoPlan, collect_topic_facts, validate_plan
from healthia_one.models import ChatMessage, ChatResponse, PatientState, VitalRecord


async def fake_plan(state, topic, locale, duration_seconds, facts):
    return EducationVideoPlan(
        title="Entendiendo tu presión arterial",
        patient_fact_keys=[fact.key for fact in facts[:2]],
        scenes=[
            EducationScene(heading="Qué es la presión arterial", body="Es la fuerza que ejerce la sangre sobre las arterias.", narration="La presión arterial describe la fuerza de la sangre al circular por las arterias.", visual_kind="veo", veo_prompt="Generic medical education animation of arterial blood flow, no people, no text overlays"),
            EducationScene(heading="Por qué se vigila", body="La tendencia ayuda a conversar con el equipo de salud.", narration="Una medición aislada no cuenta toda la historia."),
            EducationScene(heading="Qué puedes hacer", body="Guarda tus mediciones y prepara tus preguntas.", narration="Conserva tus mediciones para tu próxima valoración."),
        ],
    )


class FakeMediaProvider:
    def __init__(self): self.veo_prompts = []
    async def synthesize(self, **kwargs): raise RuntimeError("test visual fallback")
    async def maybe_generate_veo_clip(self, *, generic_prompt, **kwargs):
        self.veo_prompts.append(generic_prompt)
        return None, "operation-test"


class FakeRenderer:
    def __init__(self): self.calls = []
    def render(self, **kwargs):
        self.calls.append(kwargs)
        return b"ftyp" + b"x" * 6000


class FakeStore:
    def __init__(self): self.saved = []
    async def persist(self, *, patient_id, video_id, content):
        self.saved.append((patient_id, video_id, content))
        return f"/private/{patient_id}/{video_id}.mp4"


def patient_state():
    state = PatientState()
    state.profile.display_name = "Ana Martínez"
    state.profile.confirmed_conditions = ["Hipertensión arterial"]
    state.vitals = [VitalRecord(systolic=148, diastolic=92, pulse=78)]
    return state


def settings(): return SimpleNamespace(llm_backend="mock", adk_ready=False, model="gemini-3.5-flash")


def test_explanation_offers_video_without_auto_generation():
    state = patient_state()
    router = PatientEducationVideoRouter(settings(), planner=fake_plan, media_provider=FakeMediaProvider(), renderer=FakeRenderer(), media_store=FakeStore())
    draft = ChatResponse(message=ChatMessage(role="assistant", author="HealthIA", content="La hipertensión es presión arterial persistentemente elevada."))
    result = router.maybe_attach_offer(state, "Explícame qué es la hipertensión", draft)
    assert result.message.metadata["education_video_offer"]["requires_confirmation"] is True
    assert result.message.metadata["ui_action"]["type"] == "offer_education_video"
    assert state.missions == []


@pytest.mark.asyncio
async def test_direct_request_creates_private_completed_video_mission():
    state = patient_state()
    media, renderer, store = FakeMediaProvider(), FakeRenderer(), FakeStore()
    router = PatientEducationVideoRouter(settings(), planner=fake_plan, media_provider=media, renderer=renderer, media_store=store)
    result = await router.respond(state, "Hazme un video corto sobre mi hipertensión")
    assert result and result.mission
    assert result.mission.mission_type == "patient_education_video"
    assert str(result.mission.status) == "completed"
    record = result.message.metadata["education_video"]
    assert record["private"] is True
    assert record["url"].startswith("/api/education/videos/video_")
    assert record["narration_status"] == "visual_only_fallback"
    assert store.saved and renderer.calls and media.veo_prompts
    prompt = media.veo_prompts[0].lower()
    assert "ana" not in prompt and "148" not in prompt and "92" not in prompt


def test_exact_patient_value_is_rejected_from_veo_prompt():
    state = patient_state()
    facts = collect_topic_facts(state, "hipertensión")
    plan = EducationVideoPlan(title="Presión", scenes=[
        EducationScene(heading="Visual", body="General", narration="General", visual_kind="veo", veo_prompt="Show blood pressure 148/92 in an artery animation"),
        EducationScene(heading="Dos", body="Contenido seguro", narration="Contenido seguro"),
        EducationScene(heading="Tres", body="Contenido seguro", narration="Contenido seguro"),
    ])
    with pytest.raises(ValueError): validate_plan(plan, facts, state.profile.display_name)
