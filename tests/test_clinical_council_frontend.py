from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_adaptive_question_frontend_is_loaded_without_internal_council_ui() -> None:
    icons = (ROOT / "web/icons.js").read_text(encoding="utf-8")
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    styles = (ROOT / "web/clinical-council.css").read_text(encoding="utf-8")

    assert "/assets/clinical-council.js" in icons
    assert "[ENTREVISTA_CLINICA]" in script
    assert "clinical-question-block" in script
    assert "requestSubmit" in script
    assert "data-question-prompt" in script
    assert "question_prompt: fieldset.dataset.questionPrompt" in script
    assert "selected_specialists" not in script
    assert "renderSidebarCouncil" not in script
    assert "Coordinación clínica" not in script
    assert "junta clínica" not in script.lower()
    assert ".left-collapsed .main-nav button" in styles
    assert ".patient-chip { display: none !important; }" in styles


def test_question_blocks_keep_compact_readable_typography() -> None:
    styles = (ROOT / "web/clinical-council.css").read_text(encoding="utf-8")
    assert ".clinical-question legend" in styles
    assert "font-size: 11px" in styles
    assert ".clinical-option input:checked + span" in styles
    assert ".clinical-detail" in styles


def test_chat_has_no_fake_pending_or_unsolicited_agent_coordination() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    assert "Analizando intención y coordinando la junta clínica" not in script
    assert "HealthIA activará la respuesta segura de respaldo" not in script
    assert "addPending();" not in script
    assert "setTimeout(addPending" not in script
    assert "Gemini · preguntas adaptativas" in script
    assert "Preguntas de seguridad · sin llamada de IA" in script
    # If an older layer ever injects these elements, this layer removes them.
    assert '.agent-plan,.council-coordination,.chat-pending' in script


def test_question_block_answers_reenter_the_normal_chat_transport() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    assert 'document.querySelector("#chatInput")' in script
    assert 'document.querySelector("#chatForm")' in script
    assert "form.requestSubmit()" in script
    assert "input.dispatchEvent(new Event(\"input\", {bubbles: true}))" in script
