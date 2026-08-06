if (!window.__HEALTHIA_PRIVACY_CONTROLS__) {
  window.__HEALTHIA_PRIVACY_CONTROLS__ = true;
(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  const SIGNALS = [
    ["vitals", "Signos vitales", "Presión, pulso, oxígeno y temperatura"],
    ["weight", "Peso", "Tendencias y registros pendientes"],
    ["activity", "Actividad", "Pasos, minutos y barreras"],
    ["results", "Resultados", "Archivos pendientes de explicación"],
    ["family_history", "Historia familiar", "Genograma y patrones autorizados"],
    ["documents", "Documentos", "Archivo clínico organizado"],
    ["medications", "Tratamiento", "Tomas reportadas y omisiones"],
    ["appointments", "Citas", "Preparación y documentación"],
    ["missions", "Misiones", "Seguimiento hasta un próximo paso"],
  ];
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
    if (!value) return "";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat("es-DO", {dateStyle:"short",timeStyle:"short"}).format(date);
  }

  function activateView(view) {
    $$(".view").forEach(node => node.classList.toggle("is-active", node.id === `view-${view}`));
    $$('.main-nav [data-open]').forEach(node => node.classList.toggle("is-active", node.dataset.open === view));
    refresh().catch(error => toast(error.message));
  }

  function injectNavigation() {
    const nav = $(".main-nav");
    const missions = nav?.querySelector('[data-open="missions"]');
    if (!nav || !missions || nav.querySelector('[data-open="control"]')) return;
    const button = document.createElement("button");
    button.dataset.open = "control";
    button.innerHTML = "<span>◈</span><b>Permisos y privacidad</b>";
    button.addEventListener("click", () => activateView("control"));
    nav.insertBefore(button, missions);
  }

  function injectQuickAction() {
    const quick = $(".quick-records");
    if (!quick || quick.querySelector('[data-control-shortcut]')) return;
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.controlShortcut = "true";
    button.textContent = "◈ Permisos";
    button.addEventListener("click", () => activateView("control"));
    quick.append(button);
  }

  function injectView() {
    const main = $(".conversation-column");
    if (!main || $("#view-control")) return;
    const section = document.createElement("section");
    section.id = "view-control";
    section.className = "view";
    section.innerHTML = `<div class="page-body"><div class="page-kicker">BASTION · CONTROL DEL PACIENTE</div><h1>Permisos y privacidad</h1><p>Decide qué puede vigilar HealthIA, cuándo puede intervenir y qué queda registrado.</p><div id="controlRoot"></div></div>`;
    main.append(section);
  }

  function renderControl() {
    const root = $("#controlRoot");
    if (!root || !snapshot) return;
    const consent = snapshot.consent;
    const auditEvents = snapshot.audit_summary?.latest || [];
    const snoozed = consent.snoozed_until && new Date(consent.snoozed_until) > new Date();
    root.innerHTML = `<div class="control-layout">
      <section class="control-hero"><div><small>CONTROL REVERSIBLE</small><h2>Tú decides qué observa el equipo</h2><p>Los permisos se aplican antes de la intervención proactiva. Cambiarlos no elimina tus datos; cambia qué señales pueden activar seguimiento.</p></div><span class="control-state">${consent.proactive_enabled ? "Seguimiento activo" : "Seguimiento pausado"}</span></section>
      ${snoozed ? `<div class="snooze-banner">Intervenciones no urgentes pausadas hasta ${formatDate(consent.snoozed_until)}.</div>` : ""}
      <div class="control-grid">
        <section class="control-card"><h3>Seguimiento proactivo</h3><p>HealthIA puede adelantarse únicamente con las clases autorizadas.</p><div class="toggle-row"><div><strong>Permitir intervenciones proactivas</strong><small>El chat solicitado sigue disponible.</small></div><label class="toggle"><input id="proactiveEnabled" type="checkbox" ${consent.proactive_enabled ? "checked" : ""}><span></span></label></div><div class="toggle-row"><div><strong>Excepción de seguridad urgente</strong><small>Alertas deterministas urgentes durante silencio o pausa.</small></div><label class="toggle"><input id="urgentBypass" type="checkbox" ${consent.allow_urgent_safety_bypass ? "checked" : ""}><span></span></label></div></section>
        <section class="control-card"><h3>Horario de silencio</h3><p>Las intervenciones no urgentes esperan fuera de esta ventana.</p><div class="quiet-grid"><label>Desde<input id="quietStart" type="time" value="${escapeHtml(consent.quiet_hours_start)}"></label><label>Hasta<input id="quietEnd" type="time" value="${escapeHtml(consent.quiet_hours_end)}"></label></div><div class="control-actions"><button id="snooze24">Pausar 24 horas</button><button id="saveConsent" class="primary">Guardar cambios</button></div></section>
        <section class="control-card wide"><h3>Señales autorizadas</h3><p>Puedes activar o desactivar cada clase de seguimiento.</p>${SIGNALS.map(([key,label,description]) => `<div class="toggle-row"><div><strong>${label}</strong><small>${description}</small></div><label class="toggle"><input type="checkbox" data-signal="${key}" ${consent.signal_types.includes(key) ? "checked" : ""}><span></span></label></div>`).join("")}</section>
        <section class="control-card"><h3>Reglas silenciadas</h3><p>Dejan de producir nuevas intervenciones hasta que las reactives.</p><div class="muted-list">${consent.muted_rule_prefixes.length ? consent.muted_rule_prefixes.map(prefix => `<button data-unmute="${escapeHtml(prefix)}">${escapeHtml(prefix)} ×</button>`).join("") : "<span>Ninguna</span>"}</div></section>
        <section class="control-card"><h3>Tus datos</h3><p>Exporta datos estructurados y metadatos; no incluye archivos binarios.</p><div class="control-actions"><a class="primary" href="/api/export" download>Exportar JSON</a><button id="refreshAudit">Actualizar auditoría</button></div></section>
        <section class="control-card wide"><h3>Registro auditable</h3><p>${snapshot.audit_summary?.count || 0} acciones. No incluye razonamiento privado.</p><div class="audit-list">${auditEvents.slice().reverse().map(event => `<article class="audit-event"><div class="audit-icon">${event.outcome === "blocked" ? "!" : "✓"}</div><div><strong>${escapeHtml(event.action)}</strong><small>${escapeHtml(event.actor)} · ${escapeHtml(event.resource_type)}${event.resource_id ? ` · ${escapeHtml(event.resource_id)}` : ""}</small></div><time>${formatDate(event.created_at)}</time></article>`).join("") || "<p>Sin eventos.</p>"}</div></section>
      </div>
    </div>`;
    bindControlActions();
  }

  async function saveConsent() {
    const payload = {
      ...snapshot.consent,
      proactive_enabled: $("#proactiveEnabled").checked,
      allow_urgent_safety_bypass: $("#urgentBypass").checked,
      quiet_hours_start: $("#quietStart").value,
      quiet_hours_end: $("#quietEnd").value,
      signal_types: $$('[data-signal]:checked').map(input => input.dataset.signal),
      updated_at: new Date().toISOString(),
    };
    try {
      await api("/api/consent", {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      await refresh(); toast("Permisos actualizados.");
    } catch (error) { toast(error.message); }
  }

  async function updateMuted(prefixes, message) {
    const payload = {...snapshot.consent, muted_rule_prefixes:prefixes, updated_at:new Date().toISOString()};
    try {
      await api("/api/consent", {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      await refresh(); toast(message);
    } catch (error) { toast(error.message); }
  }

  function bindControlActions() {
    $("#saveConsent")?.addEventListener("click", saveConsent);
    $("#snooze24")?.addEventListener("click", async () => {
      try { await api("/api/consent/snooze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({hours:24})}); await refresh(); toast("Intervenciones pausadas por 24 horas."); }
      catch (error) { toast(error.message); }
    });
    $("#refreshAudit")?.addEventListener("click", () => refresh().catch(error => toast(error.message)));
    $$('[data-unmute]').forEach(button => button.addEventListener("click", () => updateMuted(snapshot.consent.muted_rule_prefixes.filter(item => item !== button.dataset.unmute), "Regla reactivada.")));
  }

  async function muteRule(ruleKey) {
    const prefix = `${String(ruleKey).split(":")[0]}:`;
    try {
      await api("/api/consent/mute", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prefix})});
      await refresh(); toast(`Silenciadas las intervenciones ${prefix}`);
    } catch (error) { toast(error.message); }
  }

  function hydrateMessageControls() {
    if (!snapshot) return;
    const byId = new Map((snapshot.messages || []).map(item => [item.id,item]));
    $$("#messageList .message").forEach(article => {
      const message = byId.get(article.dataset.id);
      const needsControl = message?.metadata?.action_target === "control";
      const ruleKey = message?.metadata?.proactive ? message.metadata.rule_key : null;
      const needsMute = Boolean(ruleKey);
      if (!needsControl && !needsMute) return;
      let bar = article.querySelector(".message-actions");
      if (!bar) {
        bar = document.createElement("div");
        bar.className = "message-actions";
        article.querySelector(".message-content")?.append(bar);
      }
      if (needsControl && !bar.querySelector(".open-control-button")) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "open-control-button";
        button.textContent = "Abrir permisos y privacidad";
        button.addEventListener("click", () => activateView("control"));
        bar.append(button);
      }
      if (needsMute && !bar.querySelector(".mute-rule-button")) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "mute-rule-button";
        button.textContent = "Silenciar este tipo";
        button.addEventListener("click", () => muteRule(ruleKey));
        bar.append(button);
      }
    });
  }

  async function refresh() {
    snapshot = await api("/api/bootstrap");
    renderControl();
    hydrateMessageControls();
  }

  window.addEventListener("DOMContentLoaded", () => {
    injectNavigation(); injectQuickAction(); injectView();
    const list = $("#messageList");
    if (list) new MutationObserver(hydrateMessageControls).observe(list, {childList:true,subtree:true});
    refresh().catch(error => toast(error.message));
  });
})();

}
