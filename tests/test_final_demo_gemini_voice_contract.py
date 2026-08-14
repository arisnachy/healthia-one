from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "final-devpost-taskmaster-demo.yml"


def test_final_demo_uses_only_approved_gemini_male_voice():
    workflow = WORKFLOW.read_text(encoding="utf-8")
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


def test_final_demo_focuses_on_taskmaster_evidence_to_outcome_path():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    recorder = (ROOT / "scripts" / "record_final_live_english_demo.py").read_text(encoding="utf-8")
    narration = (ROOT / "docs" / "FINAL_DEMO_NARRATION_EN.txt").read_text(encoding="utf-8")

    assert "results_workspace_opened" in workflow
    assert "results_workspace_opened" in recorder
    assert "adaptive_clinical_workflow_started" not in workflow
    assert "one_question_at_a_time_five_question_contract" not in workflow
    assert "Please start a clinical interview" not in recorder
    assert ".main-nav [data-open=\"results\"]" in recorder
    assert "original bytes first" in narration
    assert "durable, evidence-backed outcome" in narration
    assert "Google ADK available for bounded agent execution" in narration


def test_final_demo_requires_private_healthia_explain_outcome():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    recorder = (ROOT / "scripts" / "record_final_live_english_demo.py").read_text(encoding="utf-8")

    for marker in (
        "healthia_explain_private_video_completed",
        "healthia_explain_gemini_tts_narration",
        "healthia_explain_video_playback",
    ):
        assert marker in workflow
        assert marker in recorder
    assert "video.get('private') is not True" in workflow
    assert "video.get('narration_status') != 'gemini_tts'" in workflow


def test_healthia_explain_wait_is_rate_limit_and_transient_error_safe():
    recorder = (ROOT / "scripts" / "record_final_live_english_demo.py").read_text(encoding="utf-8")

    assert 'error_text = str(exc)' in recorder
    assert '"HTTP 429" not in error_text and "HTTP 500" not in error_text' in recorder
    assert "rate_limit_backoff_ms: int = 3000" in recorder
    assert "page.wait_for_timeout(max(rate_limit_backoff_ms, poll_ms))" in recorder
    assert "timeout_s=210.0" in recorder
    assert "poll_ms=2000" in recorder
    assert "rate_limit_backoff_ms=5000" in recorder


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
