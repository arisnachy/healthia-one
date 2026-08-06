if (!window.__HEALTHIA_PROFILE_DEVICES__) {
  window.__HEALTHIA_PROFILE_DEVICES__ = true;
  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
    const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
    const empty = value => value === null || value === undefined || value === "" ? "Sin dato" : esc(value);
    const csv = value => String(value || "").split(/[,\n]/).map(item => item.trim()).filter(Boolean);
    const numeric = value => value === "" ? null : Number(value);
    let snapshot = null;
    let refreshPromise = null;
    let pairingPoll = null;

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
      const items = [
        ["profile", "◌", "Perfil del paciente"],
        ["devices", "⌁", "Dispositivos"],
      ];
      for (const [view, icon, label] of items) {
        const button = document.createElement("button");
        button.dataset.open = view;
        button.innerHTML = `<span class="nav-icon">${icon}</span><b>${label}</b>`;
        button.addEventListener("click", () => activate(view));
        nav.insertBefore(button, record);
      }
    }

    function addViews() {
      const main = $(".conversation-column");
      if (!main || $("#view-profile")) return;
      main.insertAdjacentHTML("beforeend", `
        <section id="view-profile" class="view"><div class="page-body profile-page"><div class="page-kicker">PERFIL DE SALUD</div><h1>Perfil integral</h1><p>Datos generales, antecedentes, hábitos, tratamiento, salud reproductiva y resumen vital.</p><div id="profileRoot"></div></div></section>
        <section id="view-devices" class="view"><div class="page-body device-page"><div class="page-kicker">ANDROID HEALTH</div><h1>Dispositivos y Health Connect</h1><p>Sincronización autorizada desde reloj, teléfono, báscula y aplicaciones compatibles.</p><div id="deviceRoot"></div></div></section>`);
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
            <label>Grupo sanguíneo<input name="blood_type"></label>
            <label>Teléfono<input name="phone"></label>
            <label>Correo<input name="email" type="email"></label>
            <label>Ocupación<input name="occupation"></label>
            <label class="wide">Alergias<textarea name="allergies"></textarea></label>
            <label class="wide">Patologías crónicas<textarea name="chronic_conditions"></textarea></label>
            <label class="wide">Antecedentes transfusionales<textarea name="transfusion_history"></textarea></label>
            <label class="wide">Antecedentes traumáticos<textarea name="traumatic_history"></textarea></label>
            <label class="wide">Antecedentes quirúrgicos<textarea name="surgical_history"></textarea></label>
            <label>Cigarrillo<select name="smoking_status"><option value="unknown">Sin dato</option><option value="never">Nunca</option><option value="former">Anterior</option><option value="current">Actual</option></select></label>
            <label>Alcohol<select name="alcohol_status"><option value="unknown">Sin dato</option><option value="never">Nunca</option><option value="former">Anterior</option><option value="current">Actual</option></select></label>
            <label>Drogas<select name="drug_use_status"><option value="unknown">Sin dato</option><option value="never">Nunca</option><option value="former">Anterior</option><option value="current">Actual</option></select></label>
            <label>Café · tazas/día<input name="coffee_cups_per_day" type="number" min="0" step="0.5"></label>
            <label>Té · tazas/día<input name="tea_cups_per_day" type="number" min="0" step="0.5"></label>
            <label>Salud reproductiva<select name="reproductive_applicable"><option value="false">No registrar</option><option value="true">Activar</option></select></label>
            <label>Estado<select name="pregnancy_status"><option value="unknown">Sin dato</option><option value="not_pregnant">No embarazada</option><option value="pregnant">Embarazada</option><option value="postpartum">Puerperio</option></select></label>
            <label>Última menstruación<input name="last_menstrual_period" type="date"></label>
            <label>Fecha probable de parto<input name="estimated_due_date" type="date"></label>
            <label>Fecha del parto<input name="delivery_date" type="date"></label>
          </div>
          <footer><button type="button" data-close-profile>Cancelar</button><button type="submit">Guardar perfil</button></footer>
        </form></dialog>
        <dialog id="medicationNormalizeDialog" class="health-os-dialog"><form id="medicationNormalizeForm" class="health-os-form">
          <header><div><small>ORGANIZADOR DE TRATAMIENTO</small><h2>Organizar medicamento</h2></div><button type="button" data-close-medication>×</button></header>
          <label class="wide">Texto original<textarea name="text" required placeholder="Losartán 50 mg vía oral cada 24 horas"></textarea></label>
          <div id="medicationSuggestion" class="medication-suggestion"></div>
          <footer><button type="button" data-close-medication>Cancelar</button><button type="submit">Analizar texto</button></footer>
        </form></dialog>
        <dialog id="deviceConnectDialog" class="health-os-dialog device-connect-dialog"><div class="device-connect-shell">
          <header><div><small>CONEXIÓN SEGURA</small><h2>Conectar Health Connect</h2></div><button type="button" data-close-device>×</button></header>
          <p class="device-connect-lead">El navegador no puede leer Health Connect directamente. El puente Android solicita permiso al paciente y envía únicamente los tipos autorizados.</p>
          <div class="device-connect-steps">
            <article><span>1</span><div><strong>Instala el puente Android</strong><p>Ábrelo desde Android Studio o instala el APK que genere el proyecto.</p></div></article>
            <article><span>2</span><div><strong>Introduce la dirección y el código</strong><p>En un teléfono real usa la IP de esta computadora, no 127.0.0.1.</p></div></article>
            <article><span>3</span><div><strong>Autoriza y sincroniza</strong><p>Android mostrará cada permiso de Health Connect antes de enviar datos.</p></div></article>
          </div>
          <div class="pairing-panel">
            <label>Dirección del backend<input id="pairingBackendUrl" inputmode="url" autocomplete="off"></label>
            <label>Código temporal<input id="pairingCode" readonly value="------"></label>
            <div id="pairingStatus" class="pairing-status">Generando conexión segura…</div>
            <div class="pairing-actions"><button id="copyPairing" type="button">Copiar datos</button><a href="https://github.com/arisnachy/healthia-one/tree/main/android-health-bridge" target="_blank" rel="noreferrer">Abrir puente Android ↗</a></div>
          </div>
          <div class="device-demo-path"><div><strong>¿No tienes un dispositivo ahora?</strong><p>Ejecuta una sincronización sintética para probar toda la interfaz y el flujo longitudinal.</p></div><button id="dialogDemoDeviceSync" type="button">Probar sin dispositivo</button></div>
        </div></dialog>`);
      $$('[data-close-profile]').forEach(node => node.addEventListener("click", () => $("#profileDialog")?.close()));
      $$('[data-close-medication]').forEach(node => node.addEventListener("click", () => $("#medicationNormalizeDialog")?.close()));
      $$('[data-close-device]').forEach(node => node.addEventListener("click", closeDeviceDialog));
    }

    const tags = values => (values || []).length ? values.map(value => `<span>${esc(value)}</span>`).join("") : '<span class="empty-value">Sin dato</span>';

    function renderProfile() {
      const root = $("#profileRoot");
      const summary = snapshot?.profile_summary;
      if (!root || !summary) return;
      const profile = summary.profile;
      const history = profile.personal_history || {};
      const lifestyle = profile.lifestyle || {};
      const pregnancy = summary.pregnancy || {};
      const vitals = summary.vitals || {};
      const vitalItems = [
        ["PA", vitals.blood_pressure, "mmHg"], ["FC", vitals.heart_rate_bpm, "lpm"], ["FR", vitals.respiratory_rate_rpm, "rpm"],
        ["Glicemia", vitals.blood_glucose_mg_dl, "mg/dL"], ["Colesterol", vitals.cholesterol_mg_dl, "mg/dL"],
        ["Oximetría", vitals.oxygen_saturation_percent, "%"], ["Temp", vitals.temperature_c, "°C"],
        ["Peso", vitals.weight_kg, "kg"], ["IMC", vitals.bmi, "kg/m²"], ["Estado nutricional", vitals.nutritional_status, ""],
      ];
      root.innerHTML = `
        <div class="profile-toolbar"><div><strong>${esc(profile.display_name)}</strong><p>${summary.age_years} años · ${empty(profile.sex_at_birth)} · ${empty(profile.blood_type)}</p></div><div><button id="normalizeMedicationButton">Organizar medicamento</button><button id="editProfileButton">Editar perfil</button></div></div>
        <div class="vital-matrix">${vitalItems.map(([label,value,unit]) => `<article><span>${label}</span><strong>${empty(value)}</strong><small>${unit}</small></article>`).join("")}</div>
        <div class="profile-section-grid">
          <article class="profile-card"><header><h3>Datos generales</h3></header><dl><dt>Nacimiento</dt><dd>${empty(profile.birth_date)}</dd><dt>Talla</dt><dd>${empty(profile.height_cm)} cm</dd><dt>Teléfono</dt><dd>${empty(profile.phone)}</dd><dt>Correo</dt><dd>${empty(profile.email)}</dd><dt>Ocupación</dt><dd>${empty(profile.occupation)}</dd></dl></article>
          <article class="profile-card"><header><h3>Medicamentos</h3><span>${summary.medication_count || 0}</span></header><div class="tag-list">${tags((snapshot.medication_plans || []).map(item => `${item.name} ${item.strength || ""}`.trim()))}</div></article>
          <article class="profile-card"><header><h3>Antecedentes personales</h3></header><div class="tag-list">${tags(history.chronic_conditions)}</div><dl><dt>Transfusionales</dt><dd>${tags(history.transfusion_history)}</dd><dt>Traumáticos</dt><dd>${tags(history.traumatic_history)}</dd><dt>Quirúrgicos</dt><dd>${tags(history.surgical_history)}</dd></dl></article>
          <article class="profile-card"><header><h3>Hábitos</h3></header><dl><dt>Cigarrillo</dt><dd>${empty(lifestyle.smoking_status)}</dd><dt>Alcohol</dt><dd>${empty(lifestyle.alcohol_status)}</dd><dt>Drogas</dt><dd>${empty(lifestyle.drug_use_status)}</dd><dt>Café</dt><dd>${empty(lifestyle.coffee_cups_per_day)}</dd><dt>Té</dt><dd>${empty(lifestyle.tea_cups_per_day)}</dd></dl></article>
          <article class="profile-card"><header><h3>Antecedentes familiares</h3></header><p>${snapshot.family_summary?.biological_member_count || 0} familiares biológicos registrados.</p><button data-profile-open="family">Abrir genograma</button></article>
          <article class="profile-card reproductive-card"><header><h3>Salud gineco-obstétrica</h3><span>${esc(pregnancy.status || "unknown")}</span></header>${profile.reproductive_health?.applicable ? `<dl><dt>FUM</dt><dd>${empty(pregnancy.last_menstrual_period)}</dd><dt>Edad gestacional</dt><dd>${pregnancy.gestational_age_weeks !== null ? `${pregnancy.gestational_age_weeks} semanas + ${pregnancy.gestational_age_days} días` : "Sin cálculo"}</dd><dt>FPP</dt><dd>${empty(pregnancy.estimated_due_date)}</dd><dt>Día de puerperio</dt><dd>${empty(pregnancy.postpartum_day)}</dd></dl><p>${esc(pregnancy.dating_note || "")}</p>` : '<p>Módulo no activado para este perfil.</p>'}</article>
        </div>`;
      $("#editProfileButton")?.addEventListener("click", openProfileForm);
      $("#normalizeMedicationButton")?.addEventListener("click", () => $("#medicationNormalizeDialog")?.showModal());
      $$('[data-profile-open]').forEach(button => button.addEventListener("click", () => activate(button.dataset.profileOpen)));
    }

    function fillForm(form, profile) {
      const set = (name, value) => { const node = form.elements.namedItem(name); if (node) node.value = value ?? ""; };
      for (const key of ["display_name", "birth_date", "sex_at_birth", "height_cm", "blood_type", "phone", "email", "occupation"]) set(key, profile[key]);
      set("allergies", (profile.allergies || []).join(", "));
      set("chronic_conditions", (profile.personal_history?.chronic_conditions || []).join(", "));
      set("transfusion_history", (profile.personal_history?.transfusion_history || []).join(", "));
      set("traumatic_history", (profile.personal_history?.traumatic_history || []).join(", "));
      set("surgical_history", (profile.personal_history?.surgical_history || []).join(", "));
      for (const key of ["smoking_status", "alcohol_status", "drug_use_status", "coffee_cups_per_day", "tea_cups_per_day"]) set(key, profile.lifestyle?.[key]);
      set("reproductive_applicable", String(profile.reproductive_health?.applicable || false));
      for (const key of ["pregnancy_status", "last_menstrual_period", "estimated_due_date", "delivery_date"]) set(key, profile.reproductive_health?.[key]);
    }

    function openProfileForm() {
      const form = $("#profileForm");
      const profile = snapshot?.profile_summary?.profile;
      if (!form || !profile) return;
      fillForm(form, profile);
      $("#profileDialog")?.showModal();
    }

    function bindForms() {
      $("#profileForm")?.addEventListener("submit", async event => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const current = structuredClone(snapshot.profile_summary.profile);
        for (const key of ["display_name", "birth_date", "sex_at_birth", "blood_type", "phone", "email", "occupation"]) current[key] = form.get(key);
        current.height_cm = numeric(form.get("height_cm"));
        current.allergies = csv(form.get("allergies"));
        current.personal_history.chronic_conditions = csv(form.get("chronic_conditions"));
        current.personal_history.transfusion_history = csv(form.get("transfusion_history"));
        current.personal_history.traumatic_history = csv(form.get("traumatic_history"));
        current.personal_history.surgical_history = csv(form.get("surgical_history"));
        for (const key of ["smoking_status", "alcohol_status", "drug_use_status"]) current.lifestyle[key] = form.get(key);
        current.lifestyle.coffee_cups_per_day = numeric(form.get("coffee_cups_per_day"));
        current.lifestyle.tea_cups_per_day = numeric(form.get("tea_cups_per_day"));
        current.reproductive_health.applicable = form.get("reproductive_applicable") === "true";
        for (const key of ["pregnancy_status", "last_menstrual_period", "estimated_due_date", "delivery_date"]) current.reproductive_health[key] = form.get(key) || null;
        try {
          await api("/api/profile", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(current)});
          $("#profileDialog")?.close();
          await refresh();
          toast("Perfil actualizado.");
        } catch (error) { toast(error.message); }
      });

      $("#medicationNormalizeForm")?.addEventListener("submit", async event => {
        event.preventDefault();
        try {
          const text = new FormData(event.currentTarget).get("text");
          const result = await api("/api/profile/medications/normalize", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({text})});
          const suggestion = result.suggestion;
          $("#medicationSuggestion").innerHTML = `<article><strong>${esc(suggestion.name)} ${esc(suggestion.strength || "")}</strong><p>${esc(suggestion.route)} · ${esc(suggestion.schedule || "frecuencia no detectada")}</p><small>${esc(result.safety)}</small><button type="button" id="confirmMedication">Confirmar y guardar</button></article>`;
          $("#confirmMedication")?.addEventListener("click", async () => {
            suggestion.verification_status = "patient_confirmed";
            await api("/api/treatment/plans", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(suggestion)});
            $("#medicationNormalizeDialog")?.close();
            event.currentTarget.reset();
            await refresh();
            toast("Medicamento organizado y confirmado.");
          }, {once:true});
        } catch (error) { toast(error.message); }
      });
    }

    function closeDeviceDialog() {
      if (pairingPoll) clearInterval(pairingPoll);
      pairingPoll = null;
      $("#deviceConnectDialog")?.close();
    }

    async function demoDeviceSync() {
      await api("/api/demo/device-sync", {method:"POST"});
      await refresh();
      toast("Datos sintéticos sincronizados.");
    }

    async function startDevicePairing() {
      const dialog = $("#deviceConnectDialog");
      dialog?.showModal();
      const status = $("#pairingStatus");
      if (status) status.textContent = "Generando conexión segura…";
      if (pairingPoll) clearInterval(pairingPoll);
      try {
        const pairing = await api("/api/devices/pairing", {method:"POST"});
        $("#pairingBackendUrl").value = pairing.backend_url;
        $("#pairingCode").value = pairing.code;
        let networkHint = "";
        try {
          const host = new URL(pairing.backend_url).hostname;
          if (["127.0.0.1", "localhost"].includes(host)) {
            networkHint = " En el teléfono sustituye 127.0.0.1 por la IP local de tu PC; el campo puede editarse.";
          }
        } catch {}
        if (status) status.textContent = `Código válido hasta ${new Date(pairing.expires_at).toLocaleTimeString("es-DO", {hour:"2-digit", minute:"2-digit"})}. Esperando al puente Android.${networkHint}`;
        pairingPoll = setInterval(async () => {
          try {
            const current = await api(`/api/devices/pairing/${pairing.code}`);
            if (current.claimed) {
              clearInterval(pairingPoll); pairingPoll = null;
              if (status) status.textContent = `${current.display_name || "Dispositivo Android"} vinculado. Pulsa Sincronizar ahora en el teléfono.`;
              await refresh();
            }
          } catch {
            clearInterval(pairingPoll); pairingPoll = null;
            if (status) status.textContent = "El código expiró. Cierra y vuelve a abrir para generar otro.";
          }
        }, 2000);
      } catch (error) {
        if (status) status.textContent = error.message;
      }
    }

    function renderDevices() {
      const root = $("#deviceRoot");
      const summary = snapshot?.device_summary;
      if (!root || !summary) return;
      const connections = summary.connections || [];
      const latest = summary.latest_by_metric || {};
      root.innerHTML = `
        <div class="device-hero"><div><strong>Android Health Connect</strong><p>Lee datos autorizados en segundo plano y conserva procedencia, hora y dispositivo.</p></div><div><button id="connectDevice">Conectar dispositivo</button><button id="demoDeviceSync">Probar sin dispositivo</button><button id="refreshDevices">Actualizar</button></div></div>
        <div class="device-boundary"><strong>No es una transmisión clínica garantizada en tiempo real.</strong><p>La disponibilidad depende de la fuente que escriba cada dato en Health Connect.</p></div>
        <div class="device-stats"><article><span>Conexiones</span><strong>${connections.length}</strong></article><article><span>Registros</span><strong>${summary.record_count || 0}</strong></article><article><span>Métricas compatibles</span><strong>${summary.supported_metrics?.length || 0}</strong></article></div>
        <div class="device-grid">${(summary.supported_metrics || []).map(metric => { const item = latest[metric]; return `<article class="device-metric"><header><h3>${esc(metric.replaceAll("_", " "))}</h3><span>${item ? "sincronizado" : "sin dato"}</span></header><strong>${item ? `${esc(item.value)} ${esc(item.unit)}` : "—"}</strong><small>${item ? `${esc(item.source_name)} · ${new Date(item.observed_at).toLocaleString("es-DO")}` : "Esperando una fuente autorizada"}</small></article>`; }).join("")}</div>
        <div class="connection-list">${connections.length ? connections.map(connection => `<article><strong>${esc(connection.display_name)}</strong><span>${esc(connection.status)} · background ${connection.background_read ? "on" : "off"}</span><small>${connection.last_sync_at ? new Date(connection.last_sync_at).toLocaleString("es-DO") : "Sin sincronización"}</small></article>`).join("") : '<article><strong>Sin dispositivo conectado</strong><span>Instala la app puente Android y concede permisos de Health Connect.</span></article>'}</div>`;
      $("#connectDevice")?.addEventListener("click", startDevicePairing);
      $("#demoDeviceSync")?.addEventListener("click", () => demoDeviceSync().catch(error => toast(error.message)));
      const dialogDemo = $("#dialogDemoDeviceSync");
      if (dialogDemo) dialogDemo.onclick = () => demoDeviceSync().then(closeDeviceDialog).catch(error => toast(error.message));
      const copyPairing = $("#copyPairing");
      if (copyPairing) copyPairing.onclick = async () => {
        const value = `Backend: ${$("#pairingBackendUrl")?.value || ""}\nCódigo: ${$("#pairingCode")?.value || ""}`;
        try { await navigator.clipboard.writeText(value); toast("Datos de conexión copiados."); } catch { toast("Copia manualmente la dirección y el código."); }
      };
      $("#refreshDevices")?.addEventListener("click", () => refresh().catch(error => toast(error.message)));
    }

    async function refresh() {
      if (refreshPromise) return refreshPromise;
      refreshPromise = api("/api/bootstrap").then(data => {
        snapshot = data;
        renderProfile();
        renderDevices();
      }).finally(() => { refreshPromise = null; });
      return refreshPromise;
    }

    window.addEventListener("DOMContentLoaded", () => {
      addNavigation();
      addViews();
      addDialogs();
      bindForms();
      refresh().catch(error => toast(error.message));
    });
  })();
}
