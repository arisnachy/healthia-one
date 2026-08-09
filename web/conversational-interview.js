if (!window.__HEALTHIA_CONVERSATIONAL_INTERVIEW__) {
  window.__HEALTHIA_CONVERSATIONAL_INTERVIEW__ = true;

  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
    const i18n = window.HealthIAI18n;
    const text = (en, es) => i18n?.locale === "es" ? es : en;

    const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[char]));

    function ensureStylesheet() {
      if (document.querySelector('link[data-conversational-interview-style]')) return;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/assets/conversational-interview.css";
      link.dataset.conversationalInterviewStyle = "true";
      document.head.append(link);
    }

    function ensureFreeText(fieldset) {
      let input = $(".clinical-detail", fieldset);
      if (input) return input;
      input = document.createElement("input");
      input.type = "text";
      input.maxLength = 500;
      input.className = "clinical-detail";
      input.placeholder = text("Or tell me in your own words", "O cuéntamelo con tus palabras");
      fieldset.append(input);
      return input;
    }

    function answerText(fieldset) {
      const selected = $$("input:checked", fieldset).map(input => input.value);
      const detail = $(".clinical-detail", fieldset)?.value.trim() || "";
      return [selected.join(", "), detail].filter(Boolean).join(" · ");
    }

    function appendHistory(history, fieldset) {
      const prompt = fieldset.dataset.questionPrompt || $("legend", fieldset)?.textContent || "";
      const answer = answerText(fieldset);
      const pair = document.createElement("div");
      pair.className = "clinical-conversation-pair";
      pair.innerHTML = `
        <div class="clinical-mini-turn assistant"><span>HealthIA</span><p>${esc(prompt)}</p></div>
        <div class="clinical-mini-turn patient"><span>${text("You", "Tú")}</span><p>${esc(answer)}</p></div>`;
      history.append(pair);
    }

    function transform(form) {
      if (!form || form.dataset.conversationalized === "true") return;
      const fields = $$(".clinical-question", form);
      if (fields.length !== 5) return;

      form.dataset.conversationalized = "true";
      form.classList.add("clinical-conversation-mode");
      const headerTitle = $("header h4", form);
      const headerCopy = $("header p", form);
      const stage = $(".clinical-stage", form);
      const source = $(".clinical-source", form);
      const questionsRoot = $(".clinical-questions", form);
      const progressRow = $(".clinical-progress-row", form);
      const submitRow = $(".clinical-submit-row", form);
      const legacyError = $(".clinical-form-error", form);

      if (headerTitle) headerTitle.textContent = text("I will ask one useful thing at a time", "Te iré preguntando una cosa útil a la vez");
      if (headerCopy) headerCopy.textContent = text(
        "Use a suggestion if it fits, or answer naturally in your own words.",
        "Puedes tocar una sugerencia si encaja o responder con tus propias palabras."
      );
      if (source) source.textContent = text("Adaptive to this conversation", "Adaptado a esta conversación");
      if (progressRow) progressRow.hidden = true;
      if (submitRow) submitRow.hidden = true;
      if (legacyError) legacyError.hidden = true;

      const history = document.createElement("div");
      history.className = "clinical-conversation-history";
      history.setAttribute("aria-live", "polite");
      questionsRoot?.before(history);

      const controls = document.createElement("div");
      controls.className = "clinical-turn-controls";
      controls.innerHTML = `
        <button type="button" class="clinical-dont-know">${text("I don't know", "No sé")}</button>
        <button type="button" class="clinical-next-question">${text("Continue", "Continuar")}</button>`;
      questionsRoot?.after(controls);

      const error = document.createElement("p");
      error.className = "clinical-turn-error";
      error.hidden = true;
      controls.after(error);

      fields.forEach((fieldset, index) => {
        fieldset.hidden = index !== 0;
        const legend = $("legend", fieldset);
        if (legend) legend.textContent = fieldset.dataset.questionPrompt || legend.textContent.replace(/^\d+\.\s*/, "");
        ensureFreeText(fieldset);
      });

      let current = 0;
      let completed = false;

      function updateTurn() {
        fields.forEach((fieldset, index) => { fieldset.hidden = index !== current; });
        if (stage) stage.textContent = `${current + 1} / ${fields.length}`;
        const next = $(".clinical-next-question", controls);
        if (next) next.textContent = current === fields.length - 1
          ? text("Send and continue", "Enviar y continuar")
          : text("Continue", "Continuar");
        const input = $(".clinical-detail", fields[current]);
        requestAnimationFrame(() => input?.focus({preventScroll: true}));
      }

      function advance() {
        if (completed) return;
        const fieldset = fields[current];
        const answer = answerText(fieldset);
        if (!answer) {
          error.textContent = text(
            "Choose a suggestion or tell me in your own words.",
            "Elige una sugerencia o cuéntamelo con tus propias palabras."
          );
          error.hidden = false;
          return;
        }
        error.hidden = true;
        appendHistory(history, fieldset);
        fieldset.hidden = true;

        if (current < fields.length - 1) {
          current += 1;
          updateTurn();
          history.lastElementChild?.scrollIntoView({behavior: "smooth", block: "nearest"});
          return;
        }

        completed = true;
        controls.hidden = true;
        if (stage) stage.textContent = text("Done", "Listo");
        form.requestSubmit();
      }

      $(".clinical-next-question", controls)?.addEventListener("click", advance);
      $(".clinical-dont-know", controls)?.addEventListener("click", () => {
        const fieldset = fields[current];
        const detail = ensureFreeText(fieldset);
        $$("input[type=radio], input[type=checkbox]", fieldset).forEach(input => { input.checked = false; });
        detail.value = text("I don't know", "No sé");
        advance();
      });

      form.addEventListener("keydown", event => {
        if (event.key !== "Enter" || event.shiftKey || !event.target?.classList?.contains("clinical-detail")) return;
        event.preventDefault();
        advance();
      });

      updateTurn();
    }

    function hydrate(root = document) {
      $$(".clinical-question-block", root).forEach(transform);
    }

    function boot() {
      ensureStylesheet();
      hydrate();
      const list = $("#messageList");
      if (!list) return;
      new MutationObserver(mutations => {
        mutations.forEach(mutation => mutation.addedNodes.forEach(node => {
          if (!(node instanceof Element)) return;
          if (node.matches?.(".clinical-question-block")) transform(node);
          hydrate(node);
        }));
      }).observe(list, {childList: true, subtree: true});
      document.addEventListener("healthia:ui-updated", () => hydrate());
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once: true});
    else boot();
  })();
}
