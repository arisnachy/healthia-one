from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_results_have_safe_processing_and_inline_original_preview() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    for marker in ('id="resultProcessing"', 'id="originalPreviewDialog"', 'id="originalPreviewBody"'):
        assert marker in html
    for marker in ("function healthiaAvatarSvg()", "function setResultProcessing(stage = null)", 'setResultProcessing("uploading")', 'setResultProcessing("reading")', 'data-open-original', 'function openOriginalPreview(documentId)', '"?inline=1"', 'api("/api/consultations/new", {method:"POST"})'):
        assert marker in app
    assert 'message.metadata?.conversation_boundary === "new_consultation"' in app
    for marker in (".healthia-avatar", ".result-processing", ".result-preview", ".original-preview-dialog", "@keyframes result-dot"):
        assert marker in css
    subprocess.run(["node", "--check", str(WEB / "app.js")], check=True)


def test_chat_feedback_is_ephemeral_and_final_question_metadata_is_secondary() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    council = (WEB / "clinical-council.js").read_text(encoding="utf-8")
    css = (WEB / "clinical-council.css").read_text(encoding="utf-8")

    assert 'new CustomEvent("healthia:chat-settled"' in app
    assert 'document.addEventListener("healthia:chat-settled", removePending)' in council
    assert 'class="chat-pending-status" role="status" aria-live="polite"' in council
    assert '$("#messageList .chat-pending")?.remove()' not in council
    assert '$$("#messageList .chat-pending").forEach(node => node.remove())' in council
    assert '<div class="clinical-question-metadata"><span class="clinical-stage">2 + 3</span></div>' in council
    assert '$(".clinical-question-metadata", form)?.append(sourceBadge)' in council
    assert ".chat-pending-status" in css
    assert ".clinical-question-metadata" in css
    subprocess.run(["node", "--check", str(WEB / "clinical-council.js")], check=True)
