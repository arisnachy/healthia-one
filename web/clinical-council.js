if (!window.__HEALTHIA_CLINICAL_COUNCIL__) {
  window.__HEALTHIA_CLINICAL_COUNCIL__ = true;

  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
    const i18n = window.HealthIAI18n;
    const text = (en, es) => i18n?.locale === "es" ? es : en;
    const ANSWER_PREFIX = "[ENTREVISTA_CLINICA]";
    const sidebarCouncil = () => [
      ["CI", text("Clinical interview", "Entrevista clínica"), text("Complaint, evolution and symptoms", "Motivo, evolución y síntomas")],
      ["CS", text("Clinical safety", "Seguridad clínica"), text("Warning signs and care level", "Alarmas y nivel de atención")],
      ["LH", text("Longitudinal history", "Historia longitudinal"), text("Notes and full history", "Notas e historia completa")],
      ["MS", text("Medication safety", "Seguridad farmacológica"), text("Medications and allergies", "Medicamentos y alergias")],
      ["ER", text("Evidence & results", "Evidencia y resultados"), text("Results and provenance", "Resultados y procedencia")],
      ["FU", text("Follow-up", "Seguimiento"), text("Next step and closure", "Siguiente paso y cierre")],
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
      const response = await fetch("/api/bootstrap", {headers: {Accept: "application/json", "Accept-Language": i18n?.locale || "en"}});
      if (!response.ok) throw new Error(`bootstrap ${response.status}`);
      snapshot = await response.json();
      consolidateIdentity();
      hydrateMessages();
    }

    function initials(name) {
      const values = String(name || text("Patient", "Paciente")).trim().split(/\s+/).filter(Boolean).slice(0, 2);
      return values.map(value => value[0]?.toUpperCase() || "").join("") || "P";
    }

    function prepareIdentityShell() {
      const account = $("#accountPill");
      if (account) {
        account.innerHTML = `<div class="patient-avatar">P</div><div><strong>${text("Patient", "Paciente")}</strong><span>${text("Loading account", "Cargando cuenta")}</span></div>`;
      }
      $(".patient-chip")?.remove();
    }

    function renderSidebarCouncil() {
      const section = $(".rail-section");
      if (!section) return;
      section.dataset.clinicalCouncil = "true";
      section.innerHTML = `
        <p>${text("Available health areas", "Áreas disponibles")}</p>
        <small class="council-availability-note">${text("Activated only when the current request needs them", "Solo se activan cuando la consulta las necesita")}</small>
        ${sidebarCouncil().map(([code, label, detail]) => `
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
        <div><strong>${esc(profile.display_name)}</strong><span>${text("Account & settings", "Cuenta y configuración")}</span></div>`;
      account.setAttribute("aria-label", `${text("Account & settings for", "Cuenta y configuración de")} ${profile.display_name}`);
      $(".patient-chip")?.remove();
      renderSidebarCouncil();
      $$(".main-nav button").forEach(button => {
        const label = $("b", button)?.textContent?.trim();
        if (label) button.title = label;
      });
      const newConsultation = $("#newConsultation");
      if (newConsultation) newConsultation.title = text("New consultation", "Nueva consulta");
    }

    function readablePatientAnswer(article) {
      const body = $(".message-body", article);
      if (!body) return;
      const raw = body.textContent || "";
      if (!raw.includes(ANSWER_PREFIX)) return;
      body.innerHTML = `<p>${text("I answered the questions in this part of the consultation.", "Respondí las preguntas de esta parte de la consulta.")}</p>`;
    }

    function publicAreaLabel(step) {
      if (i18n?.locale !== "es") return text("Verified clinical context", "Contexto clínico verificado");
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
        <summary>${text("Context used", "Contexto usado")} · ${message.agent_plan.length} ${text("required areas", "áreas necesarias")}</summary>
        ${message.agent_plan.map(step => `
          <div class="council-member">
            <strong>${esc(publicAreaLabel(step))}</strong>
            <span>${esc(i18n?.locale === "es" ? (step.action || "Revisión clínica") : "Verified on-demand clinical check")}</span>
          </div>`).join("")}`;
      $(".message-content", article)?.append(details);
    }

    function actionCopy(target, mission) {
      const evidenceCount = Number(mission?.evidence_ids?.length || 0);
      const completed = mission?.status === "completed";
      const map = {
        results: text("I located the requested result, kept its original evidence linked, and connected it to your health record.", "Localicé el resultado solicitado, mantuve vinculada su evidencia original y lo conecté con tu expediente."),
        measurements: text("I connected this answer with your recorded measurements so the conversation keeps the same clinical thread.", "Conecté esta respuesta con tus mediciones registradas para mantener el mismo hilo clínico."),
        treatment: text("I checked the treatment already recorded in your account without changing the prescribed plan.", "Revisé el tratamiento ya registrado en tu cuenta sin modificar el esquema indicado."),
        appointments: text("I connected the conversation with your visit information and the next step already on record.", "Conecté la conversación con la información de tu cita y el siguiente paso registrado."),
        timeline: text("I linked this turn with your longitudinal health timeline instead of treating it as an isolated message.", "Vinculé este turno con tu línea longitudinal de salud en vez de tratarlo como un mensaje aislado."),
        family: text("I used the family history you authorized and kept the relationship to your record explicit.", "Usé los antecedentes familiares que autorizaste y mantuve explícita su relación con tu expediente."),
        documents: text("I kept the document tied to its source and your health record so it can be retrieved again.", "Mantuve el documento ligado a su fuente y a tu expediente para poder recuperarlo nuevamente."),
        clinical_interview: text("I kept what you already told me and used it to decide what still needs clarification.", "Conservé lo que ya me dijiste y lo usé para decidir qué falta aclarar."),
      };
      return {
        body: map[target] || text("I kept this action connected to your authorized health context.", "Mantuve esta acción conectada con tu contexto de salud autorizado."),
        footer: completed
          ? text(`Completed with ${evidenceCount} linked evidence item${evidenceCount === 1 ? "" : "s"}.`, `Completada con ${evidenceCount} evidencia${evidenceCount === 1 ? "" : "s"} vinculada${evidenceCount === 1 ? "" : "s"}.`)
          : mission?.next_action || text("The thread remains open for the next verified step.", "El hilo permanece abierto para el siguiente paso verificable."),
      };
    }

    function renderActionReceipt(article, message) {
      if ($(".action-receipt", article)) return;
      const target = String(message?.metadata?.action_target || "").trim();
      const mission = message?.mission_id ? (snapshot?.missions || []).find(item => item.id === message.mission_id) : null;
      if (!target && !mission) return;
      const copy = actionCopy(target, mission);
      const receipt = document.createElement("div");
      receipt.className = "action-receipt";
      receipt.innerHTML = `
        <strong>${text("What I did", "Lo que hice")}</strong>
        <span>${esc(copy.body)}</span>
        <small>${esc(copy.footer)}</small>`;
      $(".message-content", article)?.append(receipt);
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

    function renderUnavailableQuestionState(article, message, interview) {
      if ($(".clinical-question-unavailable", article)) return;
      const meta = message?.metadata || {};
      const node = document.createElement("div");
      node.className = "clinical-question-unavailable";
      node.dataset.internalStatus = meta.llm_status || "ai_question_generation_unavailable";
      node.innerHTML = `
        <strong>${text("I could not complete the next personalized questions right now.", "No pude completar las próximas preguntas personalizadas ahora mismo.")}</strong>
        <p>${text("I will not replace them with a generic form or make up information. What you already told me remains saved, and you can retry this part.", "No voy a sustituirlas por un formulario genérico ni inventar información. Lo que ya me dijiste permanece guardado y puedes reintentar esta parte.")}</p>`;
      $(".message-content", article)?.append(node);
      interview.question_source = interview.question_source || "unavailable_not_faked";
    }

    function renderQuestionBlock(article, message) {
      const interview = message?.metadata?.clinical_interview;
      const block = interview?.question_block;
      if (!block || interview.status !== "awaiting_answers" || $(".clinical-question-block", article)) return;

      const questions = Array.isArray(block.questions) ? block.questions : [];
      if (questions.length !== 5) {
        renderUnavailableQuestionState(article, message, interview);
        return;
      }

      const form = document.createElement("form");
      form.className = "clinical-question-block is-progressive";
      form.dataset.interviewId = interview.id;
      form.dataset.stage = String(block.stage || interview.stage || 1);
      form.innerHTML = `
        <header>
          <div><h4>${esc(text("Let me clarify two things first", "Déjame aclarar dos cosas primero"))}</h4><p>${esc(text("I kept what you already told me. I will show the remaining three only after these first two.", "Conservé lo que ya me dijiste. Te mostraré las tres restantes después de estas dos primeras."))}</p></div>
          <span class="clinical-stage">2 + 3</span>
        </header>
        <div class="clinical-questions">
          ${questions.map((question, index) => `
            <fieldset class="clinical-question" data-question-index="${index}" data-question-id="${esc(question.id)}" data-question-prompt="${esc(question.prompt)}" ${index >= 2 ? "hidden" : ""}>
              <legend>${index + 1}. ${esc(question.prompt)}</legend>
              <div class="clinical-options">${optionMarkup(question, interview.id)}</div>
              ${question.allow_detail ? `<input class="clinical-detail" type="text" maxlength="500" placeholder="${esc(question.detail_placeholder || text("Add a detail if it helps", "Agrega un detalle si ayuda"))}">` : ""}
            </fieldset>`).join("")}
        </div>
        <div class="clinical-progress-row">
          <span class="clinical-progress-copy">${text("2 of 5 visible", "2 de 5 visibles")}</span>
          <button class="clinical-show-all" type="button">${text("Continue with the remaining 3", "Continuar con las 3 restantes")}</button>
        </div>
        <p class="clinical-form-error" hidden></p>
        <div class="clinical-submit-row"><button class="clinical-submit" type="submit" hidden>${esc(text("Send my answers", "Enviar mis respuestas"))}</button></div>`;

      const source = interview.question_source || message.metadata?.question_source || "";
      const judgeScore = Number(interview.judge_review?.score ?? message.metadata?.judge_review?.score ?? 0);
      form.dataset.questionSource = source;
      form.dataset.judgeScore = judgeScore ? String(judgeScore) : "";
      const sourceBadge = document.createElement("span");
      sourceBadge.className = "clinical-source is-dynamic";
      sourceBadge.textContent = source === "gemini_dynamic"
        ? text("Questions created for this case", "Preguntas creadas para este caso")
        : text("Adaptive questions checked for this case", "Preguntas adaptativas verificadas para este caso");
      $("header", form)?.append(sourceBadge);

      const reveal = $(".clinical-show-all", form);
      const submit = $(".clinical-submit", form);
      reveal?.addEventListener("click", () => {
        $$(".clinical-question[hidden]", form).forEach(fieldset => { fieldset.hidden = false; });
        reveal.hidden = true;
        submit.hidden = false;
        const progress = $(".clinical-progress-copy", form);
        if (progress) progress.textContent = text("All 5 are now visible", "Las 5 ya están visibles");
        $$(".clinical-question", form)[2]?.scrollIntoView({behavior: "smooth", block: "nearest"});
      });

      form.addEventListener("submit", event => {
        event.preventDefault();
        const error = $(".clinical-form-error", form);
        const answers = [];
        let missing = false;
        $$(".clinical-question", form).forEach(fieldset => {
          const selected = $$("input:checked", fieldset).map(input => input.value);
          const detail = $(".clinical-detail", fieldset)?.value.trim() || "";
          if (!selected.length && !detail) missing = true;
          answers.push({
            question_id: fieldset.dataset.questionId,
            question_prompt: fieldset.dataset.questionPrompt,
            selected,
            detail,
          });
        });
        if (missing) {
          error.textContent = text("Answer each question or add a detail before continuing.", "Responde cada pregunta o agrega un detalle antes de continuar.");
          error.hidden = false;
          return;
        }
        error.hidden = true;
        submit.disabled = true;
        submit.textContent = text("Sending answers…", "Enviando respuestas…");
        const payload = {interview_id: interview.id, stage: Number(form.dataset.stage || 1), answers};
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
        renderActionReceipt(article, message);
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
        <div class="message-content"><div class="message-head"><strong>HealthIA</strong><span>${text("now", "ahora")}</span></div><div class="message-body"><p>${text("Understanding what you said and checking what still matters", "Entendiendo lo que dijiste y revisando qué todavía importa")}<span class="chat-pending-dots"></span></p></div></div>`;
      list.append(article);
      $("#chatScroll")?.scrollTo({top: $("#chatScroll").scrollHeight, behavior: "smooth"});
      pendingTimer = setTimeout(() => {
        const body = $(".message-body", article);
        if (body) body.innerHTML = `<p>${text("I am taking a little longer than usual. If I cannot complete this part safely, I will tell you instead of inventing information.", "Estoy tardando un poco más de lo normal. Si no puedo completar esta parte de forma segura, te lo diré en lugar de inventar información.")}</p>`;
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
      try { await loadSnapshot(); }
      catch (error) { console.warn("HealthIA clinical council hydration failed", error); }
    }

    document.addEventListener("healthia:ui-updated", () => {
      clearTimeout(hydrateTimer);
      hydrateTimer = setTimeout(() => loadSnapshot().catch(() => hydrateMessages()), 80);
    });
    document.addEventListener("healthia:locale-changed", () => {
      renderSidebarCouncil();
      consolidateIdentity();
      hydrateMessages();
    });

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once: true});
    else boot();
  })();
}