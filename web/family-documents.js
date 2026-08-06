if (!window.__HEALTHIA_FAMILY_DOCUMENTS__) {
  window.__HEALTHIA_FAMILY_DOCUMENTS__ = true;
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

  function injectNavigation() {
    const nav = $(".main-nav");
    const missions = nav?.querySelector('[data-open="missions"]');
    if (!nav || !missions || nav.querySelector('[data-open="family"]')) return;
    const family = document.createElement("button");
    family.dataset.open = "family";
    family.innerHTML = "<span>◇</span><b>Genograma familiar</b>";
    const documents = document.createElement("button");
    documents.dataset.open = "documents";
    documents.innerHTML = "<span>▣</span><b>Documentos</b>";
    nav.insertBefore(family, missions);
    nav.insertBefore(documents, missions);
    [family, documents].forEach(button => button.addEventListener("click", () => activateView(button.dataset.open)));
  }

  function injectQuickActions() {
    const quick = $(".quick-records");
    if (!quick || quick.querySelector('[data-health-os="family"]')) return;
    const family = document.createElement("button");
    family.type = "button";
    family.dataset.healthOs = "family";
    family.textContent = "◇ Familia";
    const documents = document.createElement("button");
    documents.type = "button";
    documents.dataset.healthOs = "documents";
    documents.textContent = "▣ Documento";
    family.addEventListener("click", () => activateView("family"));
    documents.addEventListener("click", () => activateView("documents"));
    quick.append(family, documents);
  }

  function injectViews() {
    const main = $(".conversation-column");
    if (!main || $("#view-family")) return;
    const family = document.createElement("section");
    family.id = "view-family";
    family.className = "view";
    family.innerHTML = `<div class="page-body"><div class="page-kicker">HEREDITAS · HISTORIA FAMILIAR</div><h1>Genograma patológico</h1><p>Organiza parentescos y antecedentes para preparar preguntas preventivas. Un patrón familiar no confirma una enfermedad.</p><div id="genogramRoot"></div></div>`;
    const documents = document.createElement("section");
    documents.id = "view-documents";
    documents.className = "view";
    documents.innerHTML = `<div class="page-body"><div class="page-kicker">ARCHIVUM · EXPEDIENTE DOCUMENTAL</div><h1>Documentos del paciente</h1><p>Laboratorios, imágenes, recetas, informes y notas organizados por procedencia y estado.</p><div id="documentsRoot"></div></div>`;
    main.append(family, documents);
  }

  function injectDialogs() {
    if ($("#familyDialog")) return;
    document.body.insertAdjacentHTML("beforeend", `
      <dialog id="familyDialog" class="health-os-dialog"><form id="familyForm" class="health-os-form">
        <header><div><small>GENOGRAMA PATOLÓGICO</small><h2>Añadir familiar</h2></div><button type="button" data-close="familyDialog">×</button></header>
        <div class="health-os-fields">
          <label>Nombre o etiqueta<input name="display_name" required placeholder="Madre, abuelo paterno..."></label>
          <label>Parentesco<input name="relation" required placeholder="madre"></label>
          <label>Generación<select name="generation"><option value="-2">Abuelos</option><option value="-1">Padres / tíos</option><option value="0" selected>Paciente / hermanos</option><option value="1">Hijos</option><option value="2">Nietos</option></select></label>
          <label>Línea<select name="lineage"><option value="maternal">Materna</option><option value="paternal">Paterna</option><option value="both">Ambas</option><option value="unknown">No definida</option></select></label>
          <label>Sexo al nacer<select name="sex_at_birth"><option value="female">Femenino</option><option value="male">Masculino</option><option value="unknown">No registrado</option></select></label>
          <label>Patología principal<input name="condition" placeholder="Diabetes"></label>
          <label>Edad al diagnóstico<input name="age_at_diagnosis" type="number" min="0" max="120"></label>
          <label class="wide">Notas<textarea name="notes" rows="2" placeholder="Fuente, incertidumbre o detalles relevantes"></textarea></label>
        </div><footer><button type="button" data-close="familyDialog">Cancelar</button><button type="submit">Guardar familiar</button></footer>
      </form></dialog>
      <dialog id="documentDialog" class="health-os-dialog"><form id="documentForm" class="health-os-form">
        <header><div><small>ARCHIVO CLÍNICO</small><h2>Guardar documento</h2></div><button type="button" data-close="documentDialog">×</button></header>
        <div class="health-os-fields">
          <label class="wide">Archivo<input name="file" type="file" accept=".json,.csv,.txt,.pdf,.png,.jpg,.jpeg" required></label>
          <label>Título<input name="title" placeholder="Resultado de laboratorio"></label>
          <label>Categoría<select name="category"><option value="laboratory">Laboratorio</option><option value="imaging">Imagen</option><option value="prescription">Receta</option><option value="consultation">Consulta / informe</option><option value="discharge">Alta</option><option value="vaccine">Vacuna</option><option value="insurance">Seguro</option><option value="identity">Identidad</option><option value="other">Otro</option></select></label>
        </div><footer><button type="button" data-close="documentDialog">Cancelar</button><button type="submit">Guardar documento</button></footer>
      </form></dialog>`);
    $$('[data-close]').forEach(button => button.addEventListener("click", () => $(`#${button.dataset.close}`)?.close()));
  }

  function activateView(view) {
    $$(".view").forEach(node => node.classList.toggle("is-active", node.id === `view-${view}`));
    $$('.main-nav [data-open]').forEach(node => node.classList.toggle("is-active", node.dataset.open === view));
    if (view === "family" || view === "documents") refresh().catch(error => toast(error.message));
  }

  function generationLabel(value) {
    return ({"-2":"Abuelos y generaciones previas","-1":"Padres, tíos y tías","0":"Paciente y hermanos","1":"Hijos","2":"Nietos"})[String(value)] || "Familia";
  }

  function renderGenogram() {
    const root = $("#genogramRoot");
    if (!root || !snapshot) return;
    const members = snapshot.family_members || [];
    const summary = snapshot.family_summary || {clusters:[]};
    const grouped = new Map();
    members.forEach(member => {
      const key = String(member.generation);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(member);
    });
    const rows = ["-2","-1","0","1","2"].filter(key => grouped.has(key)).map(key => `
      <section class="generation-row"><div class="generation-label">${generationLabel(key)}</div><div class="generation-members">${grouped.get(key).map(member => `
        <article class="family-node" data-sex="${escapeHtml(member.sex_at_birth)}"><header><div class="person-symbol"><span>${member.sex_at_birth === "female" ? "F" : member.sex_at_birth === "male" ? "M" : "?"}</span></div><small>${escapeHtml(member.lineage)}</small></header><h3>${escapeHtml(member.display_name)}</h3><small>${escapeHtml(member.relation)}</small><div class="family-condition-list">${member.conditions.length ? member.conditions.map(condition => `<div class="family-condition">${escapeHtml(condition.name)}${condition.age_at_diagnosis != null ? ` · ${condition.age_at_diagnosis} años` : ""}</div>`).join("") : '<div class="family-empty">Sin patologías registradas</div>'}</div></article>`).join("")}</div></section>`).join("");
    root.innerHTML = `<div class="genogram-shell"><div class="genogram-toolbar"><div><strong>Mapa familiar autorizado</strong><p>Separa datos confirmados, reportados e incompletos.</p></div><button id="addFamilyButton">＋ Añadir familiar</button></div><div class="genogram-summary"><article><span>Familiares</span><strong>${members.length}</strong></article><article><span>Biológicos</span><strong>${summary.biological_member_count || 0}</strong></article><article><span>Patrones a contextualizar</span><strong>${summary.clusters?.length || 0}</strong></article></div><div class="genogram-board">${rows || '<div class="family-empty">Añade el primer familiar para construir la línea patológica.</div>'}</div><div class="family-clusters">${summary.clusters?.length ? summary.clusters.map(cluster => `<article class="family-cluster"><strong>${escapeHtml(cluster.condition)}</strong><p>${cluster.relative_count} familiares registrados · ${cluster.early_onset_count} con inicio antes de 50 años. Es contexto preventivo, no diagnóstico.</p></article>`).join("") : '<article class="family-cluster"><strong>Sin agregaciones visibles</strong><p>El sistema no inventa patrones cuando faltan datos.</p></article>'}</div></div>`;
    $("#addFamilyButton")?.addEventListener("click", () => $("#familyDialog")?.showModal());
  }

  function renderDocuments() {
    const root = $("#documentsRoot");
    if (!root || !snapshot) return;
    const documents = snapshot.documents || [];
    const index = snapshot.document_index || {total:0,pending_review:0,by_category:{}};
    root.innerHTML = `<div class="document-toolbar"><div><strong>Expediente documental</strong><p>Todos los documentos conservan categoría, procedencia y estado.</p></div><button id="addDocumentButton">⇧ Cargar documento</button></div><div class="document-index"><article><span>Total</span><strong>${index.total || 0}</strong></article><article><span>Pendientes de revisión</span><strong>${index.pending_review || 0}</strong></article><article><span>Categorías</span><strong>${Object.keys(index.by_category || {}).length}</strong></article><article><span>Resultados estructurados</span><strong>${snapshot.results?.length || 0}</strong></article></div><div class="document-grid">${documents.length ? documents.slice().reverse().map(document => `<article class="document-card"><header><h3>${escapeHtml(document.title)}</h3><span class="document-badge">${escapeHtml(document.category)}</span></header><p>${escapeHtml(document.summary || "Documento guardado")}</p><footer><small>${escapeHtml(document.filename)} · ${(document.size_bytes / 1024).toFixed(1)} KB</small><a href="/api/documents/${encodeURIComponent(document.id)}/download">Abrir ↗</a></footer></article>`).join("") : '<article class="document-card"><h3>Sin documentos</h3><p>Carga laboratorios, imágenes, recetas o informes. HealthIA no leerá ni inventará contenido sin una extracción verificable.</p></article>'}</div>`;
    $("#addDocumentButton")?.addEventListener("click", () => $("#documentDialog")?.showModal());
  }

  function hydrateChatControls() {
    $$("#messageList .message").forEach(article => {
      if (article.querySelector(".health-os-message-actions")) return;
      const text = article.textContent?.toLowerCase() || "";
      const targets = [];
      if (text.includes("genograma") || text.includes("historia familiar") || text.includes("familiares")) {
        targets.push(["Abrir genograma", "family"]);
      }
      if (text.includes("documento") || text.includes("expediente") || text.includes("archivo")) {
        targets.push(["Abrir documentos", "documents"]);
      }
      if (!targets.length) return;
      const bar = document.createElement("div");
      bar.className = "message-actions health-os-message-actions";
      bar.innerHTML = targets.map(([label, target]) => `<button type="button" data-health-os-target="${target}">${label}</button>`).join("");
      article.querySelector(".message-content")?.append(bar);
    });
  }

  async function refresh() {
    snapshot = await api("/api/bootstrap");
    renderGenogram();
    renderDocuments();
    hydrateChatControls();
  }

  function bindForms() {
    $("#familyForm")?.addEventListener("submit", async event => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(event.currentTarget).entries());
      const condition = String(values.condition || "").trim();
      const payload = {
        display_name: values.display_name,
        relation: values.relation,
        generation: Number(values.generation),
        lineage: values.lineage,
        sex_at_birth: values.sex_at_birth,
        conditions: condition ? [{name: condition, age_at_diagnosis: values.age_at_diagnosis ? Number(values.age_at_diagnosis) : null, notes: values.notes || "", confirmed: false}] : [],
      };
      try {
        await api("/api/family", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
        event.currentTarget.reset(); $("#familyDialog")?.close(); await refresh(); toast("Familiar añadido al genograma.");
      } catch (error) { toast(error.message); }
    });
    $("#documentForm")?.addEventListener("submit", async event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      try {
        await api("/api/documents/upload", {method:"POST",body:form});
        event.currentTarget.reset(); $("#documentDialog")?.close(); await refresh(); toast("Documento organizado en el expediente.");
      } catch (error) { toast(error.message); }
    });
  }

  function extendChatActions() {
    $("#messageList")?.addEventListener("click", event => {
      const target = event.target.closest("[data-health-os-target]")?.dataset.healthOsTarget;
      if (target) activateView(target);
    });
    const list = $("#messageList");
    if (list) new MutationObserver(hydrateChatControls).observe(list, {childList: true, subtree: true});
    hydrateChatControls();
  }

  window.addEventListener("DOMContentLoaded", () => {
    injectNavigation(); injectQuickActions(); injectViews(); injectDialogs(); bindForms(); extendChatActions();
    refresh().catch(error => toast(error.message));
  });
})();

}
