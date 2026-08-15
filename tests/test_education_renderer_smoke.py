import io
import wave

from healthia_one.education_video_models import EducationScene, EducationVideoPlan, NarrationAudio
from healthia_one.education_video_renderer import EducationVideoRenderer


def test_healthia_explain_renderer_outputs_mp4():
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(bytes(8000 * 2 * 2))
    plan = EducationVideoPlan(title="HealthIA Explain", scenes=[
        EducationScene(heading="Concepto", body="Explicación clínica visual.", narration="Concepto."),
        EducationScene(heading="Seguimiento", body="Conserva tus mediciones.", narration="Seguimiento."),
        EducationScene(heading="Preguntas", body="Prepara dudas para tu consulta.", narration="Preguntas."),
    ])
    media = EducationVideoRenderer().render(
        title=plan.title,
        topic="hipertensión",
        facts=[],
        plan=plan,
        narration=NarrationAudio(data=audio.getvalue(), suffix=".wav", mime_type="audio/wav"),
        target_duration_seconds=12,
        veo_clip=None,
    )
    assert len(media) > 4096
    assert b"ftyp" in media[:64]
