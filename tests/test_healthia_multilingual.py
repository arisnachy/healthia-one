import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from healthia_one.education_video import PatientEducationVideoRouter
from healthia_one.education_video_models import EducationScene, EducationVideoPlan, NarrationAudio, is_video_request
from healthia_one.gemini_tts_connector import GeminiTextToSpeechConnector
from healthia_one.google_constellation import GoogleAction
from healthia_one.language import detect_text_language, resolve_response_locale, tts_locale
from healthia_one.models import PatientState, VitalRecord


class FakeTokenProvider:
    def token(self, scopes):
        return "test-token"


class FakeTransport:
    def __init__(self):
        self.calls = []

    def call(self, method, url, *, headers=None, body=None):
        self.calls.append((method, url, headers or {}, body or {}))
        return {"audioContent": base64.b64encode(b"RIFF-fake-audio").decode("ascii")}


def test_patient_text_language_overrides_operating_system_language():
    assert resolve_response_locale("I have chest pain and want help please", requested_locale="es-DO") == "en"
    assert resolve_response_locale("Tengo dolor y quiero que me expliques este resultado", requested_locale="en-US") == "es"
    assert resolve_response_locale("Tenho dor e quero ajuda com este resultado", requested_locale="en-US") == "pt"
    assert resolve_response_locale("この結果の意味を説明してください", requested_locale="en-US") == "ja"


def test_tts_locale_mapping_uses_supported_google_bcp47_codes():
    assert tts_locale("es-DO") == "es-419"
    assert tts_locale("pt-PT") == "pt-BR"
    assert tts_locale("fr-CA") == "fr-FR"
    assert tts_locale("ja-JP") == "ja-JP"
    assert tts_locale("zh-CN") == "cmn-CN"


def test_multilingual_video_intent_detection():
    assert is_video_request("Crie um vídeo curto sobre minha pressão")
    assert is_video_request("Erstelle ein Video über meinen Blutdruck")
    assert is_video_request("高血圧について動画で説明してください")
    assert is_video_request("Сделай видео о гипертонии")


def test_gemini_tts_connector_preserves_guard_payload_and_style_controls():
    transport = FakeTransport()
    connector = GeminiTextToSpeechConnector(token_provider=FakeTokenProvider(), transport=transport)
    result = connector.execute(
        GoogleAction.TEXT_TO_SPEECH_SYNTHESIZE,
        {
            "text": "Hola, esta es una explicación clínica.",
            "language_code": "es-419",
            "audio_encoding": "LINEAR16",
            "sample_rate_hertz": 24000,
            "model_name": "gemini-2.5-pro-tts",
            "voice_name": "Charon",
            "style_prompt": "Voz cálida, serena y profesional.",
        },
        idempotency_key="test",
    )
    assert result.data["model_name"] == "gemini-2.5-pro-tts"
    _, url, _, body = transport.calls[0]
    assert url.endswith("/v1/text:synthesize")
    assert body["input"]["prompt"].startswith("Voz cálida")
    assert body["voice"] == {
        "languageCode": "es-419",
        "modelName": "gemini-2.5-pro-tts",
        "name": "Charon",
    }
    assert body["audioConfig"]["sampleRateHertz"] == 24000


async def portuguese_plan(state, topic, locale, duration_seconds, facts):
    assert locale == "pt"
    return EducationVideoPlan(
        title="Entendendo sua pressão arterial",
        patient_fact_keys=[fact.key for fact in facts[:1]],
        scenes=[
            EducationScene(heading="O que é", body="Explicação geral.", narration="A pressão arterial descreve a força do sangue nas artérias.", visual_kind="veo", veo_prompt="Generic educational animation of arterial blood flow, no people, no text"),
            EducationScene(heading="Por que importa", body="A tendência importa.", narration="A tendência ao longo do tempo ajuda a entender o controle."),
            EducationScene(heading="Próximo passo", body="Continue o acompanhamento.", narration="Siga o plano já indicado pelo seu profissional de saúde."),
        ],
    )


class SilentMedia:
    async def synthesize(self, **kwargs):
        return NarrationAudio(data=b"RIFF" + b"x" * 200, suffix=".wav", mime_type="audio/wav")

    async def maybe_generate_veo_clip(self, **kwargs):
        return None, ""


class FakeRenderer:
    def render(self, **kwargs):
        return b"ftyp" + b"x" * 6000


class FakeStore:
    async def persist(self, *, patient_id, video_id, content):
        return f"/private/{patient_id}/{video_id}.mp4"


@pytest.mark.asyncio
async def test_healthia_explain_video_follows_language_written_by_patient():
    state = PatientState()
    state.profile.locale = "en-US"  # OS/profile language differs on purpose.
    state.profile.confirmed_conditions = ["Hipertensão arterial"]
    state.vitals = [VitalRecord(systolic=148, diastolic=92, pulse=78)]
    router = PatientEducationVideoRouter(
        SimpleNamespace(llm_backend="mock", adk_ready=False, model="gemini-3.5-flash"),
        planner=portuguese_plan,
        media_provider=SilentMedia(),
        renderer=FakeRenderer(),
        media_store=FakeStore(),
    )
    result = await router.respond(state, "Crie um vídeo sobre minha hipertensão e pressão")
    assert result is not None
    assert result.message.metadata["response_locale"] == "pt"
    assert result.message.metadata["education_video"]["locale"] == "pt"
    assert "Ver video" not in result.message.content
    assert "Assistir ao vídeo" in result.message.content


def test_frontend_ui_defaults_to_browser_os_language_for_shipped_ui_packs():
    source = Path("web/i18n.js").read_text(encoding="utf-8")
    assert "navigator.languages" in source
    assert "navigator.language" in source
    assert 'localStorage.getItem("healthia.locale")' in source
    assert 'override === "auto"' in source
    assert "document.documentElement.lang = locale" in source
