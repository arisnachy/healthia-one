if (!window.__HEALTHIA_PATIENT_RECORD__) {
  window.__HEALTHIA_PATIENT_RECORD__ = true;
(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const i18n = window.HealthIAI18n;
  const text = (en, es) => i18n?.locale === "es" ? es : en;
  const localeTag = () => i18n?.browserLocaleTag?.() || "en-US";
  let snapshot = null;
  let refreshTimer = null;

  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));

  async function loadSnapshot() {
    const response = await fetch("/api/bootstrap", {headers:{"Accept-Language":i18n?.locale || "en"}});
    if (!response.ok) throw new Error(`bootstrap ${response.status}`);
    snapshot = await response.json();
    renderPatientOS();
    hydrateMessageActions();
  }

  function activeMissions() {
    return (snapshot?.missions || []).filter(item => !["completed", "cancelled"].includes(item.status));
  }

  function chips(items) {
    return items.length
      ? items.map(item => `<span>${escapeHtml(item)}</span>`).join("")
      : `<span>${escapeHtml(text("No records", "Sin registros"))}</span>`;
  }

  function renderPatientOS() {
    if (!snapshot) return;
    const profile = snapshot.profile;
    const active = activeMissions();
    const setText = (selector, value) => { const node = $(selector); if (node) node.textContent = value; };
    const signals = profile.consented_signal_types || profile.authorized_signals || [];
    setText("#heroPatientName", profile.display_name);
    setText("#signalSummary", `${signals.length} ${text("active types", "tipos activos")}`);
    setText("#openMissionSummary", String(active.length));
    setText("#nextAction", active.at(-1)?.next_action || text(
      "No pending actions. HealthIA will only use signals you authorized.",
      "Sin acciones pendientes. HealthIA usará solo las señales autorizadas.",
    ));
    setText("#nextActionRisk", active.at(-1)?.risk_level || text("stable", "estable"));

    const medicationPreview = $("#medicationPreview");
    if (medicationPreview) {
      medicationPreview.innerHTML = profile.medications.length
        ? profile.medications.map(item => `<span>${escapeHtml(item)}</span>`).join("")
        : `<span>${escapeHtml(text("No medications recorded", "Sin medicamentos registrados"))}</span>`;
    }

    const recordGrid = $("#recordGrid");
    if (recordGrid) {
      recordGrid.innerHTML = `
        <article class="record-card"><header><h3>${text("Confirmed conditions", "Condiciones confirmadas")}</h3><small>${text("Clinical source", "Fuente clínica")}</small></header><div class="record-list">${chips(profile.confirmed_conditions)}</div></article>
        <article class="record-card"><header><h3>${text("Recorded medications", "Medicamentos registrados")}</h3><small>${text("Do not change without review", "No modificar sin revisión")}</small></header><div class="record-list">${chips(profile.medications)}</div></article>
        <article class="record-card"><header><h3>${text("Allergies", "Alergias")}</h3><small>${text("Patient reported", "Declaradas por el paciente")}</small></header><div class="record-list">${chips(profile.allergies)}</div></article>
        <article class="record-card"><header><h3>${text("Authorized signals", "Señales autorizadas")}</h3><small>${text("Patient controlled", "Control del paciente")}</small></header><div class="record-list">${chips(signals)}</div></article>
        <article class="record-card wide"><header><h3>${text("Longitudinal continuity", "Continuidad longitudinal")}</h3><small>${text("Verifiable summary", "Resumen verificable")}</small></header><p>${snapshot.vitals.length} ${text("vital entries", "registros de signos")} · ${snapshot.weights.length} ${text("weights", "pesos")} · ${snapshot.activity.length} ${text("activity entries", "registros de actividad")} · ${snapshot.results.length} ${text("results", "resultados")} · ${snapshot.missions.length} ${text("missions", "misiones")}.</p></article>`;
    }

    $("#chatScroll")?.classList.toggle("has-history", snapshot.messages.length > 1);
  }

  function actionFor(message) {
    const rule = message?.metadata?.rule_key || "";
    const actions = [];
    if (rule.includes("weight")) actions.push([text("Record weight", "Registrar peso"), "weight"]);
    if (rule.includes("bp") || rule.includes("vital")) actions.push([text("Record blood pressure", "Registrar presión"), "vital"]);
    if (rule.includes("activity")) actions.push([text("Record activity", "Registrar actividad"), "activity"]);
    if (rule.includes("result")) actions.push([text("Open results", "Abrir resultados"), "results"]);
    if (message?.metadata?.proactive) actions.push([text("Reply in chat", "Responder en el chat"), "reply"]);
    return actions;
  }

  function hydrateMessageActions() {
    if (!snapshot) return;
    const byId = new Map(snapshot.messages.map(item => [item.id, item]));
    $$("#messageList .message").forEach(article => {
      article.querySelector(".patient-record-actions")?.remove();
      const actions = actionFor(byId.get(article.dataset.id));
      if (!actions.length) return;
      const bar = document.createElement("div");
      bar.className = "message-actions patient-record-actions";
      bar.innerHTML = actions.map(([label, action]) => `<button type="button" data-health-action="${action}">${escapeHtml(label)}</button>`).join("");
      article.querySelector(".message-content")?.append(bar);
    });
  }

  function openDialog(type) { document.querySelector(`[data-dialog="${type}"]`)?.click(); }
  function activateView(view) { document.querySelector(`.main-nav [data-open="${view}"]`)?.click(); }

  function setupMessageActions() {
    $("#messageList")?.addEventListener("click", event => {
      const button = event.target.closest("[data-health-action]");
      if (!button) return;
      const action = button.dataset.healthAction;
      if (["vital", "weight", "activity"].includes(action)) openDialog(action);
      else if (action === "results") activateView("results");
      else if (action === "reply") { activateView("chat"); $("#chatInput")?.focus(); }
    });

    const observer = new MutationObserver(() => {
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => loadSnapshot().catch(() => {}), 180);
    });
    const list = $("#messageList");
    if (list) observer.observe(list, {childList: true});
  }

  function setupComposer() {
    const input = $("#chatInput");
    const send = $("#sendButton");
    if (!input || !send) return;
    const sync = () => { send.disabled = !input.value.trim(); };
    input.addEventListener("input", sync);
    $("#chatForm")?.addEventListener("submit", () => setTimeout(sync, 0));
    sync();
  }

  function setupVoice() {
    const button = $("#voiceButton");
    const input = $("#chatInput");
    if (!button || !input || button.dataset.patientVoiceBound === "true") return;
    button.dataset.patientVoiceBound = "true";
    button.addEventListener("click", () => {
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) {
        const toast = $("#toast");
        if (toast) { toast.textContent = text("Voice dictation is not available in this browser.", "El dictado no está disponible en este navegador."); toast.hidden = false; setTimeout(() => { toast.hidden = true; }, 2800); }
        return;
      }
      const recognition = new Recognition();
      recognition.lang = localeTag();
      recognition.interimResults = true;
      recognition.continuous = false;
      button.classList.add("is-listening");
      recognition.onresult = event => {
        input.value = [...event.results].map(result => result[0].transcript).join(" ");
        input.dispatchEvent(new Event("input", {bubbles:true}));
      };
      recognition.onerror = () => {};
      recognition.onend = () => { button.classList.remove("is-listening"); input.focus(); };
      recognition.start();
    });
  }

  function setupRefreshHooks() {
    ["#runCheck", "#dataForm", "#resultFile", "#resultFilePage"].forEach(selector => {
      $(selector)?.addEventListener(selector.includes("File") ? "change" : "click", () => setTimeout(() => loadSnapshot().catch(() => {}), 700));
    });
    $$('.main-nav [data-open="record"]').forEach(node => node.addEventListener("click", () => loadSnapshot().catch(() => {})));
  }

  function boot() {
    setupComposer(); setupVoice(); setupMessageActions(); setupRefreshHooks(); loadSnapshot().catch(() => {});
  }
  document.addEventListener("healthia:locale-changed", () => { renderPatientOS(); hydrateMessageActions(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once:true}); else boot();
})();

}