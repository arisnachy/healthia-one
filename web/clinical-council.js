if (!window.__HEALTHIA_CLINICAL_COUNCIL__) {
  window.__HEALTHIA_CLINICAL_COUNCIL__ = true;

  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
    const ANSWER_PREFIX = "[ENTREVISTA_CLINICA]";
    const sidebarCouncil = [
      ["EC", "Entrevista clínica", "Motivo, evolución y síntomas"],
      ["SC", "Seguridad clínica", "Alarmas y nivel de atención"],
      ["AL", "Archivo longitudinal", "Notas e historia completa"],
      ["SF", "Seguridad farmacológica", "Medicamentos y alergias"],
      ["ND", "Notas y documentos", "Resultados y procedencia"],
      ["SG", "Seguimiento", "Siguiente paso y cierre"],
    ];

    let snapshot = null;
    let hydrateTimer = null;
    let pendingTimer = null;

    const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[char]));

    function ensureStylesheet() {
      if ($('link[data-clinical-council-style]')) return;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/assets/clinical-council.css";
      link.dataset.clinicalCouncilStyle = "true";
      document.head.append(link);
    }

    async function loadSnapshot() {
      const response = await fetch("/api/bootstrap", {headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error(`bootstrap ${response.status}`);
      snapshot = await response.json();
      consolidateIdentity();
      hydrateMessages();
    }

    function initials(name) {
      const values = String(name || "Paciente").trim().split(/\s+/).filter(Boolean).slice(0, 2);
      return values.map(value => value[0]?.toUpperCase() || "").join("") || "P";
    }

    function prepareIdentityShell() {
      const account = $("#accountPill");
      if (account) {
        account.innerHTML = '<div class="patient-avatar">P</div><div><strong>Paciente</strong><span>Cargando perfil autorizado</span></div>';
      }
      $(".patient-chip")?.remove();
    }

    function renderSidebarCouncil() {
      const section = $(".rail-section");
      if (!section || section.dataset.clinicalCouncil === "true") return;
      section.dataset.clinicalCouncil = "true";
      section.innerHTML = `
        <p>Áreas disponibles</p>
        <small class="council-availability-note">Se activan según la consulta</small>
        ${sidebarCouncil.map(([code, label, detail]) => `
          <div class="agent-mini" title="${esc(label)}">
            <span>${esc(code)}</span><div><strong>${esc(label)}</strong><small>${esc(detail)}</small></div>
          </div>`).join("")}`;
    }

    function consolidateIdentity() {
      const profile = snapshot?.profile;
      const account = $("#accountPill");
      if (!profile || !account) return;
      account.innerHTML = `
        <div class="patient-avatar">${esc(initials(profile.display_name))}</div>
        <div><strong>${esc(profile.display_name)}</strong><span>Paciente · datos autorizados</span></div>`;
      account.setAttribute("aria-label", `Perfil de ${profile.display_name}`);
      $(".patient-chip")?.remove();
      renderSidebarCouncil();
      $$(".main-nav button").forEach(button => {
        const label = $("b", button)?.textContent?.trim();
        if (label) button.title = label;
      });
      const newConsultation = $("#newConsultation");
      if (newConsultation) newConsultation.title = "Nueva consulta";
    }

    function readablePatientAnswer(article) {
      const body = $(".message-body", article);
      if (!body) return;
      const text = body.textContent || "";
      if (!text.includes(ANSWER_PREFIX)) return;
      body.innerHTML = "<p>Respondí el bloque de entrevista clínica.</p>";
    }

    function publicAreaLabel(step) {
      const reason = String(step?.reason || "").trim();
      return reason || "Área clínica coordinada";
    }

    function renderCouncil(article, message) {
      if (!message?.agent_plan?.length) return;
      $(".agent-plan", article)?.remove();
      if ($(".council-summary", article)) return;
      const details = document.createElement("details");
      details.className = "council-summary";
      details.innerHTML = `
        <summary>Coordinación clínica · ${message.agent_plan.length} áreas activadas</summary>
        ${message.agent_plan.map(step => `
          <div class="council-member">
            <strong>${esc(publicAreaLabel(step))}</strong>
            <span>${esc(step.action || "Revisión clínica")}</span>
          </div>`).join("")}`;
      $(".message-content", article)?.append(details);
    }

    function optionMarkup(question, interviewId) {
      const type = question.multiple ? "checkbox" : "radio";
      const name = `clinical_${interviewId}_${question.id}`;
      return (question.options || []).map(option => `
        <label class="clinical-option">
          <input type="${type}" name="${esc(name)}" value="${esc(option)}">
          <span>${esc(option)}</span>
        </label>`).join("");
    }

    function renderQuestionBlock(article, message) {
      const interview = message?.metadata?.clinical_interview;
      const block = interview?.question_block;
      if (!block || interview.status !== "awaiting_answers" || $(".clinical-question-block", article)) return;
      const form = document.createElement("form");
      form.className = "clinical-question-block";
      form.dataset.interviewId = interview.id;
      form.dataset.stage = String(block.stage || interview.stage || 1);
      form.innerHTML = `
        <header>
          <div><h4>${esc(block.title || "Entrevista clínica")}</h4><p>${esc(block.instruction || "Selecciona las respuestas que correspondan.")}</p></div>
          <span class="clinical-stage">5 preguntas</span>
        </header>
        <div class="clinical-questions">
          ${(block.questions || []).map((question, index) => `
            <fieldset class="clinical-question" data-question-id="${esc(question.id)}">
              <legend>${index + 1}. ${esc(question.prompt)}</legend>
              <div class="clinical-options">${optionMarkup(question, interview.id)}</div>
              ${question.allow_detail ? `<input class="clinical-detail" type="text" maxlength="500" placeholder="${esc(question.detail_placeholder || "Agregar detalle (opcional)")}">` : ""}
            </fieldset>`).join("")}
        </div>
        <p class="clinical-form-error" hidden></p>
        <div class="clinical-submit-row"><button class="clinical-submit" type="submit">${esc(block.submit_label || "Continuar")}</button></div>`;

      const source = interview.question_source || message.metadata?.question_source || "safe_fallback";
      const judgeScore = Number(interview.judge_review?.score ?? message.metadata?.judge_review?.score ?? 0);
      const sourceLabel = source === "gemini_dynamic" ? "Gemini · preguntas adaptativas" : "Modo seguro · respaldo";
      form.dataset.questionSource = source;
      const sourceBadge = document.createElement("span");
      sourceBadge.className = `clinical-source ${source === "gemini_dynamic" ? "is-dynamic" : "is-fallback"}`;
      sourceBadge.textContent = sourceLabel;
      if (judgeScore) sourceBadge.title = `Validación de calidad: ${judgeScore}/100`;
      $("header", form)?.append(sourceBadge);

      form.addEventListener("submit", event => {
        event.preventDefault();
        const error = $(".clinical-form-error", form);
        const answers = [];
        let missing = false;
        $$(".clinical-question", form).forEach(fieldset => {
          const selected = $$("input:checked", fieldset).map(input => input.value);
          const detail = $(".clinical-detail", fieldset)?.value.trim() || "";
          if (!selected.length && !detail) missing = true;
          answers.push({question_id: fieldset.dataset.questionId, selected, detail});
        });
        if (missing) {
          error.textContent = "Responde cada pregunta o agrega un detalle antes de continuar.";
          error.hidden = false;
          return;
        }
        error.hidden = true;
        const submit = $(".clinical-submit", form);
        submit.disabled = true;
        submit.textContent = "Enviando a la junta…";
        const payload = {
          interview_id: interview.id,
          stage: Number(form.dataset.stage || 1),
          answers,
        };
        const input = $("#chatInput");
        const chatForm = $("#chatForm");
        if (!input || !chatForm) return;
        input.value = `${ANSWER_PREFIX}${JSON.stringify(payload)}`;
        input.dispatchEvent(new Event("input", {bubbles: true}));
        chatForm.requestSubmit();
      });
      $(".message-content", article)?.append(form);
    }

    function hydrateMessages() {
      if (!snapshot) return;
      const byId = new Map((snapshot.messages || []).map(message => [message.id, message]));
      $$("#messageList .message").forEach(article => {
        readablePatientAnswer(article);
        const message = byId.get(article.dataset.id);
        if (!message) return;
        renderQuestionBlock(article, message);
        renderCouncil(article, message);
      });
    }

    function removePending() {
      $("#messageList .chat-pending")?.remove();
      clearTimeout(pendingTimer);
      pendingTimer = null;
    }

    function addPending() {
      removePending();
      const list = $("#messageList");
      if (!list) return;
      const article = document.createElement("article");
      article.className = "message assistant chat-pending";
      article.innerHTML = `
        <div class="avatar">H1</div>
        <div class="message-content"><div class="message-head"><strong>HealthIA</strong><span>ahora</span></div><div class="message-body"><p>Analizando intención y coordinando la junta clínica<span class="chat-pending-dots"></span></p></div></div>`;
      list.append(article);
      $("#chatScroll")?.scrollTo({top: $("#chatScroll").scrollHeight, behavior: "smooth"});
      pendingTimer = setTimeout(() => {
        const body = $(".message-body", article);
        if (body) body.innerHTML = "<p>Gemini está tardando. HealthIA activará la respuesta segura de respaldo automáticamente.</p>";
      }, 9000);
    }

    function setupChatFeedback() {
      const form = $("#chatForm");
      const input = $("#chatInput");
      if (!form || !input || form.dataset.clinicalFeedbackBound) return;
      form.dataset.clinicalFeedbackBound = "true";
      form.addEventListener("submit", () => {
        if (!input.value.trim()) return;
        const chatScroll = $("#chatScroll");
        chatScroll?.classList.remove("entry-mode");
        chatScroll?.classList.add("conversation-started");
        addPending();
      }, true);

      const list = $("#messageList");
      if (!list) return;
      const observer = new MutationObserver(mutations => {
        const assistantArrived = mutations.some(mutation => [...mutation.addedNodes].some(node =>
          node instanceof Element && node.matches?.(".message.assistant:not(.chat-pending)")));
        if (assistantArrived) removePending();
        clearTimeout(hydrateTimer);
        hydrateTimer = setTimeout(() => loadSnapshot().catch(() => hydrateMessages()), 120);
      });
      observer.observe(list, {childList: true});
    }

    async function boot() {
      ensureStylesheet();
      prepareIdentityShell();
      renderSidebarCouncil();
      setupChatFeedback();
      try {
        await loadSnapshot();
      } catch (error) {
        console.warn("HealthIA clinical council hydration failed", error);
      }
    }

    document.addEventListener("healthia:ui-updated", () => {
      clearTimeout(hydrateTimer);
      hydrateTimer = setTimeout(() => loadSnapshot().catch(() => hydrateMessages()), 80);
    });

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", boot, {once: true});
    } else {
      boot();
    }
  })();
}
