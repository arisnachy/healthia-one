(() => {
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  const es = () => window.HealthIAI18n?.locale === "es";
  const copy = (spanish, english) => es() ? spanish : english;
  const refs = {
    nav: $('[data-open="discoveries"]'),
    navLabel: $('#discoveriesNavLabel'),
    badge: $('#discoveriesBadge'),
    kicker: $('#discoveriesKicker'),
    title: $('#discoveriesTitle'),
    body: $('#discoveriesBody'),
    summary: $('#discoveriesSummary'),
    discoveries: $('#discoveriesList'),
    programs: $('#opportunityProgramList'),
    receipts: $('#opportunityReceiptList'),
  };
  if (!refs.nav || !refs.discoveries) return;

  let payload = null;
  let loadPromise = null;

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set('Accept-Language', window.HealthIAI18n?.locale || 'en');
    const response = await fetch(path, {...options, headers});
    if (!response.ok) {
      let detail = `Error ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return response.json();
  }

  function dateLabel(value) {
    if (!value) return copy('Sin fecha', 'No date');
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return esc(value);
    return new Intl.DateTimeFormat(es() ? 'es-DO' : 'en-US', {dateStyle:'medium'}).format(date);
  }

  function externalLink(url, label) {
    if (!url) return '';
    return `<a class="secondary-button" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  }

  function chatButton(promptEs, promptEn, labelEs, labelEn) {
    return `<button type="button" class="secondary-button" data-opportunity-chat-es="${esc(promptEs)}" data-opportunity-chat-en="${esc(promptEn)}">${esc(copy(labelEs, labelEn))}</button>`;
  }

  function renderSummary() {
    const discoveries = payload?.discoveries || [];
    const programs = payload?.programs || [];
    const applications = payload?.applications || [];
    const receipts = payload?.receipts || [];
    const fresh = discoveries.filter(item => item.status === 'new').length;
    if (refs.badge) refs.badge.textContent = fresh;
    refs.summary.innerHTML = [
      [copy('Nuevos', 'New'), fresh],
      [copy('Programas', 'Programs'), programs.length],
      [copy('Solicitudes', 'Applications'), applications.length],
      [copy('Recibos', 'Receipts'), receipts.length],
    ].map(([label, value]) => `<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
  }

  function renderDiscoveries() {
    const items = (payload?.discoveries || []).slice().reverse();
    if (!items.length) {
      refs.discoveries.innerHTML = `<article class="data-card"><h3>${esc(copy('Nada nuevo que merezca interrumpirte', 'Nothing new worth interrupting you for'))}</h3><p>${esc(copy('HealthIA conserva tus temas autorizados y evita convertir cada publicación en una alerta.', 'HealthIA keeps your authorized topics and avoids turning every publication into an alert.'))}</p></article>`;
      return;
    }
    refs.discoveries.innerHTML = items.map(item => {
      const relation = item.relation === 'self' ? copy('Personal', 'Personal') : `${copy('Familia', 'Family')} · ${item.subject_label || item.relation}`;
      const tier = String(item.source?.evidence_tier || 'unknown').replaceAll('_', ' ');
      const benefits = (item.potential_benefits || []).slice(0, 3).map(value => `<li>${esc(value)}</li>`).join('');
      const limitations = (item.limitations || []).slice(0, 2).map(value => `<li>${esc(value)}</li>`).join('');
      return `<article class="data-card opportunity-card" data-discovery-id="${esc(item.id)}">
        <header><div><small>${esc(relation)} · ${esc(tier)}</small><h3>${esc(item.title)}</h3></div><small>${esc(dateLabel(item.source?.published_at || item.created_at))}</small></header>
        <p><strong>${esc(copy('Por qué te lo muestro:', 'Why this may matter:'))}</strong> ${esc(item.why_relevant || '')}</p>
        <p>${esc(item.summary || '')}</p>
        ${benefits ? `<div><strong>${esc(copy('Beneficios reportados por la fuente', 'Source-reported potential benefits'))}</strong><ul>${benefits}</ul></div>` : ''}
        ${limitations ? `<details><summary>${esc(copy('Límites y precauciones', 'Limits and cautions'))}</summary><ul>${limitations}</ul></details>` : ''}
        <div class="card-actions">${externalLink(item.source?.url, copy('Fuente original', 'Original source'))}${chatButton('Compáralo con mi medicación', 'Compare it with my medication', 'Comparar en el chat', 'Compare in chat')}<button type="button" class="secondary-button" data-save-discovery="${esc(item.id)}">${esc(copy('Guardar', 'Save'))}</button></div>
      </article>`;
    }).join('');
  }

  function renderProgramsAndApplications() {
    const programs = payload?.programs || [];
    const applications = payload?.applications || [];
    const cards = [];
    if (programs.length) {
      cards.push(`<div class="page-kicker">${esc(copy('AYUDAS Y RECURSOS', 'ASSISTANCE & RESOURCES'))}</div>`);
      for (const item of programs.slice().reverse()) {
        const related = applications.find(app => app.program_id === item.id);
        const status = related?.status || copy('candidato', 'candidate');
        const missing = related ? [...(related.missing_documents || []), ...(related.missing_fields || [])] : [];
        cards.push(`<article class="data-card opportunity-program-card">
          <header><div><small>${esc(item.provider)}</small><h3>${esc(item.title)}</h3></div><small>${esc(status)}</small></header>
          <p>${esc(item.benefit_summary || '')}</p>
          ${item.deadline ? `<p><strong>${esc(copy('Fecha límite:', 'Deadline:'))}</strong> ${esc(dateLabel(item.deadline))}</p>` : ''}
          ${missing.length ? `<p><strong>${esc(copy('Falta:', 'Missing:'))}</strong> ${esc(missing.join(', '))}</p>` : ''}
          <p><small>${esc(copy('Los requisitos encontrados por búsqueda permanecen desconocidos hasta verificarlos contra la fuente o formulario oficial.', 'Requirements found by search remain unknown until verified against the official source or form.'))}</small></p>
          <div class="card-actions">${externalLink(item.url, copy('Fuente oficial', 'Official source'))}${chatButton(`Completa el formulario de ${item.title}`, `Prepare the application for ${item.title}`, copy('Preparar en chat', 'Prepare in chat'), copy('Preparar en chat', 'Prepare in chat'))}</div>
        </article>`);
      }
    }
    if (!programs.length && !applications.length) {
      cards.push(`<article class="data-card"><h3>${esc(copy('Sin ayudas verificables guardadas todavía', 'No verifiable assistance saved yet'))}</h3><p>${esc(copy('Puedes pedirme en el chat: “Busca ayudas para…”', 'You can ask in chat: “Find assistance for…”'))}</p></article>`);
    }
    refs.programs.innerHTML = cards.join('');
  }

  function renderReceipts() {
    const receipts = (payload?.receipts || []).slice(0, 10);
    if (!receipts.length) {
      refs.receipts.innerHTML = '';
      return;
    }
    refs.receipts.innerHTML = `<div class="page-kicker">${esc(copy('RECIBOS DE AUTOPILOT', 'AUTOPILOT RECEIPTS'))}</div>` + receipts.map(receipt => {
      const actions = (receipt.actions || []).map(action => `<li><strong>${esc(action.action)}</strong> · ${esc(action.status)} — ${esc(action.reason)}</li>`).join('');
      return `<article class="data-card autopilot-receipt-card">
        <header><div><small>${esc(receipt.event_type)}</small><h3>${esc(copy('Trabajo verificable', 'Verifiable work'))}</h3></div><small>${esc(receipt.status)}</small></header>
        <p>${esc(copy('Costo:', 'Cost:'))} ${esc(receipt.cost_class)} · ${esc(dateLabel(receipt.created_at))}</p>
        <details><summary>${esc(copy('Ver acciones públicas', 'View public actions'))}</summary><ul>${actions}</ul></details>
        <small>${esc(copy('Este recibo muestra acciones, estados e IDs correlacionados; no contiene razonamiento privado.', 'This receipt shows actions, states and correlated IDs; it contains no private reasoning.'))}</small>
      </article>`;
    }).join('');
  }

  function localizeHeadings() {
    if (refs.navLabel) refs.navLabel.textContent = copy('Descubrimientos', 'Discoveries');
    if (refs.kicker) refs.kicker.textContent = copy('EVIDENCIA · OPORTUNIDADES · RECIBOS', 'EVIDENCE · OPPORTUNITIES · RECEIPTS');
    if (refs.title) refs.title.textContent = copy('Descubrimientos', 'Discoveries');
    if (refs.body) refs.body.textContent = copy(
      'Ciencia relevante, ayudas y recibos de acciones. HealthIA mantiene esto en silencio hasta que algo merezca tu atención.',
      'Relevant science, support programs and action receipts. HealthIA keeps this quiet until something is worth your attention.'
    );
  }

  function render() {
    localizeHeadings();
    renderSummary();
    renderDiscoveries();
    renderProgramsAndApplications();
    renderReceipts();
  }

  async function load(force = false) {
    if (loadPromise && !force) return loadPromise;
    loadPromise = api('/api/opportunities').then(data => { payload = data; render(); return data; }).catch(error => {
      refs.discoveries.innerHTML = `<article class="data-card"><h3>${esc(copy('No pude abrir Descubrimientos', 'Could not open Discoveries'))}</h3><p>${esc(error.message)}</p></article>`;
      throw error;
    }).finally(() => { loadPromise = null; });
    return loadPromise;
  }

  function sendToChat(prompt) {
    const chatButton = $('[data-open="chat"]');
    const input = $('#chatInput');
    const form = $('#chatForm');
    chatButton?.click();
    if (!input || !form) return;
    input.value = prompt;
    input.dispatchEvent(new Event('input', {bubbles:true}));
    form.requestSubmit();
  }

  refs.nav.addEventListener('click', () => { load(true).catch(() => {}); });
  document.addEventListener('healthia:locale-changed', () => { if (payload) render(); else localizeHeadings(); });
  document.addEventListener('healthia:ui-updated', () => {
    if (document.querySelector('#view-discoveries.is-active')) load(true).catch(() => {});
  });
  document.addEventListener('click', async event => {
    const save = event.target.closest('[data-save-discovery]');
    if (save) {
      try {
        await api(`/api/opportunities/discoveries/${encodeURIComponent(save.dataset.saveDiscovery)}/save`, {method:'POST'});
        await load(true);
      } catch {}
      return;
    }
    const chat = event.target.closest('[data-opportunity-chat-es]');
    if (chat) {
      sendToChat(es() ? chat.dataset.opportunityChatEs : chat.dataset.opportunityChatEn);
    }
  });

  localizeHeadings();
  load().catch(() => {});
})();
