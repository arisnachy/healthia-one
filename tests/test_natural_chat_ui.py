from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_patient_chat_hides_internal_agent_coordination() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    lowered = script.lower()
    assert "junta clínica" not in lowered
    assert "junta clinica" not in lowered
    assert "coordinando" not in lowered
    assert "consejo clínico" not in lowered
    assert "consejo clinico" not in lowered
    assert "preparando la junta" not in lowered
    assert "chat-pending" in script  # only stripped if an older layer creates it
    assert '.agent-plan,.council-coordination,.chat-pending' in script


def test_question_ui_renders_only_backend_selected_questions() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    assert "message?.metadata?.clinical_interview" in script
    assert "interview.status !== \"awaiting_answers\"" in script
    assert "block?.questions?.length" in script
    assert "(block.questions || []).map(questionMarkup)" in script
    assert "Gemini · preguntas adaptativas" in script
    assert "Preguntas de seguridad · sin llamada de IA" in script
    assert "selected_specialists" not in script
    assert "renderSidebarCouncil" not in script
    assert "prepareCouncilMessage" not in script


def test_question_answers_return_through_the_same_chat_transport() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    assert 'const ANSWER_PREFIX = "[ENTREVISTA_CLINICA]"' in script
    assert "form.requestSubmit()" in script
    assert 'document.querySelector("#chatInput")' in script
    assert "window.healthiaFetch || fetch" in script
