(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const i18n = window.HealthIAI18n;
  const text = (en, es) => i18n?.locale === "es" ? es : en;
  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  const localeTag = () => i18n?.browserLocaleTag?.() || "en-US";
  const label = value => String(value || "").replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());

  let latestData = null;
  const googleMissionCache = new Map();
  const googleMissionLoads = new Map();

  const refs = {
    pulse: $("#livingPulse"), pulseTitle: $("#livingPulseTitle"), pulseCopy: $("#livingPulseCopy"), pulseStatus: $("#livingPulseStatus"),
    pulseTwin: $("#livingPulseTwin"), pulseMissions: $("#livingPulseMissions"), pulseDecisions: $("#livingPulseDecisions"),
    surface: $("#view-living .living-surface"), surfaceTitle: $("#livingSurfaceTitle"), surfaceCopy: $("#livingSurfaceCopy"), surfaceStatus: $("#livingSurfaceStatus"),
    twinVersion: $("#livingTwinVersion"), twinMeta: $("#livingTwinMeta"), evidenceCount: $("#livingEvidenceCount"), evidenceMeta: $("#livingEvidenceMeta"),
    missionCount: $("#livingMissionCount"), missionMeta: $("#livingMissionMeta"), decisionCount: $("#livingDecisionCount"), decisionMeta: $("#livingDecisionMeta"),
    twinBadge: $("#livingTwinBadge"), twinSummary: $("#livingTwinSummary"), missionList: $("#livingMissionList"), activityCount: $("#livingActivityCount"),
    activityList: $("#livingActivityList"), decisionBadge: $("#livingDecisionBadge"), decisionQueue: $("#livingDecisionQueue"),
  };

  function dateLabel(value) {
    if (!value) return text("No date", "Sin fecha");
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? text("No date", "Sin fecha") : new Intl.DateTimeFormat(localeTag(), {dateStyle: "medium", timeStyle: "short"}).format(date);
  }

  function statusLabel(value) {
    return label(value).toUpperCase();
  }

  function activeMissions(data) {
    return (data?.missions || []).filter(item => !["completed", "cancelled"].includes(String(item.status || ""))).slice().reverse();
  }

  function googleMissionIds(data) {
    return [...new Set((data?.messages || []).map(message => String(message?.metadata?.google_mission_id || "").trim()).filter(Boolean))];
  }

  function loadGoogleMissions(data) {
    const ids = googleMissionIds(data);
    const pending = ids.filter(id => !googleMissionCache.has(id) && !googleMissionLoads.has(id));
    pending.forEach(id => {
      const request = fetch(`/api/google-constellation/missions/${encodeURIComponent(id)}`, {headers: {Accept: "application/json", "Accept-Language": i18n?.locale || "en"}})
        .then(response => response.ok ? response.json() : null)
        .then(mission => { if (mission) googleMissionCache.set(id, mission); })
        .catch(() => null)
        .finally(() => googleMissionLoads.delete(id));
      googleMissionLoads.set(id, request);
    });
    if (pending.length) Promise.all(pending.map(id => googleMissionLoads.get(id))).then(() => { if (latestData === data) render(data); });
    return ids.map(id => googleMissionCache.get(id)).filter(Boolean);
  }

  function googleMissionDecisions(missions) {
    const decisions = [];
    missions.forEach(mission => {
      const state = String(mission.state || "");
      if (state === "awaiting_authorization" || state === "blocked") {
        decisions.push({key: `google:${mission.id}`, title: mission.title, copy: text("Authorization or review is required before this mission can continue.", "Hace falta autorización o revisión antes de que esta misión continúe."), kind: "google_authorization"});
      } else if (state === "awaiting_selection") {
        decisions.push({key: `google:${mission.id}`, title: mission.title, copy: text("Select one of the verified candidates to continue this mission.", "Selecciona una de las opciones verificadas para continuar esta misión."), kind: "google_selection"});
      }
    });
    return decisions;
  }

  function humanDecisions(data, missions) {
    const decisions = [];
    const push = (key, title, copy, kind) => {
      if (!key || decisions.some(item => item.key === key)) return;
      decisions.push({key, title: String(title || text("Human checkpoint", "Punto de revisión humana")), copy: String(copy || ""), kind});
    };
    missions.forEach(mission => {
      const status = String(mission.status || "");
      if (["waiting_patient", "waiting_professional"].includes(status)) {
        push(`mission:${mission.id}`, mission.title, mission.next_action, status === "waiting_professional" ? "professional" : "patient");
      }
      (mission.agent_plan || []).filter(step => step.status === "blocked").forEach((step, index) => {
        push(`agent:${mission.id}:${index}`, mission.title, step.action, "blocked");
      });
    });
    (data?.documents || []).filter(item => item.status === "pending_review").forEach(document => {
      push(`document:${document.id}`, document.title || document.filename, text("Original evidence needs review before it becomes a confirmed record.", "La evidencia original necesita revisión antes de convertirse en un registro confirmado."), "evidence");
    });
    ((data?.clinical_twin?.obligations || [])).filter(item => item.status === "waiting").forEach(obligation => {
      push(`obligation:${obligation.id}`, text("Open health obligation", "Obligación de salud abierta"), obligation.required_action, "obligation");
    });
    return decisions;
  }

  function renderPulse(data, missions, decisions, twin, googleMissions) {
    if (!refs.pulse) return;
    refs.pulse.hidden = false;
    const version = Number(twin?.version || 0);
    refs.pulseTitle.textContent = version
      ? text("Your health story is connected", "Tu historia de salud está conectada")
      : text("HealthIA is ready to carry your story forward", "HealthIA está lista para dar continuidad a tu historia");
    refs.pulseCopy.textContent = text("HealthIA is watching only the signals you authorized and keeping every next step traceable.", "HealthIA observa solo las señales que autorizaste y mantiene trazable cada siguiente paso.");
    refs.pulseStatus.innerHTML = `<i aria-hidden="true"></i> ${escapeHtml(text("Synced from your record", "Sincronizado desde tu expediente"))}`;
    refs.pulseTwin.textContent = `v${version}`;
    const googleActive = (googleMissions || []).filter(item => !["completed", "failed"].includes(String(item.state || "")));
    refs.pulseMissions.textContent = String(missions.length + googleActive.length);
    refs.pulseDecisions.textContent = String(decisions.length);
  }

  function renderTwin(data, twin) {
    if (!refs.surface || !refs.twinSummary) return;
    const version = Number(twin?.version || 0);
    const counts = twin?.counts || {};
    const physiology = twin?.physiology || {};
    const vital = physiology.latest_vital;
    const weight = physiology.latest_weight;
    const activity = physiology.latest_activity;
    const signals = twin?.consent_scope?.signal_types || data?.profile?.authorized_signals || [];
    const conditionList = (twin?.conditions || []).slice(0, 3);
    const evidenceIds = new Set([
      ...(twin?.evidence_refs || []),
      ...Object.values(twin?.observations || {}).flat(),
      ...(twin?.result_nodes || []).flatMap(item => [item.result_id, item.document_id]),
    ].filter(Boolean).map(String));
    const evidence = evidenceIds.size;
    refs.twinVersion.textContent = `v${version}`;
    refs.twinMeta.textContent = version ? text(`${signals.length} authorized signal${signals.length === 1 ? "" : "s"} · canonical record`, `${signals.length} señal${signals.length === 1 ? "" : "es"} autorizada${signals.length === 1 ? "" : "s"} · expediente canónico`) : text("Building from authorized record", "Construyendo desde el expediente autorizado");
    refs.evidenceCount.textContent = String(evidence);
    refs.evidenceMeta.textContent = text("Persisted references", "Referencias persistidas");
    refs.twinBadge.textContent = version ? text("CONNECTED", "CONECTADO") : text("READY", "LISTO");
    refs.twinSummary.innerHTML = `
      <div class="living-twin-line"><span>${escapeHtml(text("Confirmed context", "Contexto confirmado"))}</span><strong>${escapeHtml(conditionList.length ? conditionList.join(" · ") : text("No confirmed conditions recorded", "No hay condiciones confirmadas registradas"))}</strong></div>
      <div class="living-twin-observations">
        <div><span>${escapeHtml(text("Latest vital", "Último signo"))}</span><strong>${vital ? `${escapeHtml(vital.systolic || "—")}/${escapeHtml(vital.diastolic || "—")}` : "—"}</strong><small>${vital ? escapeHtml(text("Blood pressure", "Presión arterial")) : escapeHtml(text("Awaiting a record", "Esperando un registro"))}</small></div>
        <div><span>${escapeHtml(text("Latest weight", "Último peso"))}</span><strong>${weight ? `${escapeHtml(Number(weight.weight_kg).toFixed(1))} kg` : "—"}</strong><small>${weight ? escapeHtml(text("Patient record", "Registro del paciente")) : escapeHtml(text("Awaiting a record", "Esperando un registro"))}</small></div>
        <div><span>${escapeHtml(text("Latest activity", "Última actividad"))}</span><strong>${activity ? Number(activity.steps || 0).toLocaleString(localeTag()) : "—"}</strong><small>${activity ? escapeHtml(text("steps", "pasos")) : escapeHtml(text("Awaiting a record", "Esperando un registro"))}</small></div>
      </div>
      <div class="living-twin-foot"><span>${escapeHtml(text("Organ systems", "Sistemas orgánicos"))}: <strong>${escapeHtml(String(counts.organ_system_states || 0))}</strong></span><span>${escapeHtml(text("Deviations tracked", "Desviaciones seguidas"))}: <strong>${escapeHtml(String(counts.deviations || 0))}</strong></span></div>`;
  }

  function renderMissions(missions, decisions, googleMissions) {
    if (!refs.missionList) return;
    const googleActive = googleMissions.filter(item => !["completed", "failed"].includes(String(item.state || "")));
    refs.missionCount.textContent = String(missions.length + googleActive.length);
    refs.missionMeta.textContent = missions.length || googleActive.length ? text("Follow-up threads", "Hilos de seguimiento") : text("No open threads", "No hay hilos abiertos");
    if (!missions.length && !googleActive.length) {
      refs.missionList.innerHTML = `<p class="living-empty">${escapeHtml(text("No active mission. HealthIA will open one only when your record and policy require a next step.", "No hay misiones activas. HealthIA abrirá una solo cuando tu expediente y la política indiquen un siguiente paso."))}</p>`;
      return;
    }
    const localRows = missions.slice(0, 3).map(mission => {
      const plan = mission.agent_plan || [];
      const completed = plan.filter(item => item.status === "completed").length;
      const waiting = decisions.some(item => item.key === `mission:${mission.id}`);
      return `<article class="living-mission-item ${waiting ? "is-waiting" : ""}"><div class="living-mission-head"><strong>${escapeHtml(mission.title)}</strong><span>${escapeHtml(statusLabel(mission.status))}</span></div><p>${escapeHtml(mission.next_action)}</p><small>${escapeHtml(`${completed}/${plan.length || 0} ${text("agent steps complete", "pasos de agentes completados")}`)} · ${escapeHtml(String(mission.evidence_ids?.length || 0))} ${escapeHtml(text("evidence refs", "referencias"))}</small></article>`;
    });
    const googleRows = googleActive.slice(0, 3).map(mission => {
      const waiting = ["awaiting_authorization", "awaiting_selection", "blocked"].includes(String(mission.state || ""));
      const publicEvent = (mission.public_events || []).at(-1);
      const next = waiting
        ? (mission.state === "awaiting_selection" ? text("Selection is needed to continue.", "Hace falta una selección para continuar.") : text("Authorization is needed before any external action.", "Hace falta autorización antes de cualquier acción externa."))
        : (publicEvent?.summary || text("Mission is progressing through its authorized workflow.", "La misión avanza por su flujo autorizado."));
      return `<article class="living-mission-item ${waiting ? "is-waiting" : ""}"><div class="living-mission-head"><strong>${escapeHtml(mission.title || text("Google health mission", "Misión de salud Google"))}</strong><span>${escapeHtml(statusLabel(mission.state))}</span></div><p>${escapeHtml(next)}</p><small>${escapeHtml(text("Patient-scoped Google mission", "Misión Google vinculada al paciente"))} · ${escapeHtml(String((mission.public_events || []).length))} ${escapeHtml(text("public steps", "pasos públicos"))}</small></article>`;
    });
    refs.missionList.innerHTML = [...localRows, ...googleRows].join("");
  }

  function renderActivity(data, googleMissions) {
    if (!refs.activityList) return;
    const audit = (data?.audit_summary?.latest || []).slice().reverse();
    const googleEvents = googleMissions.flatMap(mission => (mission.public_events || []).map(event => ({created_at: event.at, action: event.summary, resource_type: "Google mission", outcome: "success"})));
    const activity = [...audit.map(item => ({...item, source: "audit"})), ...googleEvents.map(item => ({...item, source: "google"}))].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    const total = activity.length;
    refs.activityCount.textContent = `${total} ${text(total === 1 ? "recorded step" : "recorded steps", total === 1 ? "paso registrado" : "pasos registrados")}`;
    if (!activity.length) {
      refs.activityList.innerHTML = `<li class="living-empty">${escapeHtml(text("No durable receipts yet. Activity appears here when HealthIA records a patient-authorized step.", "Aún no hay comprobantes duraderos. La actividad aparecerá cuando HealthIA registre un paso autorizado por el paciente."))}</li>`;
      return;
    }
    refs.activityList.innerHTML = activity.slice(0, 4).map(item => `<li><span class="living-activity-node ${item.outcome === "success" ? "is-success" : "is-watch"}" aria-hidden="true"></span><div><strong>${escapeHtml(label(item.action))}</strong><small>HealthIA · ${escapeHtml(label(item.resource_type))}</small></div><time datetime="${escapeHtml(item.created_at)}">${escapeHtml(dateLabel(item.created_at))}</time></li>`).join("");
  }

  function renderDecisions(decisions) {
    if (!refs.decisionQueue) return;
    refs.decisionCount.textContent = String(decisions.length);
    refs.decisionMeta.textContent = decisions.length ? text("Waiting for review", "Esperando revisión") : text("No review requested", "No se requiere revisión");
    refs.decisionBadge.textContent = decisions.length ? text("YOUR INPUT", "TU DECISIÓN") : text("CLEAR", "DESPEJADO");
    refs.decisionBadge.classList.toggle("living-card-state-attention", decisions.length > 0);
    refs.decisionBadge.classList.toggle("living-card-state-muted", decisions.length === 0);
    refs.decisionQueue.innerHTML = decisions.length
      ? decisions.slice(0, 3).map(item => `<article><span class="living-decision-icon" aria-hidden="true">${item.kind === "professional" ? "◫" : "◆"}</span><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.copy)}</p><small>${escapeHtml(item.kind === "professional" ? text("Professional review", "Revisión profesional") : item.kind === "evidence" ? text("Evidence review", "Revisión de evidencia") : text("Patient checkpoint", "Punto del paciente"))}</small></div></article>`).join("")
      : `<p class="living-empty">${escapeHtml(text("No human decision is being requested. When one is needed, HealthIA will stop and show the next action here.", "No se solicita una decisión humana. Cuando haga falta, HealthIA se detendrá y mostrará aquí el siguiente paso."))}</p>`;
  }

  function setStaticCopy(data) {
    const es = i18n?.locale === "es";
    const set = (selector, value) => { const node = $(selector); if (node) node.textContent = value; };
    set("#livingNavButton b", es ? "Sistema vivo" : "Living System");
    document.querySelectorAll(".living-surface-kicker").forEach(node => { node.textContent = es ? "MOTOR DE CONTINUIDAD" : "CONTINUITY ENGINE"; });
    set("#livingOpenView", es ? "Abrir sistema vivo" : "Open Living System");
    set("#livingOpenMissions", es ? "Ver misiones" : "View missions");
    set("#view-living .living-twin-card .living-card-kicker", es ? "GEMELO DEL PACIENTE" : "PATIENT TWIN");
    set("#view-living .living-mission-card .living-card-kicker", es ? "ORQUESTACIÓN DE MISIONES" : "MISSION ORCHESTRATION");
    set("#view-living .living-activity-card .living-card-kicker", es ? "ACTIVIDAD AUTÓNOMA" : "AUTONOMOUS ACTIVITY");
    set("#view-living .living-decision-card .living-card-kicker", es ? "PUNTO HUMANO" : "HUMAN CHECKPOINT");
    set("#view-living .living-twin-card h2", es ? "Continuidad con procedencia" : "Continuity with provenance");
    set("#view-living .living-mission-card h2", es ? "Trabajo que permanece abierto" : "Work that stays open");
    set("#view-living .living-activity-card h2", es ? "Lo que HealthIA registró" : "What HealthIA recorded");
    set("#view-living .living-decision-card h2", es ? "Las decisiones siguen siendo tuyas" : "Decisions that stay yours");
    const metricLabels = es ? ["Gemelo del paciente", "Evidencia vinculada", "Misiones activas", "Decisiones humanas"] : ["Patient Twin", "Evidence linked", "Active missions", "Human decisions"];
    const metricMeta = es ? ["Expediente canónico", "Referencias persistidas", "Hilos de seguimiento", "Esperando revisión"] : ["Canonical record", "Persisted references", "Follow-up threads", "Waiting for review"];
    document.querySelectorAll("#view-living .living-metric").forEach((node, index) => { if (node.children[0]) node.children[0].textContent = metricLabels[index]; if (node.children[2]) node.children[2].textContent = metricMeta[index]; });
    const pulseLabels = es ? ["Gemelo del paciente", "Misiones activas", "Decisiones humanas"] : ["Patient Twin", "Active missions", "Human decisions"];
    document.querySelectorAll("#livingPulse .living-pulse-metrics span").forEach((node, index) => { node.textContent = pulseLabels[index]; });
    set("#view-living .living-surface-boundary", es ? "⌁ HealthIA organiza evidencia autorizada y guía el seguimiento. No diagnostica, prescribe ni cambia tratamientos silenciosamente." : "⌁ HealthIA organizes authorized evidence and guides follow-up. It does not diagnose, prescribe or silently change treatment.");
    set("#view-living .living-surface-header h1", es ? "HealthIA está dando continuidad a tu historia" : "HealthIA is carrying your story forward");
    set("#view-living .living-surface-header p", es ? "Tu expediente autorizado, las misiones activas y las próximas decisiones permanecen conectadas aquí." : "Your authorized record, active missions and next decisions stay connected here.");
    void data;
  }

  function render(data) {
    if (!data) return;
    latestData = data;
    const twin = data.clinical_twin || {};
    const missions = activeMissions(data);
    const googleMissions = loadGoogleMissions(data);
    const decisions = [...humanDecisions(data, missions), ...googleMissionDecisions(googleMissions)];
    setStaticCopy(data);
    renderPulse(data, missions, decisions, twin, googleMissions);
    if (refs.surface) refs.surface.hidden = false;
    if (refs.surfaceTitle) refs.surfaceTitle.textContent = text("HealthIA is carrying your story forward", "HealthIA está dando continuidad a tu historia");
    if (refs.surfaceCopy) refs.surfaceCopy.textContent = text("Your authorized record, active missions and next decisions stay connected here.", "Tu expediente autorizado, las misiones activas y las próximas decisiones permanecen conectadas aquí.");
    if (refs.surfaceStatus) refs.surfaceStatus.innerHTML = `<i aria-hidden="true"></i> ${escapeHtml(text("Synced from your record", "Sincronizado desde tu expediente"))}`;
    renderTwin(data, twin);
    renderMissions(missions, decisions, googleMissions);
    renderActivity(data, googleMissions);
    renderDecisions(decisions);
  }

  function openView(view) {
    const button = document.querySelector(`[data-open="${view}"]`);
    if (button) button.click();
  }

  $("#livingOpenView")?.addEventListener("click", () => openView("living"));
  $("#livingOpenMissions")?.addEventListener("click", () => openView("missions"));
  document.addEventListener("healthia:state-updated", event => render(event.detail?.data));
  document.addEventListener("healthia:locale-changed", () => { if (latestData) render(latestData); });
})();
