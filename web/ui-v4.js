(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  let snapshot = null;

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let detail = `Error ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return response.json();
  }

  function toast(message) {
    const node = $("#toast");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
    setTimeout(() => { node.hidden = true; }, 3000);
  }

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "sin fecha" : new Intl.DateTimeFormat("es-DO", {dateStyle:"medium", timeStyle:"short"}).format(date);
  }

  function activateView(view) {
    $$(".view").forEach(node => node.classList.toggle("is-active", node.id === `view-${view}`));
    $$('.main-nav [data-open]').forEach(node => node.classList.toggle("is-active", node.dataset.open === view));
    refresh().catch(error => toast(error.message));
  }

  function injectNavigation() {
    const nav = $(".main-nav");
    const missions = nav?.querySelector('[data-open="missions"]');
    if (!nav || !missions || nav.querySelector('[data-open="timeline"]')) return;
    const items = [
      ["timeline", "⌁", "Línea de salud"],
      ["treatment", "✚", "Tratamiento"],
      ["appointments", "◫", "Citas y consulta"],
    ];
    items.forEach(([view, icon, label]) => {
      const button = document.createElement("button");
      button.dataset.open = view;
      button.innerHTML = `<span>${icon}</span><b>${label}</b>`;
      button.addEventListener("click", () => activateView(view));
      nav.insertBefore(button, missions);
    });
  }

  function injectQuickActions() {
    const quick = $(".quick-records");
    if (!quick || quick.querySelector('[data-continuity="timeline"]')) return;
    [["timeline","⌁ Historia"],["treatment","✚ Toma"],["appointments","◫ Cita"]].forEach(([target,label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.continuity = target;
      button.textContent = label;
      button.addEventListener("click", () => activateView(target));
      quick.append(button);
    });
  }

  function injectViews() {
    const main = $(".conversation-column");
    if (!main || $("#view-timeline")) return;
    const definitions = [
      ["timeline", "HISTORIA · CONTINUIDAD", "Línea de salud", "Todos tus eventos en una cronología con procedencia.", "timelineRoot"],
      ["treatment", "MEDSAFE · SEGURIDAD", "Tratamiento y tomas", "Registro del esquema indicado y adherencia informada por el paciente.", "treatmentRoot"],
      ["appointments", "ADVOCATE · PREPARACIÓN", "Citas y consulta", "Prepara cambios, documentos, objetivos y preguntas sin empezar desde cero.", "appointmentsRoot"],
    ];
    definitions.forEach(([id,kicker,title,copy,root]) => {
      const section = document.createElement("section");
      section.id = `view-${id}`;
      section.className = "view";
      section.innerHTML = `<div class="page-body"><div class="page-kicker">${kicker}</div><h1>${title}</h1><p>${copy}</p><div id="${root}"></div></div>`;
      main.append(section);
    });
  }

  function injectDialog() {
    if ($("#appointmentDialog")) return;
    document.body.insertAdjacentHTML("beforeend", `
      <dialog id="appointmentDialog" class="health-os-dialog"><form id="appointmentForm" class="health-os-form">
        <header><div><small>CITA DEL PACIENTE</small><h2>Añadir cita</h2></div><button type="button" data-v4-close>×</button></header>
        <div class="health-os-fields">
          <label>Título<input name="title" required placeholder="Consulta de medicina familiar"></label>
          <label>Especialidad<input name="specialty" placeholder="Medicina familiar"></label>
          <label>Fecha y hora<input name="scheduled_at" type="datetime-local" required></label>
          <label>Lugar<input name="location" placeholder="Centro o videollamada"></label>
          <label class="wide">Documentos separados por coma<input name="required_documents" placeholder="Resultados recientes, lista de medicamentos"></label>
          <label class="wide">Preguntas separadas por coma<textarea name="questions" rows="2"></textarea></label>
        </div><footer><button type="button" data-v4-close>Cancelar</button><button type="submit">Guardar cita</button></footer>
      </form></dialog>`);
    $$('[data-v4-close]').forEach(button => button.addEventListener("click", () => $("#appointmentDialog")?.close()));
  }

  function renderTimeline() {
    const root = $("#timelineRoot");
    if (!root || !snapshot) return;
    const events = snapshot.timeline || [];
    const packs = snapshot.condition_packs || [];
    root.innerHTML = `<div class="continuity-layout"><div class="condition-pack-grid">${packs.map(pack => `<article class="condition-pack"><h3>${escapeHtml(pack.label)}</h3><p>${pack.signals.map(escapeHtml).join(" · ")}</p><ul>${pack.questions.map(question => `<li>${escapeHtml(question)}</li>`).join("")}</ul></article>`).join("")}</div><div class="timeline-list">${events.length ? events.map(event => `<article class="timeline-event"><div><h3>${escapeHtml(event.title)}</h3><p>${escapeHtml(event.detail)} · ${escapeHtml(event.source)}</p></div><small>${formatDate(event.occurred_at)}</small></article>`).join("") : '<article class="timeline-event"><div><h3>Sin eventos</h3><p>Registra una medición o carga un documento.</p></div></article>'}</div></div>`;
  }

  function renderTreatment() {
    const root = $("#treatmentRoot");
    if (!root || !snapshot) return;
    const summary = snapshot.medication_summary || {active_plans:[],counts:{},reported_adherence_percent:null};
    const adherence = summary.reported_adherence_percent;
    root.innerHTML = `<div class="continuity-layout"><div class="continuity-toolbar"><div><strong>Tratamiento registrado</strong><p>No se modifica desde HealthIA.</p></div></div><div class="treatment-grid">${summary.active_plans.length ? summary.active_plans.map(plan => `<article class="treatment-card"><header><h3>${escapeHtml(plan.name)} ${escapeHtml(plan.strength)}</h3><span class="health-status">activo</span></header><p>${escapeHtml(plan.schedule)} · ${escapeHtml(plan.purpose || "propósito no registrado")}</p><small>${escapeHtml(plan.instructions || "Seguir indicación profesional")}</small><div class="treatment-actions"><button data-dose="taken" data-medication="${plan.id}">Tomada</button><button data-dose="late" data-medication="${plan.id}">Tarde</button><button data-dose="skipped" data-medication="${plan.id}">Omitida</button></div></article>`).join("") : '<article class="treatment-card"><h3>Sin tratamiento estructurado</h3><p>Registra exactamente lo indicado por tu profesional.</p></article>'}</div><article class="brief-card"><h3>Adherencia informada</h3><p>${adherence == null ? "Aún no hay suficientes registros." : `${adherence.toFixed(1)}% según las tomas registradas.`}</p><div class="adherence-meter"><span style="width:${adherence || 0}%"></span></div><p>Este porcentaje no demuestra absorción ni autoriza cambios de dosis.</p></article></div>`;
    $$('[data-dose]', root).forEach(button => button.addEventListener("click", () => recordDose(button.dataset.medication, button.dataset.dose)));
  }

  async function recordDose(medicationId, status) {
    try {
      await api("/api/treatment/checkins", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({medication_id:medicationId,status})});
      await refresh(); toast("Toma registrada sin modificar el tratamiento.");
    } catch (error) { toast(error.message); }
  }

  function renderAppointments() {
    const root = $("#appointmentsRoot");
    if (!root || !snapshot) return;
    const appointments = snapshot.appointments || [];
    const brief = snapshot.consultation_brief || {};
    root.innerHTML = `<div class="continuity-layout"><div class="continuity-toolbar"><div><strong>Agenda de salud</strong><p>El paciente controla qué comparte.</p></div><button id="addAppointmentButton">＋ Añadir cita</button></div><div class="appointment-grid">${appointments.length ? appointments.map(item => `<article class="appointment-card"><header><h3>${escapeHtml(item.title)}</h3><span class="health-status">${escapeHtml(item.status)}</span></header><p>${formatDate(item.scheduled_at)} · ${escapeHtml(item.location || "lugar no registrado")}</p><small>${escapeHtml(item.specialty || "sin especialidad")}</small></article>`).join("") : '<article class="appointment-card"><h3>Sin citas</h3><p>Añade una para preparar el resumen.</p></article>'}</div>${renderBrief(brief)}</div>`;
    $("#addAppointmentButton")?.addEventListener("click", () => $("#appointmentDialog")?.showModal());
  }

  function renderBrief(brief) {
    if (!brief?.patient) return "";
    return `<section class="brief-hero"><small>RESUMEN CONTROLADO POR EL PACIENTE</small><h2>Preparación de consulta</h2><p>${escapeHtml(brief.truth_boundary || "Revisar antes de compartir")}</p><div class="brief-grid"><article class="brief-card"><h3>Condiciones confirmadas</h3><p>${brief.confirmed_conditions?.map(escapeHtml).join(" · ") || "Sin registros"}</p></article><article class="brief-card"><h3>Documentos requeridos</h3><p>${brief.required_documents?.map(escapeHtml).join(" · ") || "Sin requisitos registrados"}</p></article><article class="brief-card"><h3>Contexto familiar</h3><p>${brief.family_context?.map(escapeHtml).join(" · ") || "Sin patrones agregados"}</p></article><article class="brief-card"><h3>Preguntas prioritarias</h3><ul>${brief.questions?.map(item => `<li>${escapeHtml(item)}</li>`).join("") || "<li>Sin preguntas</li>"}</ul></article></div></section>`;
  }

  async function refresh() {
    snapshot = await api("/api/bootstrap");
    renderTimeline(); renderTreatment(); renderAppointments(); hydrateChatActions();
  }

  function hydrateChatActions() {
    if (!snapshot) return;
    const byId = new Map((snapshot.messages || []).map(item => [item.id,item]));
    $$("#messageList .message").forEach(article => {
      if (article.querySelector(".v4-message-action")) return;
      const target = byId.get(article.dataset.id)?.metadata?.action_target;
      if (!["timeline","treatment","appointments"].includes(target)) return;
      const labels = {timeline:"Abrir línea de salud",treatment:"Abrir tratamiento",appointments:"Preparar consulta"};
      const bar = document.createElement("div");
      bar.className = "message-actions v4-message-action";
      bar.innerHTML = `<button type="button">${labels[target]}</button>`;
      bar.querySelector("button").addEventListener("click", () => activateView(target));
      article.querySelector(".message-content")?.append(bar);
    });
  }

  function bindAppointmentForm() {
    $("#appointmentForm")?.addEventListener("submit", async event => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(event.currentTarget).entries());
      const split = value => String(value || "").split(",").map(item => item.trim()).filter(Boolean);
      const payload = {...values, scheduled_at:new Date(values.scheduled_at).toISOString(), required_documents:split(values.required_documents), questions:split(values.questions)};
      try {
        await api("/api/appointments", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
        event.currentTarget.reset(); $("#appointmentDialog")?.close(); await refresh(); toast("Cita añadida y resumen actualizado.");
      } catch (error) { toast(error.message); }
    });
  }

  window.addEventListener("DOMContentLoaded", () => {
    injectNavigation(); injectQuickActions(); injectViews(); injectDialog(); bindAppointmentForm();
    const list = $("#messageList");
    if (list) new MutationObserver(hydrateChatActions).observe(list, {childList:true,subtree:true});
    refresh().catch(error => toast(error.message));
  });
})();
