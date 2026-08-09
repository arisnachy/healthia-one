if (!window.__HEALTHIA_CONVERSATIONAL_INTERVIEW__) {
  window.__HEALTHIA_CONVERSATIONAL_INTERVIEW__ = true;

  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
    const i18n = window.HealthIAI18n;
    const text = (en, es) => i18n?.locale === "es" ? es : en;
    const ANSWER_PREFIX = "[ENTREVISTA_CLINICA]";
    let answeredByKey = new Map();
    let refreshTimer = null;

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

    function formKey(form) {
      return `${form?.dataset?.interviewId || ""}:${form?.dataset?.stage || ""}`;
    }

    function parseAnswerPayload(content) {
      const raw = String(content || "");
      const index = raw.indexOf(ANSWER_PREFIX);
      if (index < 0) return null;
      try {
        const payload = JSON.parse(raw.slice(index + ANSWER_PREFIX.length));
        if (!payload?.interview_id || !Array.isArray(payload.answers)) return null;
        return payload;
      } catch {
        return null;
      }
    }

    function indexAnswered(messages) {
      const next = new Map();
      (messages || []).forEach(message => {
        if (message?.role !== "patient") return;
        const payload = parseAnswerPayload(message.content);
        if (!payload) return;
        next.set(`${payload.interview_id}:${Number(payload.stage || 1)}`, payload);
      });
      answeredByKey = next;
    }

    async function refreshAnswered() {
      try {
        const response = await fetch("/api/bootstrap", {headers: {Accept: "application/json", "Accept-Language": i18n?.locale || "en"}});
        if (!response.ok) return;
        const snapshot = await response.json();
        indexAnswered(snapshot.messages);
        hydrate();
      } catch {}
    }

    function scheduleRefresh() {
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(refreshAnswered, 70);
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

    function payloadAnswerText(answer) {
      const selected = Array.isArray(answer?.selected) ? answer.selected.filter(Boolean).join(", ") : "";
      return [selected, String(answer?.detail || "").trim()].filter(Boolean).join(" · ") || text("No detail", "Sin detalle");
    }

    function appendPair(history, prompt, answer) {
      const pair = document.createElement("div");
      pair.className = "clinical-conversation-pair";
      pair.innerHTML = `
        <div class="clinical-mini-turn assistant"><span>HealthIA</span><p>${esc(prompt)}</p></div>
        <div class="clinical-mini-turn patient"><span>${text("You", "Tú")}</span><p>${esc(answer)}</p></div>`;
      history.append(pair);
    }

    function appendHistory(history, fieldset) {
      const prompt = fieldset.dataset.questionPrompt || $("legend", fieldset)?.textContent || "";
      appendPair(history, prompt, answerText(fieldset));
    }

    function ensureConversationShell(form) {
      form.classList.add("clinical-conversation-mode");
      const headerTitle = $("header h4", form);
      const headerCopy = $("header p", form);
      const source = $(".clinical-source", form);
      const progressRow = $(".clinical-progress-row", form);
      const submitRow = $(".clinical-submit-row", form);
      const legacyError = $(".clinical-form-error", form);
      if (source) source.textContent = text("Adaptive to this conversation", "Adaptado a esta conversación");
      if (progressRow) progressRow.hidden = true;
      if (submitRow) submitRow.hidden = true;
      if (legacyError) legacyError.hidden = true;
      return {headerTitle, headerCopy, stage: $(".clinical-stage", form), questionsRoot: $(".clinical-questions", form)};
    }

    function renderCompleted(form, payload) {
      if (!form || form.dataset.conversationCompleted === "true") return;
      const fields = $$(".clinical-question", form);
      if (fields.length !== 5) return;
      form.dataset.conversationalized = "true";
      form.dataset.conversationCompleted = "true";
      const shell = ensureConversationShell(form);
      if (shell.headerTitle) shell.headerTitle.textContent = text("We already covered this part", "Esta parte ya la conversamos");
      if (shell.headerCopy) shell.headerCopy.textContent = text(
        "I kept your answers in the thread so we do not ask the same things again.",
        "Conservé tus respuestas en el hilo para no volver a preguntarte lo mismo."
      );
      if (shell.stage) shell.stage.textContent = text("Done", "Listo");
      fields.forEach(fieldset => { fieldset.hidden = true; });
      $(".clinical-turn-controls", form)?.remove();
      $(".clinical-turn-error", form)?.remove();
      let history = $(".clinical-conversation-history", form);
      if (!history) {
        history = document.createElement("div");
        history.className = "clinical-conversation-history";
        shell.questionsRoot?.before(history);
      }
      history.innerHTML = "";
      (payload?.answers || []).forEach(answer => appendPair(
        history,
        answer.question_prompt || text("Clinical question", "Pregunta clínica"),
        payloadAnswerText(answer)
      ));
    }

    function collectPayload(form, fields) {
      return {
        interview_id: form.dataset.interviewId,
        stage: Number(form.dataset.stage || 1),
        answers: fields.map(fieldset => ({
          question_id: fieldset.dataset.questionId,
          question_prompt: fieldset.dataset.questionPrompt,
          selected: $$("input:checked", fieldset).map(input => input.value),
          detail: $(".clinical-detail", fieldset)?.value.trim() || "",
        })),
      };
    }

    function transform(form) {
      if (!form) return;
      const existing = answeredByKey.get(formKey(form));
      if (existing) {
        renderCompleted(form, existing);
        return;
      }
      if (form.dataset.conversationalized === "true") return;
      const fields = $$(".clinical-question", form);
      if (fields.length !== 5) return;

      form.dataset.conversationalized = "true";
      const shell = ensureConversationShell(form);
      if (shell.headerTitle) shell.headerTitle.textContent = text("I will ask one useful thing at a time", "Te iré preguntando una cosa útil a la vez");
      if (shell.headerCopy) shell.headerCopy.textContent = text(
        "Use a suggestion if it fits, or answer naturally in your own words.",
        "Puedes tocar una sugerencia si encaja o responder con tus propias palabras."
      );

      const history = document.createElement("div");
      history.className = "clinical-conversation-history";
      history.setAttribute("aria-live", "polite");
      shell.questionsRoot?.before(history);

      const controls = document.createElement("div");
      controls.className = "clinical-turn-controls";
      controls.innerHTML = `
        <button type="button" class="clinical-dont-know">${text("I don't know", "No sé")}</button>
        <button type="button" class="clinical-next-question">${text("Continue", "Continuar")}</button>`;
      shell.questionsRoot?.after(controls);

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
        if (shell.stage) shell.stage.textContent = `${current + 1} / ${fields.length}`;
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
        if (shell.stage) shell.stage.textContent = text("Done", "Listo");
        const payload = collectPayload(form, fields);
        answeredByKey.set(formKey(form), payload);
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
      refreshAnswered();
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
      document.addEventListener("healthia:ui-updated", scheduleRefresh);
      document.addEventListener("healthia:chat-settled", scheduleRefresh);
      document.addEventListener("healthia:locale-changed", scheduleRefresh);
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once: true});
    else boot();
  })();
}
