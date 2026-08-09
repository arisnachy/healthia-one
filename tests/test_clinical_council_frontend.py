from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_clinical_council_frontend_is_loaded_explicitly() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    icons = (ROOT / "web/icons.js").read_text(encoding="utf-8")
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    styles = (ROOT / "web/clinical-council.css").read_text(encoding="utf-8")

    assert html.count('/assets/clinical-council.js') == 1
    assert "/assets/clinical-council.js" not in icons
    assert "loadScript(" not in icons
    assert "/assets/clinical-council.css" in script
    assert "[ENTREVISTA_CLINICA]" in script
    assert "clinical-question-block" in script
    assert "Áreas disponibles" in script
    assert "Solo se activan cuando la consulta las necesita" in script
    assert "Contexto usado" in script
    assert "requestSubmit" in script
    assert "data-question-prompt" in script
    assert "question_prompt: fieldset.dataset.questionPrompt" in script
    assert ".left-collapsed .main-nav button" in styles
    assert ".patient-chip { display: none !important; }" in styles


def test_question_blocks_keep_compact_readable_typography_and_progressive_disclosure() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    styles = (ROOT / "web/clinical-council.css").read_text(encoding="utf-8")
    assert ".clinical-question legend" in styles
    assert "font-size: 11px" in styles
    assert ".clinical-option input:checked + span" in styles
    assert ".clinical-detail" in styles
    assert "data-question-index" in script
    assert "index >= 2 ? \"hidden\"" in script
    assert "Continuar con las 3 restantes" in script
    assert "clinical-show-all" in script
    assert ".clinical-progress-row" in styles


def test_chat_feedback_is_immediate_patient_natural_and_never_fakes_ai_fallback() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    assert "Recibí lo que me escribiste." in script
    assert "Revisando qué necesita atención" in script
    assert "Esto tarda un poco más; te diré si no puedo completarlo de forma segura." in script
    assert "addPending();" in script
    assert "setTimeout(addPending, 0)" not in script
    assert 'document.addEventListener("healthia:chat-settled", removePending)' in script
    assert "Preguntas creadas para este caso" in script
    assert "No pude completar las próximas preguntas personalizadas" in script
    assert "Google AI está tardando" not in script
    assert "Gemini + ADK" not in script
    assert "Google AI/ADK" not in script
    assert "HealthIA activará la respuesta segura de respaldo" not in script


def test_chat_exposes_action_receipts_without_private_reasoning() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    styles = (ROOT / "web/clinical-council.css").read_text(encoding="utf-8")
    assert "renderActionReceipt" in script
    assert "Lo que hice" in script
    assert "evidence_ids" in script
    assert ".action-receipt" in styles
    assert "chain of thought" not in script.lower()


def test_first_chat_submit_exits_entry_mode_before_pending_feedback() -> None:
    script = (ROOT / "web/clinical-council.js").read_text(encoding="utf-8")
    submit = script.index('form.addEventListener("submit"')
    exit_entry = script.index('chatScroll?.classList.remove("entry-mode")', submit)
    pending = script.index("addPending();", submit)
    assert submit < exit_entry < pending
