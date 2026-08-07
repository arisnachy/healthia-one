from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_clinical_council_frontend_is_loaded() -> None:
    icons = (ROOT / "web/icons.js").read_text(encoding="utf-8")
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    styles = (ROOT / "web/clinical-council.css").read_text(encoding="utf-8")

    assert "/assets/clinical-council.js" in icons
    assert "/assets/clinical-council.css" in script
    assert "[ENTREVISTA_CLINICA]" in script
    assert "clinical-question-block" in script
    assert "Áreas disponibles" in script
    assert "Se activan según la consulta" in script
    assert "Coordinación clínica" in script
    assert "requestSubmit" in script
    assert "data-question-prompt" in script
    assert "question_prompt: fieldset.dataset.questionPrompt" in script
    assert ".left-collapsed .main-nav button" in styles
    assert ".patient-chip { display: none !important; }" in styles


def test_question_blocks_keep_compact_readable_typography() -> None:
    styles = (ROOT / "web/clinical-council.css").read_text(encoding="utf-8")
    assert ".clinical-question legend" in styles
    assert "font-size: 11px" in styles
    assert ".clinical-option input:checked + span" in styles
    assert ".clinical-detail" in styles


def test_chat_feedback_is_immediate_and_has_fallback_message() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    assert "Analizando intención y coordinando la junta clínica" in script
    assert "HealthIA activará la respuesta segura de respaldo" in script
    assert "addPending();" in script
    assert "setTimeout(addPending, 0)" not in script
    assert "Gemini · preguntas adaptativas" in script
    assert "Modo seguro · respaldo" in script


def test_first_chat_submit_exits_entry_mode_before_pending_feedback() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    submit = script.index('form.addEventListener("submit"')
    exit_entry = script.index('chatScroll?.classList.remove("entry-mode")', submit)
    pending = script.index("addPending();", submit)
    assert submit < exit_entry < pending
