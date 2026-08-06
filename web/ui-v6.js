(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const paths = {
    sparkle: '<path d="M12 2.8c.7 4.3 2.9 6.5 7.2 7.2-4.3.7-6.5 2.9-7.2 7.2-.7-4.3-2.9-6.5-7.2-7.2 4.3-.7 6.5-2.9 7.2-7.2Z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    chat: '<path d="M7 18.5 3.5 20l1-3.5A8 8 0 1 1 7 18.5Z"/><path d="M8 10h8M8 14h5"/>',
    calendar: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M7 3v4M17 3v4M3.5 9.5h17"/>',
    activity: '<path d="M3 12h3l2-5 4 10 2.5-6H21"/>',
    chart: '<path d="M5 20V10M10 20V4M15 20v-7M20 20V7"/>',
    folder: '<path d="M3.5 7.5h6l2-2h9v13.5h-17Z"/>',
    family: '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3.5 20v-2.5A4.5 4.5 0 0 1 8 13h2a4.5 4.5 0 0 1 4.5 4.5V20M15 14.5h1.5A4 4 0 0 1 20.5 18v2"/>',
    file: '<path d="M6 3.5h8l4 4V20H6Z"/><path d="M14 3.5V8h4M9 12h6M9 16h6"/>',
    heart: '<path d="M20.5 9.5c0 5-8.5 10-8.5 10s-8.5-5-8.5-10A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8.5 2.5Z"/><path d="M7.5 12h2l1.2-2.5 2.1 5 1.2-2.5h2.5"/>',
    pill: '<path d="m8.2 4.2 11.6 11.6a4.1 4.1 0 0 1-5.8 5.8L2.4 10a4.1 4.1 0 1 1 5.8-5.8Z"/><path d="m8.2 15.8 7.6-7.6"/>',
    appointment: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M7 3v4M17 3v4M3.5 9.5h17M8 14l2.2 2.2L16 11"/>',
    shield: '<path d="M12 3 20 6v5.5c0 4.6-3.1 7.7-8 9.5-4.9-1.8-8-4.9-8-9.5V6Z"/><path d="m9 12 2 2 4-4"/>',
    target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>',
    bell: '<path d="M6 10a6 6 0 0 1 12 0c0 5 2 5.5 2 5.5H4S6 15 6 10Z"/><path d="M10 19h4"/>',
    scale: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9a3 3 0 0 1 6 0M12 9l2-2"/>',
    shoe: '<path d="M4 14c3.5.5 6-1 7-4l2 3c1.6 2.3 3.2 3.1 7 3.5V20H8c-2.5 0-4-1.7-4-4Z"/><path d="M12 14h3"/>',
    user: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20v-2a7 7 0 0 1 14 0v2"/>',
    flag: '<path d="M5 21V4M5 5h10l-1.5 3L15 11H5"/>',
    mic: '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3M9 21h6"/>',
    send: '<path d="M12 19V5M6.5 10.5 12 5l5.5 5.5"/>',
    sliders: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6"/>',
    panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
    chevronLeft: '<path d="m14.5 6-6 6 6 6"/>',
    close: '<path d="m7 7 10 10M17 7 7 17"/>',
    result: '<path d="M6 3.5h9l3 3V20H6Z"/><path d="M15 3.5V7h3M9 15l2-2 2 1 3-4"/>',
  };

  function icon(name, className = "v6-icon") {
    return `<span class="${className}" aria-hidden="true"><svg viewBox="0 0 24 24">${paths[name] || paths.sparkle}</svg></span>`;
  }

  function navIconName(label) {
    return ({
      "HealthIA Chat": "chat",
      "Hoy": "calendar",
      "Mediciones": "activity",
      "Resultados": "chart",
      "Mi expediente": "folder",
      "Genograma familiar": "family",
      "Documentos": "file",
      "Línea de salud": "heart",
      "Tratamiento": "pill",
      "Citas y consulta": "appointment",
      "Permisos y privacidad": "shield",
      "Misiones de salud": "target",
    })[label] || "sparkle";
  }

  function decorateNavigation() {
    const brand = $(".brand-mark");
    if (brand) brand.innerHTML = icon("sparkle");

    const primaryIcon = $(".primary-action > span");
    if (primaryIcon) primaryIcon.innerHTML = icon("plus");

    $$(".main-nav button").forEach(button => {
      const label = $("b", button)?.textContent?.trim();
      const holder = button.firstElementChild;
      if (!label || !holder) return;
      holder.className = "nav-icon";
      holder.innerHTML = `<svg viewBox="0 0 24 24">${paths[navIconName(label)]}</svg>`;
    });

    const collapseLeft = $("#collapseLeft");
    if (collapseLeft) collapseLeft.innerHTML = icon("chevronLeft");
    const collapseRight = $("#collapseRight");
    if (collapseRight) collapseRight.innerHTML = icon("panel");
    const closeContext = $("#closeContext");
    if (closeContext) closeContext.innerHTML = icon("close");
  }

  function decorateTopbar() {
    const title = $(".topbar-title");
    if (title && !$(".kira-mark", title)) title.insertAdjacentHTML("afterbegin", icon("sparkle", "kira-mark"));
    const runtime = $("#runtimeLabel");
    if (runtime && !runtime.dataset.v6Labelled) {
      runtime.dataset.v6Labelled = "true";
      const technical = runtime.textContent;
      runtime.title = technical;
      runtime.textContent = "Continuidad activa";
    }
    const review = $("#runCheck");
    if (review) review.setAttribute("title", "Ejecutar una revisión solicitada por el paciente");
  }

  function decorateIntro() {
    const orb = $(".health-orb");
    if (orb) orb.innerHTML = icon("sparkle");
    const paragraph = $(".chat-intro .intro-copy > p");
    if (paragraph) paragraph.textContent = "Tu historia, tus resultados y tus próximos pasos, en una sola conversación.";

    const buttons = $$(".suggestion-grid button");
    const definitions = [
      {label: "Registrar presión", prompt: "Quiero registrar mi presión arterial", icon: "heart"},
      {label: "Explicar resultados", prompt: "Explícame mis resultados recientes", icon: "result"},
      {label: "Ver tratamiento", prompt: "Muéstrame mi tratamiento y las tomas registradas", icon: "pill"},
    ];
    buttons.forEach((button, index) => {
      if (index >= definitions.length) { button.remove(); return; }
      const item = definitions[index];
      button.dataset.prompt = item.prompt;
      button.innerHTML = `${icon(item.icon)}<div><strong>${item.label}</strong></div>`;
      button.setAttribute("aria-label", item.label);
    });
  }

  function miniChart(kind) {
    const d = kind === "activity"
      ? '<path d="M5 21V15M10 21V10M15 21V13M20 21V6"/>'
      : kind === "weight"
        ? '<path d="M2 17 7 14l4 2 4-6 4 3 3-5"/>'
        : '<path d="M2 15 6 12l4 3 4-7 4 3 4-5"/>';
    return `<span class="v6-mini-chart" aria-hidden="true"><svg viewBox="0 0 24 24">${d}</svg></span>`;
  }

  function decorateContext() {
    const cards = $$(".context-card");
    const map = {
      "Próxima acción": ["bell", null],
      "Última presión": ["heart", "pressure"],
      "Peso": ["scale", "weight"],
      "Actividad": ["shoe", "activity"],
      "Tratamiento registrado": ["pill", null],
      "Misiones activas": ["target", null],
      "Límite clínico": ["shield", null],
    };
    cards.forEach(card => {
      const label = $(".context-heading strong", card)?.textContent?.trim() || $(":scope > strong", card)?.textContent?.trim();
      const config = map[label];
      if (!config) return;
      const heading = $(".context-heading", card);
      if (heading && !$(".health-card-icon", heading)) heading.insertAdjacentHTML("afterbegin", icon(config[0], "health-card-icon"));
      if (config[1] && !$(".v6-mini-chart", card)) card.insertAdjacentHTML("beforeend", miniChart(config[1]));
    });
  }

  function decorateComposer() {
    const attach = $(".attach-button");
    const voice = $("#voiceButton");
    const send = $("#sendButton");
    if (attach) attach.innerHTML = icon("plus");
    if (voice) voice.innerHTML = icon("mic");
    if (send) send.innerHTML = icon("send");
  }

  function patientHasConversation(snapshot) {
    return (snapshot?.messages || []).some(message => message.role === "patient");
  }

  function removeBackgroundMessages(snapshot) {
    const messages = snapshot?.messages || [];
    const firstPatient = messages.findIndex(message => message.role === "patient");
    const hidden = new Set(
      messages
        .filter((message, index) => message.metadata?.proactive || (firstPatient >= 0 && index < firstPatient))
        .map(message => message.id)
    );
    $$("#messageList .message").forEach(article => {
      if (hidden.has(article.dataset.id)) article.remove();
    });
  }

  function welcomeText(name) {
    const firstName = String(name || "").trim().split(/\s+/)[0] || "";
    return `Hola${firstName ? `, ${firstName}` : ""}. Ya revisé tus datos recientes. ¿Qué te gustaría revisar hoy?`;
  }

  function ensureWelcome(name) {
    const intro = $(".chat-intro");
    const suggestions = $(".suggestion-grid", intro);
    if (!intro || !suggestions) return;
    let welcome = $(".entry-welcome", intro);
    if (!welcome) {
      welcome = document.createElement("div");
      welcome.className = "entry-welcome";
      welcome.innerHTML = `
        <div class="entry-welcome-avatar">${icon("sparkle")}</div>
        <div class="entry-welcome-copy">
          <div class="entry-welcome-head"><strong>KIRA Health</strong><span>ahora</span></div>
          <div class="entry-welcome-bubble"><span class="entry-welcome-text"></span><span class="entry-welcome-caret"></span></div>
        </div>`;
      intro.insertBefore(welcome, suggestions);
    }

    const target = $(".entry-welcome-text", welcome);
    const text = welcomeText(name);
    if (!target || target.dataset.message === text) return;
    target.dataset.message = text;
    target.textContent = "";
    welcome.classList.remove("is-complete");
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (reduceMotion) {
      target.textContent = text;
      welcome.classList.add("is-complete");
      return;
    }
    let index = 0;
    const step = () => {
      target.textContent = text.slice(0, index += 2);
      if (index < text.length) window.setTimeout(step, 17);
      else welcome.classList.add("is-complete");
    };
    window.setTimeout(step, 180);
  }

  function removeWelcome() {
    $(".entry-welcome")?.remove();
  }

  function syncConversation(snapshot) {
    const scroll = $("#chatScroll");
    const list = $("#messageList");
    if (!scroll || !list || !snapshot) return;

    removeBackgroundMessages(snapshot);
    const livePatient = Boolean($(".message.patient", list));
    const persistedPatient = patientHasConversation(snapshot);

    if (!livePatient && !persistedPatient) {
      list.replaceChildren();
      scroll.classList.add("entry-mode");
      scroll.classList.remove("conversation-started");
      ensureWelcome(snapshot.profile?.display_name);
      return;
    }

    scroll.classList.remove("entry-mode");
    scroll.classList.add("conversation-started");
    removeWelcome();
  }

  let snapshot = null;
  let syncing = false;
  let refreshTimer = null;

  async function loadSnapshot() {
    const response = await fetch("/api/bootstrap");
    if (!response.ok) return;
    snapshot = await response.json();
    syncConversation(snapshot);
  }

  function observeConversation() {
    const list = $("#messageList");
    if (!list) return;
    new MutationObserver(() => {
      if (syncing) return;
      syncing = true;
      window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(async () => {
        try {
          if ($(".message.patient", list)) {
            $("#chatScroll")?.classList.remove("entry-mode");
            $("#chatScroll")?.classList.add("conversation-started");
            removeWelcome();
          }
          await loadSnapshot();
        } finally {
          syncing = false;
        }
      }, 100);
    }).observe(list, {childList: true});
  }

  function redecorateDynamicNavigation() {
    window.setTimeout(() => {
      decorateNavigation();
      decorateContext();
    }, 80);
  }

  window.addEventListener("DOMContentLoaded", () => {
    decorateNavigation();
    decorateTopbar();
    decorateIntro();
    decorateContext();
    decorateComposer();
    observeConversation();
    loadSnapshot().catch(() => {});

    const nav = $(".main-nav");
    if (nav) new MutationObserver(redecorateDynamicNavigation).observe(nav, {childList: true});
    const context = $("#contextPanel");
    if (context) new MutationObserver(decorateContext).observe(context, {childList: true, subtree: true});
  });
})();
