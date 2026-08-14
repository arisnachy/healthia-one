if (window.__HEALTHIA_APP_BOOTED__) {
  console.info("HealthIA app already initialized; duplicate bootstrap ignored.");
} else {
window.__HEALTHIA_APP_BOOTED__ = true;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const i18n = window.HealthIAI18n;
const tr = (key, vars = {}) => i18n?.t(key, vars) || key;
const localeTag = () => i18n?.browserLocaleTag?.() || "en-US";

const state = { data: null, currentView: "chat", dialogType: null, resultProcessing: null };
const refs = {
  shell: $("#app"), leftRail: $("#leftRail"), contextPanel: $("#contextPanel"),
  messageList: $("#messageList"), chatScroll: $("#chatScroll"), chatForm: $("#chatForm"),
  chatInput: $("#chatInput"), runtimeLabel: $("#runtimeLabel"), agentStatus: $("#agentStatus"),
  runCheck: $("#runCheck"), todayBadge: $("#todayBadge"),
  latestBp: $("#latestBp"), latestBpMeta: $("#latestBpMeta"), latestWeight: $("#latestWeight"),
  weightTrend: $("#weightTrend"), latestActivity: $("#latestActivity"), missionCount: $("#missionCount"),
  missionPreview: $("#missionPreview"), todayList: $("#todayList"), measurementList: $("#measurementList"),
  resultList: $("#resultList"), resultProcessing: $("#resultProcessing"), missionList: $("#missionList"), dialog: $("#dataDialog"),
  dataForm: $("#dataForm"), dialogTitle: $("#dialogTitle"), dialogFields: $("#dialogFields"),
  resultFile: $("#resultFile"), resultFilePage: $("#resultFilePage"), toast: $("#toast"),
  sendButton: $("#sendButton"), heroPatientName: $("#heroPatientName"), signalSummary: $("#signalSummary"),
  openMissionSummary: $("#openMissionSummary"), newConsultation: $("#newConsultation"), closeContext: $("#closeContext"),
  expandLeft: $("#expandLeft"), originalPreviewDialog: $("#originalPreviewDialog"), originalPreviewTitle: $("#originalPreviewTitle"),
  originalPreviewBody: $("#originalPreviewBody"), closeOriginalPreview: $("#closeOriginalPreview"), downloadOriginal: $("#downloadOriginal")
};

let refreshPromise = null;
let refreshQueued = false;
let eventStream = null;

function inputLocale(text) {
  return i18n?.detectInputLocale?.(text, i18n.locale) || i18n?.locale || "en";
}

function setSendState() {
  if (!refs.sendButton || !refs.chatInput) return;
  refs.sendButton.disabled = !refs.chatInput.value.trim();
}

function safeFocusComposer() {
  refs.chatInput?.focus();
  refs.chatInput?.setSelectionRange(refs.chatInput.value.length, refs.chatInput.value.length);
}

function publicName(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized.includes("healthia") ? "HealthIA" : tr("app.module");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function healthiaAvatarSvg() { return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3.2c.62 4.14 2.66 6.18 6.8 6.8-4.14.62-6.18 2.66-6.8 6.8-.62-4.14-2.66-6.18-6.8-6.8 4.14-.62 6.18-2.66 6.8-6.8Z"/><path d="M6.1 17.8h4.1l1.45-3.05 2.05 4.1 1.2-2.2h3"/></svg>'; }
function resultCopy(key) { const es = i18n?.locale === "es"; return ({uploading:es ? "Protegiendo y cargando tu original" : "Protecting and uploading your original", reading:es ? "Leyendo lo disponible, sin inventar hallazgos" : "Reading what is available, without inventing findings", original:es ? "Ver original" : "View original", download:es ? "Descargar original" : "Download original", image:es ? "Vista previa de imagen" : "Image preview", pdf:es ? "Vista previa de PDF" : "PDF preview", unavailable:es ? "Este formato no tiene vista previa visual. Puedes abrir o descargar el original." : "This format has no visual preview. You can open or download the original."})[key]; }
function documentUrl(document, inline = false) { return `/api/documents/${encodeURIComponent(document.id)}/download${inline ? "?inline=1" : ""}`; }
function documentKind(document) { const mime = String(document?.mime_type || "").toLowerCase(), filename = String(document?.filename || "").toLowerCase(); if (mime.startsWith("image/") || /\.(png|jpe?g|webp|gif)$/i.test(filename)) return "image"; return mime === "application/pdf" || filename.endsWith(".pdf") ? "pdf" : "other"; }
function setResultProcessing(stage = null) { state.resultProcessing = stage; if (!refs.resultProcessing) return; const active = Boolean(stage); refs.resultProcessing.hidden = !active; refs.resultProcessing.innerHTML = active ? `<span class="processing-avatar">${healthiaAvatarSvg()}</span><div><strong>${escapeHtml(resultCopy(stage))}</strong><small>${escapeHtml(stage === "uploading" ? resultCopy("reading") : resultCopy("uploading"))}</small></div><span class="processing-dots" aria-hidden="true"><i></i><i></i><i></i></span>` : ""; [refs.resultFile, refs.resultFilePage].forEach(input => { if (input) input.disabled = active; }); }

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
  return Number.isNaN(date.getTime()) ? tr("app.now") : new Intl.DateTimeFormat(localeTag(), {hour:"2-digit", minute:"2-digit"}).format(date);
}

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

function showToast(message) {
  refs.toast.textContent = message;
  refs.toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { refs.toast.hidden = true; }, 3200);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Accept-Language")) headers.set("Accept-Language", i18n?.locale || "en");
  const response = await fetch(path, {...options, headers});
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
  if (message.role === "patient") avatar.textContent = "P";
  else { avatar.classList.add("healthia-avatar"); avatar.innerHTML = healthiaAvatarSvg(); }
  const content = document.createElement("div");
  content.className = "message-content";
  if (message.role !== "patient") {
    content.innerHTML = `<div class="message-head"><strong>${escapeHtml(publicName(message.author))}</strong><span>${timeLabel(message.created_at)}</span></div><div class="message-body">${renderMarkdown(educationVisibleMessage(message))}</div>`;
  } else {
    content.innerHTML = `<div class="message-body">${renderMarkdown(message.content)}</div>`;
  }
  appendEducationControls(message, content);
  if (message.agent_plan?.length) {
    const details = document.createElement("details");
    details.className = "agent-plan";
    details.innerHTML = `<summary>${escapeHtml(tr("app.modules"))} · ${message.agent_plan.length}</summary>` + message.agent_plan.map(step => `<div class="agent-step"><strong>${escapeHtml(publicName(step.agent))}</strong><span>${escapeHtml(step.action)} · ${escapeHtml(step.reason)}</span></div>`).join("");
    content.append(details);
  }
  article.append(avatar, content);
  refs.messageList.append(article);
}

function renderAll() {
  const data = state.data;
  if (!data) return;
  if (refs.heroPatientName) refs.heroPatientName.textContent = data.profile.display_name || "—";
  if (refs.signalSummary) refs.signalSummary.textContent = `${(data.profile.authorized_signals || []).length || 0} ${tr("app.active_signals")}`;
  if (refs.openMissionSummary) refs.openMissionSummary.textContent = data.missions.filter(item => !["completed","cancelled"].includes(item.status)).length;
  refs.messageList.replaceChildren();
  const lastConversationBoundary = data.messages.reduce((last, message, index) => message.metadata?.conversation_boundary === "new_consultation" ? index : last, -1);
  const activeConversation = lastConversationBoundary >= 0 ? data.messages.slice(lastConversationBoundary + 1) : data.messages;
  const firstPatient = activeConversation.findIndex(message => message.role === "patient");
  const visibleMessages = firstPatient < 0 ? [] : activeConversation.slice(firstPatient).filter(message => !message.metadata?.proactive);
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
  refs.latestBpMeta.textContent = vital ? `${timeLabel(vital.measured_at)} · ${tr("app.pulse")} ${vital.pulse || "—"}` : tr("context.no_record");
  const weight = data.weights.at(-1);
  refs.latestWeight.textContent = weight ? `${weight.weight_kg.toFixed(1)} kg` : "—";
  if (data.weights.length >= 2) {
    const delta = weight.weight_kg - data.weights.at(-2).weight_kg;
    refs.weightTrend.textContent = i18n?.locale === "es"
      ? `${delta >= 0 ? "+" : ""}${delta.toFixed(1)} kg desde el registro previo`
      : `${delta >= 0 ? "+" : ""}${delta.toFixed(1)} kg since the previous entry`;
  } else refs.weightTrend.textContent = tr("context.no_trend");
  const activity = data.activity.at(-1);
  refs.latestActivity.textContent = activity ? `${activity.steps.toLocaleString(localeTag())} ${tr("app.steps")}` : "—";
  const active = data.missions.filter(item => !["completed","cancelled"].includes(item.status));
  refs.missionCount.textContent = active.length;
  refs.missionPreview.innerHTML = active.slice(-3).reverse().map(item => `<div class="mission-preview"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.next_action)}</span></div>`).join("") || `<p>${escapeHtml(tr("app.no_missions"))}</p>`;
}

function renderToday() {
  const proactive = state.data.messages.filter(message => message.metadata?.proactive);
  refs.todayBadge.textContent = proactive.length;
  refs.todayList.innerHTML = proactive.slice().reverse().map(message => `<article class="data-card"><header><h3>${escapeHtml(publicName(message.author))}</h3><small>${timeLabel(message.created_at)}</small></header><div>${renderMarkdown(message.content)}</div></article>`).join("") || `<article class="data-card"><h3>${escapeHtml(tr("app.all_quiet"))}</h3><p>${escapeHtml(tr("app.no_proactive"))}</p></article>`;
}

function renderMeasurements() {
  const items = [];
  state.data.vitals.slice().reverse().forEach(v => items.push({title:`${tr("app.bp")} ${v.systolic || "—"}/${v.diastolic || "—"}`, body:`${tr("app.pulse")} ${v.pulse || "—"}`, date:v.measured_at}));
  state.data.weights.slice().reverse().forEach(v => items.push({title:`${tr("app.weight")} ${v.weight_kg.toFixed(1)} kg`, body:v.note || tr("app.patient_record"), date:v.measured_at}));
  state.data.activity.slice().reverse().forEach(v => items.push({title:`${v.steps.toLocaleString(localeTag())} ${tr("app.steps")}`, body:`${v.active_minutes} ${tr("app.active_minutes")}`, date:v.measured_at}));
  refs.measurementList.innerHTML = items.sort((a,b) => new Date(b.date)-new Date(a.date)).map(item => `<article class="data-card"><header><h3>${escapeHtml(item.title)}</h3><small>${timeLabel(item.date)}</small></header><p>${escapeHtml(item.body)}</p></article>`).join("") || `<article class="data-card"><p>${escapeHtml(tr("app.no_measurements"))}</p></article>`;
}

function renderResults() {
  const documents = state.data.documents || [];
  refs.resultList.innerHTML = state.data.results.slice().reverse().map(result => {
    const original = documents.find(document => document.related_result_id === result.id);
    const kind = documentKind(original);
    const preview = original && kind === "image"
      ? `<button type="button" class="result-preview result-image-preview" data-open-original="${escapeHtml(original.id)}" aria-label="${escapeHtml(resultCopy("image"))}: ${escapeHtml(original.filename)}"><img src="${documentUrl(original, true)}" alt="${escapeHtml(resultCopy("image"))}: ${escapeHtml(original.filename)}"></button>`
      : original && kind === "pdf"
        ? `<div class="result-preview result-pdf-preview"><iframe title="${escapeHtml(resultCopy("pdf"))}: ${escapeHtml(original.filename)}" loading="lazy" src="${documentUrl(original, true)}#toolbar=0&navpanes=0"></iframe><button type="button" data-open-original="${escapeHtml(original.id)}">${escapeHtml(resultCopy("original"))}</button></div>`
        : "";
    const evidence = original
      ? `<div class="result-evidence"><button type="button" data-open-original="${escapeHtml(original.id)}">${escapeHtml(resultCopy("original"))}</button><a href="${documentUrl(original)}" download>${escapeHtml(resultCopy("download"))}</a><span>${escapeHtml(tr("app.twin_linked"))} · ${escapeHtml(original.status)}</span></div>`
      : `<div class="result-evidence"><span>${escapeHtml(tr("app.no_original"))}</span></div>`;
    return `<article class="data-card result-card" data-result-id="${escapeHtml(result.id)}"><header><h3>${escapeHtml(result.panel)}</h3><small>${escapeHtml(result.status)}</small></header><p>${escapeHtml(result.filename)} · ${result.items.length} ${escapeHtml(tr("app.extracted"))}</p>${preview}<div>${renderMarkdown(result.explanation)}</div>${evidence}</article>`;
  }).join("") || `<article class="data-card"><p>${escapeHtml(tr("app.no_results"))}</p></article>`;
}

function openOriginalPreview(documentId) {
  const document = state.data?.documents?.find(item => item.id === documentId);
  if (!document || !refs.originalPreviewDialog) return;
  const kind = documentKind(document), inlineUrl = documentUrl(document, true);
  refs.originalPreviewTitle.textContent = document.filename || resultCopy("original");
  refs.downloadOriginal.href = documentUrl(document);
  refs.downloadOriginal.textContent = resultCopy("download");
  refs.originalPreviewBody.innerHTML = kind === "image"
    ? `<img src="${inlineUrl}" alt="${escapeHtml(resultCopy("image"))}: ${escapeHtml(document.filename)}">`
    : kind === "pdf" ? `<iframe title="${escapeHtml(resultCopy("pdf"))}: ${escapeHtml(document.filename)}" src="${inlineUrl}#toolbar=1&navpanes=0"></iframe>` : `<p>${escapeHtml(resultCopy("unavailable"))}</p>`;
  refs.originalPreviewDialog.showModal();
}

function renderMissions() {
  refs.missionList.innerHTML = state.data.missions.slice().reverse().map(mission => `<article class="data-card"><header><h3>${escapeHtml(mission.title)}</h3><small>${escapeHtml(mission.status)}</small></header><p>${escapeHtml(mission.next_action)}</p><small>${mission.agent_plan.length} ${escapeHtml(tr("app.modules_short"))} · ${mission.evidence_ids.length} ${escapeHtml(tr("app.evidence_short"))}</small></article>`).join("") || `<article class="data-card"><p>${escapeHtml(tr("app.no_missions_yet"))}</p></article>`;
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
  try { await refreshPromise; }
  finally {
    refreshPromise = null;
    if (refreshQueued) { refreshQueued = false; queueMicrotask(() => refresh(true)); }
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
  const responseLocale = inputLocale(clean);
  refs.chatInput.value = "";
  refs.chatInput.style.height = "auto";
  setSendState();
  refs.agentStatus.textContent = tr("app.analyzing");
  const patient = {id:`local_${Date.now()}`, role:"patient", author:state.data.profile.display_name, content:clean, created_at:new Date().toISOString(), risk_level:"info", agent_plan:[], metadata:{input_locale:responseLocale}};
  state.data.messages.push(patient); renderMessage(patient); refs.chatScroll.scrollTop = refs.chatScroll.scrollHeight;
  let chatOutcome = "error";
  try {
    const response = await api("/api/chat", {method:"POST", headers:{"Content-Type":"application/json", "Accept-Language":responseLocale}, body:JSON.stringify({message:clean})});
    if (response.mission) {
      const missionIndex = state.data.missions.findIndex(item => item.id === response.mission.id);
      if (missionIndex >= 0) state.data.missions[missionIndex] = response.mission;
      else state.data.missions.push(response.mission);
    }
    document.dispatchEvent(new CustomEvent("healthia:chat-settled", {detail:{outcome:"response"}}));
    state.data.messages.push(response.message); renderMessage(response.message); renderContext(); renderMissions();
    chatOutcome = "response";
  } catch (error) { showToast(error.message); }
  finally {
    if (chatOutcome !== "response") document.dispatchEvent(new CustomEvent("healthia:chat-settled", {detail:{outcome:chatOutcome}}));
    refs.agentStatus.textContent = tr("app.ready");
    refs.chatScroll.scrollTop = refs.chatScroll.scrollHeight;
  }
}

async function upload(file) {
  if (!file) return;
  const form = new FormData(); form.append("file", file);
  setResultProcessing("uploading");
  refs.agentStatus.textContent = tr("app.uploading");
  try {
    const result = await api("/api/results/upload", {method:"POST", body:form});
    setResultProcessing("reading");
    await refresh(true);
    setView("results");
    showToast(result.status === "parsed" ? tr("app.result_parsed") : tr("app.result_pending"));
  } catch (error) { showToast(error.message); }
  setResultProcessing();
  refs.agentStatus.textContent = tr("app.ready");
}

function dialogDefinitions() {
  return {
    vital: {title:tr("dialog.vital"), fields:[['systolic',tr('field.systolic'),'number'],['diastolic',tr('field.diastolic'),'number'],['pulse',tr('field.pulse'),'number'],['respiratory_rate',tr('field.rr'),'number'],['oxygen_saturation',tr('field.oxygen'),'number'],['temperature_c',tr('field.temp'),'number'],['blood_glucose_mg_dl',tr('field.glucose'),'number'],['cholesterol_mg_dl',tr('field.cholesterol'),'number'],['symptoms',tr('field.symptoms'),'text']]},
    weight: {title:tr("dialog.weight"), fields:[['weight_kg',tr('field.weight'),'number'],['note',tr('field.note'),'text']]},
    activity: {title:tr("dialog.activity"), fields:[['steps',tr('field.steps'),'number'],['active_minutes',tr('field.minutes'),'number'],['note',tr('field.barrier'),'text']]}
  };
}

function openDialog(type) {
  state.dialogType = type;
  const def = dialogDefinitions()[type];
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
  try { await api(endpoint, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)}); refs.dialog.close(); await refresh(); showToast(tr("app.saved")); }
  catch (error) { showToast(error.message); }
}

function connectEvents() {
  if (eventStream) return;
  eventStream = new EventSource("/api/events/stream");
  let refreshTimer = null;
  eventStream.onmessage = async event => {
    const payload = JSON.parse(event.data);
    if (payload.type === "message" && !state.data.messages.some(item => item.id === payload.message.id)) {
      state.data.messages.push(payload.message); renderMessage(payload.message); renderToday(); refs.chatScroll.scrollTop = refs.chatScroll.scrollHeight; showToast(tr("app.event_observation"));
    } else if (payload.type === "state") {
      clearTimeout(refreshTimer); refreshTimer = setTimeout(() => refresh(), 120);
    } else if (payload.type === "runtime_error") showToast(tr("app.runtime_error"));
  };
  eventStream.onerror = () => showToast(tr("app.reconnecting"));
}

refs.chatForm.addEventListener("submit", event => { event.preventDefault(); sendMessage(refs.chatInput.value); });
refs.chatInput.addEventListener("input", () => { refs.chatInput.style.height = "auto"; refs.chatInput.style.height = `${Math.min(refs.chatInput.scrollHeight,150)}px`; setSendState(); });
refs.chatInput.addEventListener("keydown", event => {
  if (event.isComposing || event.keyCode === 229) return;
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); refs.chatForm.requestSubmit(); }
});
$$('[data-prompt-en]').forEach(button => button.addEventListener("click", () => {
  const key = button.dataset.promptKey;
  const translated = key && !["en","es"].includes(i18n?.locale) ? tr(key) : "";
  sendMessage(translated || button.dataset[i18n?.locale === "es" ? "promptEs" : "promptEn"] || button.dataset.promptEn);
}));
$$('[data-open]').forEach(button => button.addEventListener("click", () => setView(button.dataset.open)));
$$('[data-dialog]').forEach(button => button.addEventListener("click", () => openDialog(button.dataset.dialog)));
refs.dataForm.addEventListener("submit", event => { if (event.submitter?.value === "cancel") return; event.preventDefault(); saveDialog(); });
refs.resultFile.addEventListener("change", () => upload(refs.resultFile.files[0]));
refs.resultFilePage.addEventListener("change", () => upload(refs.resultFilePage.files[0]));
refs.resultList?.addEventListener("click", event => { const button = event.target.closest("[data-open-original]"); if (button) openOriginalPreview(button.dataset.openOriginal); });
refs.closeOriginalPreview?.addEventListener("click", () => refs.originalPreviewDialog.close());
refs.runCheck.addEventListener("click", async () => { refs.agentStatus.textContent = tr("app.reviewing"); const out = await api("/api/demo/tick", {method:"POST"}); await refresh(); refs.agentStatus.textContent = tr("app.ready"); showToast(out.created ? `${out.created} ${tr("app.new_count")}.` : tr("app.no_new")); });
function syncLeftToggle() {
  const collapsed = refs.shell.classList.contains("left-collapsed");
  refs.expandLeft?.setAttribute("aria-hidden", String(!collapsed));
  $("#collapseLeft")?.setAttribute("aria-label", collapsed ? tr("nav.expand") : tr("nav.collapse"));
}
$("#collapseLeft").addEventListener("click", () => { refs.shell.classList.toggle("left-collapsed"); syncLeftToggle(); });
refs.expandLeft?.addEventListener("click", () => { refs.shell.classList.remove("left-collapsed"); syncLeftToggle(); });
function syncContextToggle() {
  if (!refs.closeContext) return;
  const open = window.innerWidth <= 1080 ? refs.shell.classList.contains("context-open") : !refs.shell.classList.contains("right-collapsed");
  refs.closeContext.textContent = open ? "›" : "‹";
  refs.closeContext.setAttribute("aria-label", tr("top.context"));
}
$("#collapseRight").addEventListener("click", () => { if (window.innerWidth <= 1080) refs.shell.classList.toggle("context-open"); else refs.shell.classList.toggle("right-collapsed"); syncContextToggle(); });
$("#closeContext").addEventListener("click", () => { if (window.innerWidth <= 1080) refs.shell.classList.toggle("context-open"); else refs.shell.classList.toggle("right-collapsed"); syncContextToggle(); });
$("#mobileMenu").addEventListener("click", () => refs.shell.classList.toggle("menu-open"));
refs.newConsultation?.addEventListener("click", async event => {
  event.preventDefault(); refs.newConsultation.disabled = true;
  try { await api("/api/consultations/new", {method:"POST"}); await refresh(true); setView("chat"); refs.chatInput.value = ""; refs.chatInput.style.height = "auto"; setSendState(); safeFocusComposer(); showToast(tr("app.new_consult")); }
  catch (error) { showToast(error.message); }
  finally { refs.newConsultation.disabled = false; }
});

document.addEventListener("healthia:locale-changed", () => { if (state.data) renderAll(); syncLeftToggle(); syncContextToggle(); });

(async function boot() {
  try {
    const readiness = await api("/api/readiness");
    const connected = readiness.llm_backend === "gemini_api" && readiness.ai_ready;
    refs.runtimeLabel.dataset.runtimeBackend = readiness.llm_backend || "unknown";
    refs.runtimeLabel.dataset.runtimeModel = readiness.model || "";
    refs.runtimeLabel.textContent = connected
      ? (i18n?.locale === "es" ? "Continuidad conectada" : "Continuity connected")
      : readiness.llm_backend === "gemini_api"
        ? (i18n?.locale === "es" ? "Continuidad limitada" : "Continuity limited")
        : tr("app.local");
    setSendState(); syncLeftToggle(); syncContextToggle(); await refresh(); connectEvents();
  } catch (error) { showToast(error.message); }
})();

}
