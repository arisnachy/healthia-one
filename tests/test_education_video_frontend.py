from pathlib import Path


def test_chat_embeds_completed_healthia_explain_video_and_offer_button():
    source = Path("web/app.js").read_text(encoding="utf-8")
    assert "function appendEducationControls" in source
    assert 'action?.type === "offer_education_video"' in source
    assert 'await sendMessage("yes")' in source
    assert 'document.createElement("video")' in source
    assert "video.controls = true" in source
    assert "video.playsInline = true" in source
    assert 'video.preload = "metadata"' in source
    assert "video.src = record.url" in source
    assert "educationVisibleMessage(message)" in source
    assert "record.url" in source
    assert 'fallback.rel = "noopener"' in source


def test_healthia_explain_player_has_responsive_product_styling():
    css = Path("web/styles.css").read_text(encoding="utf-8")
    assert "HealthIA Explain embedded player" in css
    assert ".education-video-card video" in css
    assert "aspect-ratio:16/9" in css
    assert "max-height:60vh" in css


def test_non_english_login_uses_the_new_continuity_hero_translation():
    source = Path("web/auth.js").read_text(encoding="utf-8")
    assert 'hero: t("auth.login.preview_sub")' in source
