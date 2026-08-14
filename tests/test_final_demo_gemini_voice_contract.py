from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_final_demo_uses_only_approved_gemini_male_voice():
    workflow = (ROOT / ".github" / "workflows" / "final-live-english-demo.yml").read_text(encoding="utf-8")
    narration = (ROOT / "docs" / "FINAL_DEMO_NARRATION_EN.txt").read_text(encoding="utf-8")
    narrator = (ROOT / "scripts" / "synthesize_gemini_demo_narration.py").read_text(encoding="utf-8")

    assert "gemini-2.5-pro-tts" in workflow
    assert "NARRATION_VOICE: Charon" in workflow
    assert "Google Cloud Gemini TTS" in workflow
    assert "heygen.ai" not in workflow.lower()
    assert "VOICE_PART_1" not in workflow
    assert "VOICE_PART_2" not in workflow
    assert "180 <= duration < 240" in workflow
    assert "medium-low pitch" in workflow.lower()

    assert "HealthIA Explain" in narration
    assert "Veo 3.1 Fast" in narration
    assert "Gemini 2.5 Pro Text-to-Speech" in narration
    assert "your health never starts over" in narration.lower()

    assert "texttospeech.googleapis.com/v1/text:synthesize" in narrator
    assert 'default="Charon"' in narrator
    assert 'default="gemini-2.5-pro-tts"' in narrator
    assert "warm adult male voice" in narrator


def test_demo_narrator_splits_long_text_below_gemini_unary_limit():
    import importlib.util

    path = ROOT / "scripts" / "synthesize_gemini_demo_narration.py"
    spec = importlib.util.spec_from_file_location("healthia_demo_narrator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    text = "This is a complete sentence. " * 400
    chunks = module.split_text(text, max_bytes=3400)
    assert len(chunks) > 1
    assert all(len(chunk.encode("utf-8")) <= 3400 for chunk in chunks)
