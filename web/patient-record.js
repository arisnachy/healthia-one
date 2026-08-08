if (!window.__HEALTHIA_PATIENT_RECORD__) {
  window.__HEALTHIA_PATIENT_RECORD__ = true;
(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  let snapshot = null;
  let refreshTimer = null;

  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));

  async function loadSnapshot() {
    const response = await (window.healthiaFetch || fetch)("/api/bootstrap");
    if (!response.ok) throw new Error(`bootstrap ${response.status}`);
    snapshot = await response.json();
    renderPatientOS();
    hydrateMessageActions();
  }

  function activeMissions() {
    return (snapshot?.missions || []).filter(item => !["completed", "cancelled"].includes(item.status));
  }

  function renderPatientOS() {
    if (!snapshot) return;
    const profile = snapshot.profile;
    const active = activeMissions();
    const setText = (selector, value) => { const node = $(selector); if (node) node.textContent = value; };
    setText("#heroPatientName", profile.display_name);
    setText("#signalSummary", `${profile.consented_signal_types.length} tipos activos`);
    setText("#openMissionSummary", String(active.length));
    setText("#nextAction", active.at(-1)?.next_action || "Sin acciones pendientes. HealthIA seguirá observando solo las señales autorizadas.");
    setText("#nextActionRisk", active.at(-1)?.risk_level || "estable");

    const medicationPreview = $("#medicationPreview");
    if (medicationPreview) {
      medicationPreview.innerHTML = profile.medications.length
        ? profile.medications.map(item => `<span>${escapeHtml(item)}</span>`).join("")
        : "<span>Sin medicamentos registrados</span>";
    }

    const chips = items => items.length
      ? items.map(item => `<span>${escapeHtml(item)}</span>`).join("")
      : "<span>Sin registros</span>";
    const recordGrid = $("#recordGrid");
    if (recordGrid) {
      recordGrid.innerHTML = `
        <article class="record-card"><header><h3>Condiciones confirmadas</h3><small>Fuente clínica</small></header><div class="record-list">${chips(profile.confirmed_conditions)}</div></article>
        <article class="record-card"><header><h3>Medicamentos registrados</h3><small>No modificar sin revisión</small></header><div class="record-list">${chips(profile.medications)}</div></article>
        <article class="record-card"><header><h3>Alergias</h3><small>Declaradas por el paciente</small></header><div class="record-list">${chips(profile.allergies)}</div></article>
        <article class="record-card"><header><h3>Señales autorizadas</h3><small>Control del paciente</small></header><div class="record-list">${chips(profile.consented_signal_types)}</div></article>
        <article class="record-card wide"><header><h3>Continuidad longitudinal</h3><small>Resumen verificable</small></header><p>${snapshot.vitals.length} registros de signos · ${snapshot.weights.length} pesos · ${snapshot.activity.length} registros de actividad · ${snapshot.results.length} resultados · ${snapshot.missions.length} misiones.</p></article>`;
    }

    $("#chatScroll")?.classList.toggle("has-history", snapshot.messages.length > 1);
  }

  function actionFor(message) {
    const rule = message?.metadata?.rule_key || "";
    const actions = [];
    if (rule.includes("weight")) actions.push(["Registrar peso", "weight"]);
    if (rule.includes("bp") || rule.includes("vital")) actions.push(["Registrar presión", "vital"]);
    if (rule.includes("activity")) actions.push(["Registrar actividad", "activity"]);
    if (rule.includes("result")) actions.push(["Abrir resultados", "results"]);
    if (message?.metadata?.proactive) actions.push(["Responder en el chat", "reply"]);
    return actions;
  }

  function hydrateMessageActions() {
    if (!snapshot) return;
    const byId = new Map(snapshot.messages.map(item => [item.id, item]));
    $$("#messageList .message").forEach(article => {
      if (article.querySelector(".message-actions")) return;
      const actions = actionFor(byId.get(article.dataset.id));
      if (!actions.length) return;
      const bar = document.createElement("div");
      bar.className = "message-actions";
      bar.innerHTML = actions.map(([label, action]) => `<button type="button" data-health-action="${action}">${escapeHtml(label)}</button>`).join("");
      article.querySelector(".message-content")?.append(bar);
    });
  }

  function openDialog(type) {
    document.querySelector(`[data-dialog="${type}"]`)?.click();
  }

  function activateView(view) {
    document.querySelector(`.main-nav [data-open="${view}"]`)?.click();
  }

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
    if (!button || !input) return;
    button.addEventListener("click", () => {
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) {
        const toast = $("#toast");
        if (toast) { toast.textContent = "El dictado no está disponible en este navegador."; toast.hidden = false; setTimeout(() => { toast.hidden = true; }, 2800); }
        return;
      }
      const recognition = new Recognition();
      recognition.lang = "es-DO";
      recognition.interimResults = true;
      recognition.continuous = false;
      button.classList.add("is-listening");
      recognition.onresult = event => {
        input.value = [...event.results].map(result => result[0].transcript).join(" ");
        input.dispatchEvent(new Event("input"));
      };
      recognition.onerror = () => {};
      recognition.onend = () => { button.classList.remove("is-listening"); input.focus(); };
      recognition.start();
    });
  }

  function setupRefreshHooks() {
    ["#runCheck", "#dataForm", "#resultFile", "#resultFilePage"].forEach(selector => {
      $(selector)?.addEventListener(selector.includes("File") ? "change" : "click", () => {
        setTimeout(() => loadSnapshot().catch(() => {}), 700);
      });
    });
    $$('.main-nav [data-open="record"]').forEach(node => node.addEventListener("click", () => loadSnapshot().catch(() => {})));
  }

  window.addEventListener("DOMContentLoaded", () => {
    setupComposer();
    setupVoice();
    setupMessageActions();
    setupRefreshHooks();
    loadSnapshot().catch(() => {});
  });
})();

}
