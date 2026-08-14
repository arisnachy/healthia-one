from pathlib import Path


def main() -> None:
    auth_path = Path("web/auth.js")
    auth = auth_path.read_text(encoding="utf-8")
    auth = auth.replace(
        'hero: t("auth.hero"), heroBody: t("auth.login.hero_body")',
        'hero: t("auth.login.preview_sub"), heroBody: t("auth.login.hero_body")',
    )
    auth_path.write_text(auth, encoding="utf-8")

    app_path = Path("web/app.js")
    app = app_path.read_text(encoding="utf-8")
    anchor = '''function timeLabel(value) {\n  const date = new Date(value);\n  return Number.isNaN(date.getTime()) ? tr("app.now") : new Intl.DateTimeFormat(localeTag(), {hour:"2-digit", minute:"2-digit"}).format(date);\n}\n'''
    addition = r'''
function educationVideoRecord(message) {
  const record = message?.metadata?.education_video;
  return record && typeof record === "object" ? record : null;
}

function educationVisibleMessage(message) {
  const record = educationVideoRecord(message);
  if (!record || record.status !== "completed") return message.content;
  return String(message.content || "")
    .replace(/\n*\[▶[^\]]*\]\(\/api\/education\/videos\/[^)]+\)\n*/g, "\n\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function appendEducationControls(message, content) {
  const metadata = message?.metadata || {};
  const offer = metadata.education_video_offer;
  const action = metadata.ui_action;
  if (offer && action?.type === "offer_education_video") {
    const offerCard = document.createElement("div");
    offerCard.className = "education-video-offer";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "education-video-create";
    button.textContent = action.label || action.label_en || "Create video";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try { await sendMessage("yes"); }
      finally { button.disabled = false; }
    });
    offerCard.append(button);
    content.append(offerCard);
  }

  const record = educationVideoRecord(message);
  if (!record || record.status !== "completed" || !record.url) return;
  const card = document.createElement("section");
  card.className = "education-video-card";
  const heading = document.createElement("div");
  heading.className = "education-video-heading";
  const eyebrow = document.createElement("span");
  eyebrow.textContent = "HealthIA Explain";
  const title = document.createElement("strong");
  title.textContent = record.title || record.topic || "HealthIA Explain";
  heading.append(eyebrow, title);

  const video = document.createElement("video");
  video.controls = true;
  video.playsInline = true;
  video.preload = "metadata";
  video.src = record.url;
  video.setAttribute("aria-label", title.textContent);

  const fallback = document.createElement("a");
  fallback.className = "education-video-open";
  fallback.href = record.url;
  fallback.target = "_blank";
  fallback.rel = "noopener";
  fallback.textContent = action?.label || action?.label_en || "Open video";
  fallback.hidden = true;
  video.addEventListener("error", () => { fallback.hidden = false; }, {once:true});

  card.append(heading, video, fallback);
  content.append(card);
}
'''
    if "function appendEducationControls(" not in app:
        if anchor not in app:
            raise RuntimeError("timeLabel anchor changed")
        app = app.replace(anchor, anchor + addition, 1)

    old_assistant = 'content.innerHTML = `<div class="message-head"><strong>${escapeHtml(publicName(message.author))}</strong><span>${timeLabel(message.created_at)}</span></div><div class="message-body">${renderMarkdown(message.content)}</div>`;'
    new_assistant = 'content.innerHTML = `<div class="message-head"><strong>${escapeHtml(publicName(message.author))}</strong><span>${timeLabel(message.created_at)}</span></div><div class="message-body">${renderMarkdown(educationVisibleMessage(message))}</div>`;'
    if old_assistant in app:
        app = app.replace(old_assistant, new_assistant, 1)
    if "appendEducationControls(message, content);" not in app:
        marker = "  if (message.agent_plan?.length) {"
        if marker not in app:
            raise RuntimeError("agent plan anchor changed")
        app = app.replace(marker, "  appendEducationControls(message, content);\n" + marker, 1)
    app_path.write_text(app, encoding="utf-8")

    css_path = Path("web/styles.css")
    css = css_path.read_text(encoding="utf-8")
    marker = "/* HealthIA Explain embedded player */"
    if marker not in css:
        css += """

/* HealthIA Explain embedded player */
.education-video-offer{margin-top:12px;display:flex;align-items:center;gap:10px}
.education-video-create{appearance:none;border:1px solid #35557f;background:#2a4165;color:#fff;border-radius:12px;padding:10px 16px;font:inherit;font-weight:700;cursor:pointer;box-shadow:0 8px 24px rgba(42,65,101,.13)}
.education-video-create:hover{filter:brightness(1.06)}
.education-video-create:disabled{opacity:.55;cursor:wait}
.education-video-card{margin-top:14px;border:1px solid #dce5f0;border-radius:18px;background:#f8fafc;padding:12px;box-shadow:0 10px 28px rgba(27,48,79,.08);overflow:hidden}
.education-video-heading{display:flex;flex-direction:column;gap:3px;padding:2px 4px 10px}
.education-video-heading span{font-size:.72rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#55749d}
.education-video-heading strong{font-size:.96rem;color:#182f50}
.education-video-card video{display:block;width:100%;max-height:430px;aspect-ratio:16/9;border-radius:13px;background:#0b1524;object-fit:contain}
.education-video-open{display:inline-flex;margin:10px 4px 2px;font-weight:700;color:#315f9a;text-decoration:none}
@media(max-width:720px){.education-video-card{margin-left:-4px;margin-right:-4px}.education-video-card video{max-height:60vh}}
"""
    css_path.write_text(css, encoding="utf-8")

    test_path = Path("tests/test_education_video_frontend.py")
    test_path.write_text(
        '''from pathlib import Path\n\n\ndef test_chat_embeds_completed_healthia_explain_video_and_offer_button():\n    source = Path("web/app.js").read_text(encoding="utf-8")\n    assert "function appendEducationControls" in source\n    assert 'action?.type === "offer_education_video"' in source\n    assert 'await sendMessage("yes")' in source\n    assert 'document.createElement("video")' in source\n    assert "video.controls = true" in source\n    assert "video.playsInline = true" in source\n    assert "video.src = record.url" in source\n    assert "educationVisibleMessage(message)" in source\n\n\ndef test_healthia_explain_player_has_responsive_product_styling():\n    css = Path("web/styles.css").read_text(encoding="utf-8")\n    assert "HealthIA Explain embedded player" in css\n    assert ".education-video-card video" in css\n    assert "aspect-ratio:16/9" in css\n\n\ndef test_non_english_login_uses_the_new_continuity_hero_translation():\n    source = Path("web/auth.js").read_text(encoding="utf-8")\n    assert 'hero: t("auth.login.preview_sub")' in source\n''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
