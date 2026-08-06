if (window.__HEALTHIA_APP_BOOTED__) {
  console.info("HealthIA app already initialized; duplicate bootstrap ignored.");
} else {
window.__HEALTHIA_APP_BOOTED__ = true;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = { data: null, currentView: "chat", dialogType: null };
const refs = {
  shell: $("#app"), leftRail: $("#leftRail"), contextPanel: $("#contextPanel"),
  messageList: $("#messageList"), chatScroll: $("#chatScroll"), chatForm: $("#chatForm"),
  chatInput: $("#chatInput"), runtimeLabel: $("#runtimeLabel"), agentStatus: $("#agentStatus"),
  runCheck: $("#runCheck"), patientName: $("#patientName"), todayBadge: $("#todayBadge"),
  latestBp: $("#latestBp"), latestBpMeta: $("#latestBpMeta"), latestWeight: $("#latestWeight"),
  weightTrend: $("#weightTrend"), latestActivity: $("#latestActivity"), missionCount: $("#missionCount"),
  missionPreview: $("#missionPreview"), todayList: $("#todayList"), measurementList: $("#measurementList"),
  resultList: $("#resultList"), missionList: $("#missionList"), dialog: $("#dataDialog"),
  dataForm: $("#dataForm"), dialogTitle: $("#dialogTitle"), dialogFields: $("#dialogFields"),
  resultFile: $("#resultFile"), resultFilePage: $("#resultFilePage"), toast: $("#toast"),
  sendButton: $("#sendButton"), heroPatientName: $("#heroPatientName"), signalSummary: $("#signalSummary"),
  openMissionSummary: $("#openMissionSummary"), newConsultation: $("#newConsultation"), closeContext: $("#closeContext")
};


let refreshPromise = null;
let refreshQueued = false;
let eventStream = null;

function setSendState() {
  if (!refs.sendButton || !refs.chatInput) return;
  refs.sendButton.disabled = !refs.chatInput.value.trim();
}

function safeFocusComposer() {
  refs.chatInput?.focus();
  refs.chatInput?.setSelectionRange(refs.chatInput.value.length, refs.chatInput.value.length);
}


const PUBLIC_NAMES = {
  "KIRA Health": "HealthIA", "KIRA": "HealthIA",
  "HISTORIA": "Health history", "SENTINEL": "Safety monitoring",
  "LUMEN": "Results review", "VITA": "Healthy habits",
  "NAVIGATOR": "Follow-up", "HEREDITAS": "Family history",
  "ARCHIVUM": "Documents", "MEDSAFE": "Medication safety",
  "ADVOCATE": "Visit preparation", "BASTION": "Privacy and consent"
};
function publicName(value) { return PUBLIC_NAMES[String(value || "").trim()] || String(value || "HealthIA").replace(/_/g, " "); }

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function renderMarkdown(raw) {
  const lines = String(raw ?? "").split(/\r?\n/);
  const html = [];
  let inList = false;
  for (const source of lines) {
    const line = escapeHtml(source)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
    if (/^###\s+/.test(source)) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push(`<h3>${line.replace(/^###\s+/, "")}</h3>`);
    } else if (/^-\s+/.test(source)) {
      if (!inList) { html.push("<ul>"); inList = true; }
      html.push(`<li>${line.replace(/^-\s+/, "")}</li>`);
    } else if (!source.trim()) {
      if (inList) { html.push("</ul>"); inList = false; }
    } else {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push(`<p>${line}</p>`);
    }
  }
  if (inList) html.push("</ul>");
  return html.join("");
}

function timeLabel(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "ahora" : new Intl.DateTimeFormat("es-DO", {hour:"2-digit", minute:"2-digit"}).format(date);
}

function showToast(message) {
  refs.toast.textContent = message;
  refs.toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { refs.toast.hidden = true; }, 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `Error ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function renderMessage(message) {
  const article = document.createElement("article");
  article.className = `message ${message.role}`;
  article.dataset.id = message.id;
  article.dataset.risk = message.risk_level || "info";
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = message.role === "patient" ? "AM" : "H1";
  const content = document.createElement("div");
  content.className = "message-content";
  if (message.role !== "patient") {
    content.innerHTML = `<div class="message-head"><strong>${escapeHtml(publicName(message.author))}</strong><span>${timeLabel(message.created_at)}</span></div><div class="message-body">${renderMarkdown(message.content)}</div>`;
  } else {
    content.innerHTML = `<div class="message-body">${renderMarkdown(message.content)}</div>`;
  }
  if (message.agent_plan?.length) {
    const details = document.createElement("details");
    details.className = "agent-plan";
    details.innerHTML = `<summary>Ver módulos activados · ${message.agent_plan.length}</summary>` + message.agent_plan.map(step => `<div class="agent-step"><strong>${escapeHtml(publicName(step.agent))}</strong><span>${escapeHtml(step.action)} · ${escapeHtml(step.reason)}</span></div>`).join("");
    content.append(details);
  }
  article.append(avatar, content);
  refs.messageList.append(article);
}

function renderAll() {
  const data = state.data;
  if (!data) return;
  refs.patientName.textContent = data.profile.display_name;
  if (refs.heroPatientName) refs.heroPatientName.textContent = data.profile.display_name || "—";
  if (refs.signalSummary) refs.signalSummary.textContent = `${(data.profile.authorized_signals || []).length || 0} activas`;
  if (refs.openMissionSummary) refs.openMissionSummary.textContent = data.missions.filter(item => !["completed","cancelled"].includes(item.status)).length;
  refs.messageList.replaceChildren();
  const firstPatient = data.messages.findIndex(message => message.role === "patient");
  const visibleMessages = firstPatient < 0
    ? []
    : data.messages.slice(firstPatient).filter(message => !message.metadata?.proactive);
  visibleMessages.forEach(renderMessage);
  refs.chatScroll.classList.toggle("entry-mode", firstPatient < 0);
  refs.chatScroll.classList.toggle("conversation-started", firstPatient >= 0);
  renderContext(); renderToday(); renderMeasurements(); renderResults(); renderMissions();
  document.dispatchEvent(new CustomEvent("healthia:ui-updated"));
  refs.chatScroll.scrollTop = firstPatient < 0 ? 0 : refs.chatScroll.scrollHeight;
}

function renderContext() {
  const data = state.data;
  const vital = data.vitals.at(-1);
  refs.latestBp.textContent = vital?.systolic && vital?.diastolic ? `${vital.systolic}/${vital.diastolic}` : "—";
  refs.latestBpMeta.textContent = vital ? `${timeLabel(vital.measured_at)} · pulso ${vital.pulse || "—"}` : "Sin registro";
  const weight = data.weights.at(-1);
  refs.latestWeight.textContent = weight ? `${weight.weight_kg.toFixed(1)} kg` : "—";
  if (data.weights.length >= 2) {
    const delta = weight.weight_kg - data.weights.at(-2).weight_kg;
    refs.weightTrend.textContent = `${delta >= 0 ? "+" : ""}${delta.toFixed(1)} kg desde el registro previo`;
  } else refs.weightTrend.textContent = "Sin tendencia";
  const activity = data.activity.at(-1);
  refs.latestActivity.textContent = activity ? `${activity.steps.toLocaleString("es-DO")} pasos` : "—";
  const active = data.missions.filter(item => !["completed","cancelled"].includes(item.status));
  refs.missionCount.textContent = active.length;
  refs.missionPreview.innerHTML = active.slice(-3).reverse().map(item => `<div class="mission-preview"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.next_action)}</span></div>`).join("") || `<p>No hay misiones activas.</p>`;
}

function renderToday() {
  const proactive = state.data.messages.filter(message => message.metadata?.proactive);
  refs.todayBadge.textContent = proactive.length;
  refs.todayList.innerHTML = proactive.slice().reverse().map(message => `<article class="data-card"><header><h3>${escapeHtml(publicName(message.author))}</h3><small>${timeLabel(message.created_at)}</small></header><div>${renderMarkdown(message.content)}</div></article>`).join("") || `<article class="data-card"><h3>Todo tranquilo</h3><p>No hay nuevas intervenciones proactivas.</p></article>`;
}

function renderMeasurements() {
  const items = [];
  state.data.vitals.slice().reverse().forEach(v => items.push({title:`Presión ${v.systolic || "—"}/${v.diastolic || "—"}`, body:`Pulso ${v.pulse || "—"}`, date:v.measured_at}));
  state.data.weights.slice().reverse().forEach(v => items.push({title:`Peso ${v.weight_kg.toFixed(1)} kg`, body:v.note || "Registro del paciente", date:v.measured_at}));
  state.data.activity.slice().reverse().forEach(v => items.push({title:`${v.steps.toLocaleString("es-DO")} pasos`, body:`${v.active_minutes} minutos activos`, date:v.measured_at}));
  refs.measurementList.innerHTML = items.sort((a,b) => new Date(b.date)-new Date(a.date)).map(item => `<article class="data-card"><header><h3>${escapeHtml(item.title)}</h3><small>${timeLabel(item.date)}</small></header><p>${escapeHtml(item.body)}</p></article>`).join("") || `<article class="data-card"><p>Sin mediciones.</p></article>`;
}

function renderResults() {
  refs.resultList.innerHTML = state.data.results.slice().reverse().map(result => `<article class="data-card"><header><h3>${escapeHtml(result.panel)}</h3><small>${escapeHtml(result.status)}</small></header><p>${escapeHtml(result.filename)} · ${result.items.length} valores</p><div>${renderMarkdown(result.explanation)}</div></article>`).join("") || `<article class="data-card"><p>No has cargado resultados.</p></article>`;
}

function renderMissions() {
  refs.missionList.innerHTML = state.data.missions.slice().reverse().map(mission => `<article class="data-card"><header><h3>${escapeHtml(mission.title)}</h3><small>${escapeHtml(mission.status)}</small></header><p>${escapeHtml(mission.next_action)}</p><small>${mission.agent_plan.length} módulos · ${mission.evidence_ids.length} evidencias</small></article>`).join("") || `<article class="data-card"><p>Las misiones aparecerán cuando HealthIA detecte o reciba un asunto de seguimiento.</p></article>`;
}

async function refresh(force = false) {
  if (refreshPromise && !force) {
    refreshQueued = true;
    return refreshPromise;
  }
  refreshPromise = (async () => {
    state.data = await api("/api/bootstrap");
    renderAll();
  })();
  try {
    await refreshPromise;
  } finally {
    refreshPromise = null;
    if (refreshQueued) {
      refreshQueued = false;
      queueMicrotask(() => refresh(true));
    }
  }
}

function setView(view) {
  state.currentView = view;
  $$(".view").forEach(node => node.classList.toggle("is-active", node.id === `view-${view}`));
  $$('.main-nav [data-open], .primary-action[data-open]').forEach(node => node.classList.toggle("is-active", node.dataset.open === view));
  if (window.innerWidth < 760) refs.shell.classList.remove("menu-open");
  if (view === "chat") requestAnimationFrame(safeFocusComposer);
}

async function sendMessage(text) {
  const clean = text.trim();
  if (!clean) return;
  refs.chatInput.value = "";
  refs.chatInput.style.height = "auto";
  setSendState();
  refs.agentStatus.textContent = "HealthIA organizando el siguiente paso…";
  const patient = {id:`local_${Date.now()}`, role:"patient", author:state.data.profile.display_name, content:clean, created_at:new Date().toISOString(), risk_level:"info", agent_plan:[]};
  state.data.messages.push(patient); renderMessage(patient); refs.chatScroll.scrollTop = refs.chatScroll.scrollHeight;
  try {
    const response = await api("/api/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message:clean})});
    if (response.mission) state.data.missions.push(response.mission);
    state.data.messages.push(response.message); renderMessage(response.message); renderContext(); renderMissions();
  } catch (error) { showToast(error.message); }
  refs.agentStatus.textContent = "Equipo en segundo plano";
  refs.chatScroll.scrollTop = refs.chatScroll.scrollHeight;
}

async function upload(file) {
  if (!file) return;
  const form = new FormData(); form.append("file", file);
  refs.agentStatus.textContent = "HealthIA revisando el archivo…";
  try {
    const result = await api("/api/results/upload", {method:"POST", body:form});
    state.data.results.push(result); renderResults(); renderContext(); setView("results"); showToast("Resultado guardado y procesado.");
  } catch (error) { showToast(error.message); }
  refs.agentStatus.textContent = "Equipo en segundo plano";
}

const dialogDefinitions = {
  vital: {title:"Registrar presión y signos", fields:[['systolic','Sistólica','number'],['diastolic','Diastólica','number'],['pulse','FC · lpm','number'],['respiratory_rate','FR · rpm','number'],['oxygen_saturation','Oximetría · %','number'],['temperature_c','Temperatura · °C','number'],['blood_glucose_mg_dl','Glicemia · mg/dL','number'],['cholesterol_mg_dl','Colesterol · mg/dL','number'],['symptoms','Síntomas separados por coma','text']]},
  weight: {title:"Registrar peso", fields:[['weight_kg','Peso en kg','number'],['note','Contexto o nota','text']]},
  activity: {title:"Registrar actividad", fields:[['steps','Pasos','number'],['active_minutes','Minutos activos','number'],['note','Barrera o contexto','text']]}
};

function openDialog(type) {
  state.dialogType = type;
  const def = dialogDefinitions[type];
  refs.dialogTitle.textContent = def.title;
  refs.dialogFields.innerHTML = `<div class="form-grid">${def.fields.map(([name,label,inputType]) => `<label>${escapeHtml(label)}<input name="${name}" type="${inputType}" ${inputType === 'number' ? 'step="any"' : ''}></label>`).join("")}</div>`;
  refs.dialog.showModal();
}

async function saveDialog() {
  const form = new FormData(refs.dataForm);
  const payload = Object.fromEntries(form.entries());
  Object.keys(payload).forEach(key => { if (payload[key] === "") delete payload[key]; });
  for (const key of ["systolic","diastolic","pulse","respiratory_rate","oxygen_saturation","temperature_c","blood_glucose_mg_dl","cholesterol_mg_dl","weight_kg","steps","active_minutes"]) if (payload[key] !== undefined) payload[key] = Number(payload[key]);
  if (payload.symptoms) payload.symptoms = payload.symptoms.split(",").map(item => item.trim()).filter(Boolean);
  const endpoint = {vital:"/api/vitals", weight:"/api/weight", activity:"/api/activity"}[state.dialogType];
  try { await api(endpoint, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)}); refs.dialog.close(); await refresh(); showToast("Medición guardada."); }
  catch (error) { showToast(error.message); }
}

function connectEvents() {
  if (eventStream) return;
  eventStream = new EventSource("/api/events/stream");
  let refreshTimer = null;
  eventStream.onmessage = async event => {
    const payload = JSON.parse(event.data);
    if (payload.type === "message" && !state.data.messages.some(item => item.id === payload.message.id)) {
      state.data.messages.push(payload.message);
      renderMessage(payload.message);
      renderToday();
      refs.chatScroll.scrollTop = refs.chatScroll.scrollHeight;
      showToast("HealthIA se adelantó con una nueva observación.");
    } else if (payload.type === "state") {
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => refresh(), 120);
    } else if (payload.type === "runtime_error") showToast("El agente reportó un error auditable.");
  };
  eventStream.onerror = () => showToast("La conexión de eventos se reconectará automáticamente.");
}

refs.chatForm.addEventListener("submit", event => { event.preventDefault(); sendMessage(refs.chatInput.value); });
refs.chatInput.addEventListener("input", () => { refs.chatInput.style.height = "auto"; refs.chatInput.style.height = `${Math.min(refs.chatInput.scrollHeight,150)}px`; setSendState(); });
refs.chatInput.addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); refs.chatForm.requestSubmit(); } });
$$('[data-prompt]').forEach(button => button.addEventListener("click", () => sendMessage(button.dataset.prompt)));
$$('[data-open]').forEach(button => button.addEventListener("click", () => setView(button.dataset.open)));
$$('[data-dialog]').forEach(button => button.addEventListener("click", () => openDialog(button.dataset.dialog)));
refs.dataForm.addEventListener("submit", event => { if (event.submitter?.value === "cancel") return; event.preventDefault(); saveDialog(); });
refs.resultFile.addEventListener("change", () => upload(refs.resultFile.files[0]));
refs.resultFilePage.addEventListener("change", () => upload(refs.resultFilePage.files[0]));
refs.runCheck.addEventListener("click", async () => { refs.agentStatus.textContent = "HealthIA revisando continuidad…"; const out = await api("/api/demo/tick", {method:"POST"}); await refresh(); refs.agentStatus.textContent = "Equipo en segundo plano"; showToast(out.created ? `${out.created} observaciones nuevas.` : "No hay nuevas observaciones."); });
$("#collapseLeft").addEventListener("click", () => refs.shell.classList.toggle("left-collapsed"));
function syncContextToggle() {
  if (!refs.closeContext) return;
  const open = window.innerWidth <= 1080 ? refs.shell.classList.contains("context-open") : !refs.shell.classList.contains("right-collapsed");
  refs.closeContext.textContent = open ? "›" : "‹";
  refs.closeContext.setAttribute("aria-label", open ? "Colapsar contexto" : "Expandir contexto");
}
$("#collapseRight").addEventListener("click", () => { if (window.innerWidth <= 1080) refs.shell.classList.toggle("context-open"); else refs.shell.classList.toggle("right-collapsed"); syncContextToggle(); });
$("#closeContext").addEventListener("click", () => { if (window.innerWidth <= 1080) refs.shell.classList.toggle("context-open"); else refs.shell.classList.toggle("right-collapsed"); syncContextToggle(); });
$("#mobileMenu").addEventListener("click", () => refs.shell.classList.toggle("menu-open"));
refs.newConsultation?.addEventListener("click", async event => {
  event.preventDefault();
  refs.newConsultation.disabled = true;
  try {
    await api("/api/demo/reset", {method:"POST"});
    await refresh(true);
    setView("chat");
    refs.chatInput.value = "";
    refs.chatInput.style.height = "auto";
    setSendState();
    safeFocusComposer();
    showToast("Nueva consulta lista para iniciar.");
  } catch (error) { showToast(error.message); }
  finally { refs.newConsultation.disabled = false; }
});

(async function boot() {
  try {
    const readiness = await api("/api/readiness");
    refs.runtimeLabel.textContent = `${readiness.store_backend} · ${readiness.llm_backend}`;
    setSendState();
    syncContextToggle();
    await refresh();
    connectEvents();
  } catch (error) { showToast(error.message); }
})();

}
