(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  let snapshot = null;

  const publicNames = {
    "KIRA Health": "HealthIA",
    "KIRA": "HealthIA",
    "HISTORIA": "Health history",
    "SENTINEL": "Safety monitoring",
    "LUMEN": "Results review",
    "VITA": "Healthy habits",
    "NAVIGATOR": "Follow-up",
    "HEREDITAS": "Family history",
    "ARCHIVUM": "Documents",
    "MEDSAFE": "Medication safety",
    "ADVOCATE": "Visit preparation",
    "BASTION": "Privacy and consent",
  };

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
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.hidden = true; }, 3200);
  }

  function activate(view) {
    $$(".view").forEach(node => node.classList.toggle("is-active", node.id === `view-${view}`));
    $$('.main-nav [data-open]').forEach(node => node.classList.toggle("is-active", node.dataset.open === view));
    if (["profile", "devices"].includes(view)) refresh().catch(error => toast(error.message));
  }

  function addNavigation() {
    const nav = $(".main-nav");
    const record = nav?.querySelector('[data-open="record"]');
    if (!nav || !record || nav.querySelector('[data-open="profile"]')) return;
    const profile = document.createElement("button");
    profile.dataset.open = "profile";
    profile.innerHTML = '<span>◯</span><b>Perfil del paciente</b>';
    const devices = document.createElement("button");
    devices.dataset.open = "devices";
    devices.innerHTML = '<span>⌁</span><b>Dispositivos</b>';
    profile.addEventListener("click", () => activate("profile"));
    devices.addEventListener("click", () => activate("devices"));
    nav.insertBefore(profile, record);
    nav.insertBefore(devices, record);
  }

  function addViews() {
    const main = $(".conversation-column");
    if (!main || $("#view-profile")) return;
    const profile = document.createElement("section");
    profile.id = "view-profile";
    profile.className = "view";
    profile.innerHTML = `<div class="page-body profile-page"><div class="page-kicker">PATIENT PROFILE</div><h1>Perfil integral</h1><p>Datos generales, antecedentes, hábitos, medicación, salud reproductiva y resumen vital.</p><div id="profileRoot"></div></div>`;
    const devices = document.createElement("section");
    devices.id = "view-devices";
    devices.className = "view";
    devices.innerHTML = `<div class="page-body device-page"><div class="page-kicker">ANDROID HEALTH</div><h1>Dispositivos y Health Connect</h1><p>Sincronización autorizada desde reloj, teléfono, báscula y aplicaciones compatibles.</p><div id="deviceRoot"></div></div>`;
    main.append(profile, devices);
  }

  function addDialogs() {
    if ($("#profileDialog")) return;
    document.body.insertAdjacentHTML("beforeend", `
      <dialog id="profileDialog" class="health-os-dialog"><form id="profileForm" class="health-os-form">
        <header><div><small>PERFIL DEL PACIENTE</small><h2>Actualizar perfil</h2></div><button type="button" data-close-profile>×</button></header>
        <div class="profile-form-grid">
          <label>Nombre<input name="display_name" required></label>
          <label>Fecha de nacimiento<input name="birth_date" type="date" required></label>
          <label>Sexo al nacer<select name="sex_at_birth"><option value="female">Femenino</option><option value="male">Masculino</option><option value="intersex">Intersexual</option><option value="unknown">No registrado</option></select></label>
          <label>Talla · cm<input name="height_cm" type="number" min="50" max="250" step="0.1"></label>
          <label>Grupo sanguíneo<input name="blood_type" placeholder="O+"></label>
          <label>Teléfono<input name="phone"></label>
          <label>Correo<input name="email" type="email"></label>
          <label>Ocupación<input name="occupation"></label>
          <label class="wide">Alergias<textarea name="allergies" placeholder="Separadas por coma"></textarea></label>
          <label class="wide">Patologías crónicas<textarea name="chronic_conditions" placeholder="Separadas por coma"></textarea></label>
          <label class="wide">Antecedentes transfusionales<textarea name="transfusion_history"></textarea></label>
          <label class="wide">Antecedentes traumáticos<textarea name="traumatic_history"></textarea></label>
          <label class="wide">Antecedentes quirúrgicos<textarea name="surgical_history"></textarea></label>
          <label>Cigarrillo<select name="smoking_status"><option value="unknown">Sin dato</option><option value="never">Nunca</option><option value="former">Anterior</option><option value="current">Actual</option></select></label>
          <label>Alcohol<select name="alcohol_status"><option value="unknown">Sin dato</option><option value="never">Nunca</option><option value="former">Anterior</option><option value="current">Actual</option></select></label>
          <label>Drogas<select name="drug_use_status"><option value="unknown">Sin dato</option><option value="never">Nunca</option><option value="former">Anterior</option><option value="current">Actual</option></select></label>
          <label>Café · tazas/día<input name="coffee_cups_per_day" type="number" min="0" max="30" step="0.5"></label>
          <label>Té · tazas/día<input name="tea_cups_per_day" type="number" min="0" max="30" step="0.5"></label>
          <label>Salud reproductiva<select name="reproductive_applicable"><option value="false">No aplica / no registrar</option><option value="true">Activar</option></select></label>
          <label>Estado<select name="pregnancy_status"><option value="unknown">Sin dato</option><option value="not_pregnant">No embarazada</option><option value="pregnant">Embarazada</option><option value="postpartum">Puerperio</option></select></label>
          <label>Última menstruación<input name="last_menstrual_period" type="date"></label>
          <label>Fecha probable de parto<input name="estimated_due_date" type="date"></label>
          <label>Fecha del parto<input name="delivery_date" type="date"></label>
          <label>Gestaciones<input name="pregnancies" type="number" min="0" max="30"></label>
          <label>Partos<input name="births" type="number" min="0" max="30"></label>
          <label>Cesáreas<input name="cesareans" type="number" min="0" max="30"></label>
          <label>Pérdidas gestacionales<input name="miscarriages_or_losses" type="number" min="0" max="30"></label>
        </div>
        <footer><button type="button" data-close-profile>Cancelar</button><button type="submit">Guardar perfil</button></footer>
      </form></dialog>
      <dialog id="medicationNormalizeDialog" class="health-os-dialog"><form id="medicationNormalizeForm" class="health-os-form">
        <header><div><small>MEDICATION ORGANIZER</small><h2>Organizar medicamento</h2></div><button type="button" data-close-medication>×</button></header>
        <label class="wide">Texto original<textarea name="text" required placeholder="Losartán 50 mg vía oral cada 24 horas"></textarea></label>
        <div id="medicationSuggestion" class="medication-suggestion"></div>
        <footer><button type="button" data-close-medication>Cancelar</button><button type="submit">Analizar texto</button></footer>
      </form></dialog>`);
    $$('[data-close-profile]').forEach(node => node.addEventListener("click", () => $("#profileDialog")?.close()));
    $$('[data-close-medication]').forEach(node => node.addEventListener("click", () => $("#medicationNormalizeDialog")?.close()));
  }

  const listText = values => (values || []).length ? values.map(value => `<span>${esc(value)}</span>`).join("") : '<span class="empty-value">Sin dato</span>';
  const valueOrEmpty = value => value === null || value === undefined || value === "" ? "Sin dato" : esc(value);

  function renderProfile() {
    const root = $("#profileRoot");
    const summary = snapshot?.profile_summary;
    if (!root || !summary) return;
    const p = summary.profile;
    const h = p.personal_history || {};
    const l = p.lifestyle || {};
    const reproductive = summary.pregnancy || {};
    const vitals = summary.vitals || {};
    root.innerHTML = `
      <div class="profile-toolbar"><div><strong>${esc(p.display_name)}</strong><p>${summary.age_years} años · ${valueOrEmpty(p.sex_at_birth)} · ${valueOrEmpty(p.blood_type)}</p></div><div><button id="normalizeMedicationButton">Organizar medicamento</button><button id="editProfileButton">Editar perfil</button></div></div>
      <div class="vital-matrix">
        ${[
          ["PA", vitals.blood_pressure, "mmHg"], ["FC", vitals.heart_rate_bpm, "lpm"], ["FR", vitals.respiratory_rate_rpm, "rpm"],
          ["Glicemia", vitals.blood_glucose_mg_dl, "mg/dL"], ["Colesterol", vitals.cholesterol_mg_dl, "mg/dL"],
          ["Oximetría", vitals.oxygen_saturation_percent, "%"], ["Temp", vitals.temperature_c, "°C"],
          ["Peso", vitals.weight_kg, "kg"], ["IMC", vitals.bmi, "kg/m²"], ["Estado nutricional", vitals.nutritional_status, ""]
        ].map(([label,value,unit]) => `<article><span>${label}</span><strong>${valueOrEmpty(value)}</strong><small>${unit}</small></article>`).join("")}
      </div>
      <div class="profile-section-grid">
        <article class="profile-card"><header><h3>Datos generales</h3></header><dl><dt>Nacimiento</dt><dd>${valueOrEmpty(p.birth_date)}</dd><dt>Talla</dt><dd>${valueOrEmpty(p.height_cm)} cm</dd><dt>Teléfono</dt><dd>${valueOrEmpty(p.phone)}</dd><dt>Correo</dt><dd>${valueOrEmpty(p.email)}</dd><dt>Ocupación</dt><dd>${valueOrEmpty(p.occupation)}</dd></dl></article>
        <article class="profile-card"><header><h3>Medicamentos</h3><span>${summary.medications.length}</span></header>${summary.medications.length ? summary.medications.map(m => `<div class="structured-med"><strong>${esc(m.name)} ${esc(m.strength || "")}</strong><span>${esc(m.route)} · ${esc(m.schedule || "sin frecuencia")}</span><small>${esc(m.purpose || "Propósito no registrado")} · ${esc(m.verification_status)}</small></div>`).join("") : '<p>Sin medicamentos estructurados.</p>'}</article>
        <article class="profile-card"><header><h3>Antecedentes personales</h3></header><h4>Patologías crónicas</h4><div class="chip-list">${listText(h.chronic_conditions)}</div><h4>Transfusionales</h4><div class="chip-list">${listText(h.transfusion_history)}</div><h4>Traumáticos</h4><div class="chip-list">${listText(h.traumatic_history)}</div><h4>Quirúrgicos</h4><div class="chip-list">${listText(h.surgical_history)}</div></article>
        <article class="profile-card"><header><h3>Hábitos y no patológicos</h3></header><dl><dt>Cigarrillo</dt><dd>${valueOrEmpty(l.smoking_status)}</dd><dt>Alcohol</dt><dd>${valueOrEmpty(l.alcohol_status)}</dd><dt>Drogas</dt><dd>${valueOrEmpty(l.drug_use_status)}</dd><dt>Café</dt><dd>${valueOrEmpty(l.coffee_cups_per_day)} tazas/día</dd><dt>Té</dt><dd>${valueOrEmpty(l.tea_cups_per_day)} tazas/día</dd></dl></article>
        <article class="profile-card"><header><h3>Antecedentes heredo-familiares</h3><span>${summary.family_member_count}</span></header><p>El genograma mantiene padre, madre, hijos, hermanos y otras generaciones con procedencia y confirmación.</p><button type="button" data-profile-open="family">Abrir genograma</button></article>
        <article class="profile-card reproductive-card"><header><h3>Salud gineco-obstétrica</h3><span>${esc(reproductive.status || "unknown")}</span></header>${p.reproductive_health?.applicable ? `<dl><dt>FUM</dt><dd>${valueOrEmpty(reproductive.last_menstrual_period)}</dd><dt>Edad gestacional</dt><dd>${reproductive.gestational_age_weeks !== null ? `${reproductive.gestational_age_weeks} semanas + ${reproductive.gestational_age_days} días` : "Sin cálculo"}</dd><dt>FPP</dt><dd>${valueOrEmpty(reproductive.estimated_due_date)}</dd><dt>Día de puerperio</dt><dd>${valueOrEmpty(reproductive.postpartum_day)}</dd></dl><p>${esc(reproductive.dating_note || "")}</p>` : '<p>Módulo no activado para este perfil.</p>'}</article>
      </div>`;
    $("#editProfileButton")?.addEventListener("click", openProfileForm);
    $("#normalizeMedicationButton")?.addEventListener("click", () => $("#medicationNormalizeDialog")?.showModal());
    $$('[data-profile-open]').forEach(button => button.addEventListener("click", () => activate(button.dataset.profileOpen)));
  }

  function fillForm(form, profile) {
    const set = (name, value) => { const node = form.elements.namedItem(name); if (node) node.value = value ?? ""; };
    set("display_name", profile.display_name);
    set("birth_date", profile.birth_date);
    set("sex_at_birth", profile.sex_at_birth);
    set("height_cm", profile.height_cm);
    set("blood_type", profile.blood_type);
    set("phone", profile.phone);
    set("email", profile.email);
    set("occupation", profile.occupation);
    set("allergies", (profile.allergies || []).join(", "));
    set("chronic_conditions", (profile.personal_history?.chronic_conditions || []).join(", "));
    set("transfusion_history", (profile.personal_history?.transfusion_history || []).join(", "));
    set("traumatic_history", (profile.personal_history?.traumatic_history || []).join(", "));
    set("surgical_history", (profile.personal_history?.surgical_history || []).join(", "));
    set("smoking_status", profile.lifestyle?.smoking_status);
    set("alcohol_status", profile.lifestyle?.alcohol_status);
    set("drug_use_status", profile.lifestyle?.drug_use_status);
    set("coffee_cups_per_day", profile.lifestyle?.coffee_cups_per_day);
    set("tea_cups_per_day", profile.lifestyle?.tea_cups_per_day);
    set("reproductive_applicable", String(profile.reproductive_health?.applicable || false));
    set("pregnancy_status", profile.reproductive_health?.pregnancy_status);
    set("last_menstrual_period", profile.reproductive_health?.last_menstrual_period);
    set("estimated_due_date", profile.reproductive_health?.estimated_due_date);
    set("delivery_date", profile.reproductive_health?.delivery_date);
    set("pregnancies", profile.reproductive_health?.pregnancies);
    set("births", profile.reproductive_health?.births);
    set("cesareans", profile.reproductive_health?.cesareans);
    set("miscarriages_or_losses", profile.reproductive_health?.miscarriages_or_losses);
  }

  function openProfileForm() {
    const dialog = $("#profileDialog");
    const form = $("#profileForm");
    const profile = snapshot?.profile_summary?.profile;
    if (!dialog || !form || !profile) return;
    fillForm(form, profile);
    dialog.showModal();
  }

  const csv = value => String(value || "").split(/[,\n]/).map(item => item.trim()).filter(Boolean);
  const numberOrNull = value => value === "" ? null : Number(value);

  function bindProfileForm() {
    $("#profileForm")?.addEventListener("submit", async event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const current = structuredClone(snapshot.profile_summary.profile);
      current.display_name = form.get("display_name");
      current.birth_date = form.get("birth_date");
      current.sex_at_birth = form.get("sex_at_birth");
      current.height_cm = numberOrNull(form.get("height_cm"));
      current.blood_type = form.get("blood_type");
      current.phone = form.get("phone");
      current.email = form.get("email");
      current.occupation = form.get("occupation");
      current.allergies = csv(form.get("allergies"));
      current.personal_history.chronic_conditions = csv(form.get("chronic_conditions"));
      current.personal_history.transfusion_history = csv(form.get("transfusion_history"));
      current.personal_history.traumatic_history = csv(form.get("traumatic_history"));
      current.personal_history.surgical_history = csv(form.get("surgical_history"));
      current.lifestyle.smoking_status = form.get("smoking_status");
      current.lifestyle.alcohol_status = form.get("alcohol_status");
      current.lifestyle.drug_use_status = form.get("drug_use_status");
      current.lifestyle.coffee_cups_per_day = numberOrNull(form.get("coffee_cups_per_day"));
      current.lifestyle.tea_cups_per_day = numberOrNull(form.get("tea_cups_per_day"));
      current.reproductive_health.applicable = form.get("reproductive_applicable") === "true";
      current.reproductive_health.pregnancy_status = form.get("pregnancy_status");
      current.reproductive_health.last_menstrual_period = form.get("last_menstrual_period") || null;
      current.reproductive_health.estimated_due_date = form.get("estimated_due_date") || null;
      current.reproductive_health.delivery_date = form.get("delivery_date") || null;
      current.reproductive_health.pregnancies = numberOrNull(form.get("pregnancies"));
      current.reproductive_health.births = numberOrNull(form.get("births"));
      current.reproductive_health.cesareans = numberOrNull(form.get("cesareans"));
      current.reproductive_health.miscarriages_or_losses = numberOrNull(form.get("miscarriages_or_losses"));
      try {
        await api("/api/profile", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(current)});
        $("#profileDialog")?.close();
        await refresh();
        toast("Perfil actualizado.");
      } catch (error) { toast(error.message); }
    });

    $("#medicationNormalizeForm")?.addEventListener("submit", async event => {
      event.preventDefault();
      const text = new FormData(event.currentTarget).get("text");
      try {
        const result = await api("/api/profile/medications/normalize", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({text})});
        const s = result.suggestion;
        $("#medicationSuggestion").innerHTML = `<article><strong>${esc(s.name)} ${esc(s.strength || "")}</strong><p>${esc(s.route)} · ${esc(s.schedule || "frecuencia no detectada")}</p><small>${esc(result.safety)}</small><button type="button" id="confirmMedication">Confirmar y guardar</button></article>`;
        $("#confirmMedication")?.addEventListener("click", async () => {
          s.verification_status = "patient_confirmed";
          await api("/api/treatment/plans", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(s)});
          $("#medicationNormalizeDialog")?.close();
          event.currentTarget.reset();
          await refresh();
          toast("Medicamento organizado y confirmado por el paciente.");
        }, {once:true});
      } catch (error) { toast(error.message); }
    });
  }

  function renderDevices() {
    const root = $("#deviceRoot");
    const summary = snapshot?.device_summary;
    if (!root || !summary) return;
    const connections = summary.connections || [];
    const latest = summary.latest_by_metric || {};
    root.innerHTML = `
      <div class="device-hero"><div><strong>Android Health Connect</strong><p>Lee datos autorizados en segundo plano y conserva procedencia, hora y dispositivo.</p></div><div><button id="demoDeviceSync">Probar sincronización</button><button id="refreshDevices">Actualizar</button></div></div>
      <div class="device-boundary"><strong>No es una transmisión clínica en tiempo real.</strong><p>La disponibilidad depende del reloj, teléfono, báscula, tensiómetro o aplicación que escriba cada dato en Health Connect.</p></div>
      <div class="device-stats"><article><span>Conexiones</span><strong>${connections.length}</strong></article><article><span>Registros</span><strong>${summary.record_count || 0}</strong></article><article><span>Métricas compatibles</span><strong>${summary.supported_metrics?.length || 0}</strong></article></div>
      <div class="device-grid">
        ${(summary.supported_metrics || []).map(metric => { const item = latest[metric]; return `<article class="device-metric"><header><h3>${esc(metric.replaceAll("_", " "))}</h3><span>${item ? "sincronizado" : "sin dato"}</span></header><strong>${item ? `${esc(item.value)} ${esc(item.unit)}` : "—"}</strong><small>${item ? `${esc(item.source_name)} · ${new Date(item.observed_at).toLocaleString("es-DO")}` : "Esperando una fuente autorizada"}</small></article>`; }).join("")}
      </div>
      <div class="connection-list">${connections.length ? connections.map(c => `<article><strong>${esc(c.display_name)}</strong><span>${esc(c.status)} · background ${c.background_read ? "on" : "off"}</span><small>${c.last_sync_at ? new Date(c.last_sync_at).toLocaleString("es-DO") : "Sin sincronización"}</small></article>`).join("") : '<article><strong>Sin dispositivo conectado</strong><span>Instala la app puente Android y concede permisos de Health Connect.</span></article>'}</div>`;
    $("#demoDeviceSync")?.addEventListener("click", async () => { try { await api("/api/demo/device-sync", {method:"POST"}); await refresh(); toast("Datos sintéticos sincronizados."); } catch (error) { toast(error.message); } });
    $("#refreshDevices")?.addEventListener("click", () => refresh().catch(error => toast(error.message)));
  }

  function hideInternalNames() {
    $(".topbar-title strong") && ($(".topbar-title strong").textContent = "HealthIA");
    $(".entry-welcome-head strong") && ($(".entry-welcome-head strong").textContent = "HealthIA");
    $$(".message-head strong, .agent-step strong").forEach(node => {
      node.textContent = publicNames[node.textContent.trim()] || node.textContent;
    });
    $$(".agent-mini strong").forEach((node, index) => {
      node.textContent = ["Health history", "Safety monitoring", "Results review", "Healthy habits", "Follow-up"][index] || "Health module";
    });
    const label = $(".rail-section > p");
    if (label) label.textContent = "Módulos de salud";
  }

  async function refresh() {
    snapshot = await api("/api/bootstrap");
    renderProfile();
    renderDevices();
    hideInternalNames();
  }

  window.addEventListener("DOMContentLoaded", () => {
    addNavigation();
    addViews();
    addDialogs();
    bindProfileForm();
    refresh().catch(error => toast(error.message));
    const list = $("#messageList");
    if (list) new MutationObserver(hideInternalNames).observe(list, {childList:true, subtree:true});
  });
})();
