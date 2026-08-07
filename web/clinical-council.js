(() => {
  if (window.__HEALTHIA_CLINICAL_QUESTIONS__) return;
  window.__HEALTHIA_CLINICAL_QUESTIONS__ = true;

  const ANSWER_PREFIX = "[ENTREVISTA_CLINICA]";
  let hydrateTimer = null;
  let hydrating = false;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'\"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
  }

  function sourceLabel(message) {
    const source = message?.metadata?.question_source;
    if (source === "gemini_dynamic") return {text: "Gemini · preguntas adaptativas", dynamic: true};
    if (source === "safe_fallback") return {text: "Preguntas de seguridad · sin llamada de IA", dynamic: false};
    return {text: "Preguntas adaptadas a tu consulta", dynamic: false};
  }

  function blockFor(message) {
    const interview = message?.metadata?.clinical_interview;
    const block = interview?.question_block;
    if (!interview || interview.status !== "awaiting_answers" || !block?.questions?.length) return null;
    return {interview, block};
  }

  function optionMarkup(question) {
    const type = question.multiple ? "checkbox" : "radio";
    const name = `q_${question.id}`;
    return (question.options || []).map(option => `
      <label class="clinical-option">
        <input type="${type}" name="${escapeHtml(name)}" value="${escapeHtml(option)}">
        <span>${escapeHtml(option)}</span>
      </label>`).join("");
  }

  function questionMarkup(question, index) {
    return `
      <fieldset class="clinical-question" data-question-id="${escapeHtml(question.id)}" data-question-prompt="${escapeHtml(question.prompt)}">
        <legend><span>${index + 1}</span>${escapeHtml(question.prompt)}</legend>
        <div class="clinical-options">${optionMarkup(question)}</div>
        ${question.allow_detail === false ? "" : `<input class="clinical-detail" type="text" placeholder="${escapeHtml(question.detail_placeholder || "Puedes agregar un detalle")}" autocomplete="off">`}
      </fieldset>`;
  }

  function renderBlock(message, article) {
    const data = blockFor(message);
    if (!data || article.querySelector(".clinical-question-block")) return;
    const {interview, block} = data;
    const label = sourceLabel(message);
    article.querySelectorAll(".agent-plan,.council-coordination,.chat-pending").forEach(node => node.remove());

    const section = document.createElement("section");
    section.className = "clinical-question-block";
    section.dataset.interviewId = interview.id;
    section.dataset.stage = String(interview.stage || block.stage || 1);
    section.dataset.questionSource = message.metadata?.question_source || "contextual";
    section.innerHTML = `
      <div class="clinical-block-head">
        <div>
          <strong>${escapeHtml(block.title || "Preguntas para entenderte mejor")}</strong>
          <p>${escapeHtml(block.instruction || "Responde solo lo que sepas. Puedes ampliar cualquier opción.")}</p>
        </div>
        <span class="clinical-source ${label.dynamic ? "is-dynamic" : ""}">${escapeHtml(label.text)}</span>
      </div>
      <form class="clinical-question-form">
        ${(block.questions || []).map(questionMarkup).join("")}
        <div class="clinical-submit-row"><button type="submit" class="clinical-submit">${escapeHtml(block.submit_label || "Continuar")}</button></div>
      </form>`;
    article.querySelector(".message-content")?.append(section);

    section.querySelector("form")?.addEventListener("submit", event => {
      event.preventDefault();
      const answers = [];
      for (const fieldset of section.querySelectorAll(".clinical-question")) {
        const selected = [...fieldset.querySelectorAll("input[type=radio]:checked,input[type=checkbox]:checked")].map(input => input.value);
        const detail = fieldset.querySelector(".clinical-detail")?.value?.trim() || "";
        if (!selected.length && !detail) {
          fieldset.classList.add("needs-answer");
          fieldset.scrollIntoView({behavior: "smooth", block: "center"});
          return;
        }
        fieldset.classList.remove("needs-answer");
        answers.push({question_id: fieldset.dataset.questionId, question_prompt: fieldset.dataset.questionPrompt, selected, detail});
      }
      const payload = ANSWER_PREFIX + JSON.stringify({interview_id: interview.id, stage: Number(interview.stage || block.stage || 1), answers});
      const input = document.querySelector("#chatInput");
      const form = document.querySelector("#chatForm");
      if (!input || !form) return;
      input.value = payload;
      input.dispatchEvent(new Event("input", {bubbles: true}));
      form.requestSubmit();
      section.querySelector(".clinical-submit").disabled = true;
    });
  }

  function stripInternalAgentUi() {
    document.querySelectorAll("#messageList .agent-plan,.council-coordination,.chat-pending").forEach(node => node.remove());
  }

  async function hydrate() {
    if (hydrating) return;
    hydrating = true;
    try {
      if (window.healthiaAuthReady) await window.healthiaAuthReady;
      const request = window.healthiaFetch || fetch;
      const response = await request("/api/bootstrap");
      if (!response.ok) return;
      const snapshot = await response.json();
      for (const message of snapshot.messages || []) {
        if (!blockFor(message)) continue;
        const article = document.querySelector(`#messageList .message[data-id="${CSS.escape(message.id)}"]`);
        if (article) renderBlock(message, article);
      }
      stripInternalAgentUi();
    } catch (error) {
      console.debug("Clinical question hydration skipped", error);
    } finally {
      hydrating = false;
    }
  }

  function scheduleHydrate() {
    clearTimeout(hydrateTimer);
    hydrateTimer = setTimeout(hydrate, 30);
  }

  document.addEventListener("healthia:ui-updated", scheduleHydrate);
  document.addEventListener("healthia:identity-changed", scheduleHydrate);
  document.addEventListener("healthia:signed-out", () => {
    clearTimeout(hydrateTimer);
    document.querySelectorAll(".clinical-question-block").forEach(node => node.remove());
  });
  new MutationObserver(scheduleHydrate).observe(document.documentElement, {subtree: true, childList: true});
  scheduleHydrate();
})();
