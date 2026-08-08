(() => {
  if (window.HealthIAI18n) return;

  const dictionaries = {
    en: {
      "meta.title": "HealthIA ONE · Your health never starts over",
      "meta.description": "HealthIA ONE — patient-first agentic health continuity system",
      "brand.tagline": "Your health, with memory",
      "nav.collapse": "Collapse navigation",
      "nav.expand": "Expand navigation",
      "nav.new": "New consultation",
      "nav.main": "Main navigation",
      "nav.chat": "HealthIA Chat",
      "nav.today": "Today",
      "nav.measurements": "Measurements",
      "nav.results": "Results",
      "nav.record": "My record",
      "nav.missions": "Health missions",
      "rail.areas": "Health areas",
      "rail.history": "History",
      "rail.history.sub": "Longitudinal memory",
      "rail.safety": "Safety",
      "rail.safety.sub": "Signals and priorities",
      "rail.results": "Results",
      "rail.results.sub": "Evidence and explanation",
      "rail.followup": "Follow-up",
      "rail.followup.sub": "Next step",
      "account.patient": "Patient",
      "account.settings": "Account & settings",
      "account.open": "Account and settings",
      "top.preparing": "Preparing continuity",
      "top.ready": "Ready when you need me",
      "top.review": "Review continuity",
      "top.context": "Show or hide context",
      "chat.eyebrow": "HEALTHIA ONE · PERSONAL CONTINUITY",
      "chat.hero": "Your health never starts over.",
      "chat.hero.body": "Tell me what is happening the way you would tell a person. I use your authorized memory and ask only what is missing.",
      "chat.patient": "Patient",
      "chat.signals": "Authorized signals",
      "chat.open_missions": "Open missions",
      "chat.prompt.bp": "Record blood pressure",
      "chat.prompt.bp.sub": "With technique and context",
      "chat.prompt.results": "Explain results",
      "chat.prompt.results.sub": "With the original file",
      "chat.prompt.weight": "Review my weight",
      "chat.prompt.weight.sub": "Trend and context",
      "chat.prompt.visit": "Prepare a visit",
      "chat.prompt.visit.sub": "History, documents and questions",
      "chat.input": "Tell me what is happening, ask about a result, or record something…",
      "chat.attach": "Attach result",
      "chat.voice": "Dictate message",
      "chat.send": "Send",
      "chat.boundary": "HealthIA organizes and guides using your authorized data. It does not replace professional evaluation or prescribe.",
      "today.kicker": "REQUESTED OR EVENT-DRIVEN FOLLOW-UP",
      "today.title": "Today",
      "today.body": "Items derived from your data, events, or reviews you requested.",
      "measure.kicker": "AUTHORIZED SIGNALS",
      "measure.title": "Measurements",
      "measure.body": "Record data with context; a trend matters more than an isolated number.",
      "measure.vitals": "＋ Blood pressure & vitals",
      "measure.weight": "＋ Weight",
      "measure.activity": "＋ Activity",
      "results.kicker": "EVIDENCE-BACKED RESULTS",
      "results.title": "Results",
      "results.body": "Upload a study; HealthIA preserves the original, identifies what it can read, and links it to your clinical memory.",
      "results.upload": "Upload result",
      "results.formats": "JSON, CSV, TXT, PDF or image · max 5 MB",
      "record.kicker": "PATIENT RECORD",
      "record.title": "My health story in one place",
      "record.body": "Confirmed data, registered treatment, allergies, and signals you authorized.",
      "missions.kicker": "CONTINUITY & FOLLOW-UP",
      "missions.title": "Health missions",
      "missions.body": "Living tasks that stay open until a verifiable next step or closure exists.",
      "context.kicker": "AUTHORIZED CONTEXT",
      "context.title": "Your health now",
      "context.next": "Next action",
      "context.active": "active",
      "context.none": "No pending actions.",
      "context.bp": "Latest blood pressure",
      "context.no_record": "No record",
      "context.weight": "Weight",
      "context.no_trend": "No trend",
      "context.activity": "Activity",
      "context.last": "Latest record",
      "context.treatment": "Registered treatment",
      "context.missions": "Active missions",
      "context.boundary": "Clinical boundary",
      "context.boundary.body": "Possibilities explained by HealthIA are not confirmed diagnoses. Medication and clinical decisions require professional evaluation.",
      "dialog.kicker": "PATIENT ENTRY",
      "dialog.new": "New measurement",
      "dialog.close": "Close",
      "dialog.cancel": "Cancel",
      "dialog.save": "Save",
      "app.now": "now",
      "app.module": "Health module",
      "app.modules": "View activated modules",
      "app.active_signals": "active",
      "app.pulse": "pulse",
      "app.no_missions": "No active missions.",
      "app.all_quiet": "All quiet",
      "app.no_proactive": "No new event-driven observations.",
      "app.bp": "Blood pressure",
      "app.weight": "Weight",
      "app.patient_record": "Patient entry",
      "app.steps": "steps",
      "app.active_minutes": "active minutes",
      "app.no_measurements": "No measurements.",
      "app.original": "View original file ↗",
      "app.twin_linked": "Clinical twin linked",
      "app.no_original": "No original file linked",
      "app.extracted": "extracted items",
      "app.no_results": "No results uploaded yet.",
      "app.modules_short": "modules",
      "app.evidence_short": "evidence",
      "app.no_missions_yet": "Missions appear when HealthIA detects or receives a follow-up task.",
      "app.analyzing": "HealthIA is analyzing your message…",
      "app.ready": "Ready",
      "app.uploading": "HealthIA is identifying and organizing the result…",
      "app.result_parsed": "Result interpreted, saved, and linked to the clinical twin.",
      "app.result_pending": "Original saved; multimodal analysis pending without inventing findings.",
      "app.saved": "Measurement saved.",
      "app.event_observation": "HealthIA has a new observation triggered by a clinical event.",
      "app.runtime_error": "HealthIA reported an auditable runtime error.",
      "app.reconnecting": "The event connection will reconnect automatically.",
      "app.reviewing": "HealthIA is reviewing continuity…",
      "app.no_new": "No new observations.",
      "app.new_count": "new observations",
      "app.new_consult": "New consultation ready.",
      "app.local": "Local mode · no API",
      "app.key_missing": "Gemini · API configuration missing",
      "dialog.vital": "Record blood pressure and vitals",
      "dialog.weight": "Record weight",
      "dialog.activity": "Record activity",
      "field.systolic": "Systolic",
      "field.diastolic": "Diastolic",
      "field.pulse": "HR · bpm",
      "field.rr": "RR · rpm",
      "field.oxygen": "Oxygen saturation · %",
      "field.temp": "Temperature · °C",
      "field.glucose": "Glucose · mg/dL",
      "field.cholesterol": "Cholesterol · mg/dL",
      "field.symptoms": "Symptoms separated by commas",
      "field.weight": "Weight in kg",
      "field.note": "Context or note",
      "field.steps": "Steps",
      "field.minutes": "Active minutes",
      "field.barrier": "Barrier or context",
      "auth.title": "HealthIA ONE · Sign in",
      "auth.eyebrow": "HEALTHIA ONE · PATIENT CONTINUITY",
      "auth.hero": "Your health should remember you.",
      "auth.hero.body": "One private patient space for your conversations, results, devices, health missions and longitudinal evidence.",
      "auth.point.private": "Patient-scoped data",
      "auth.point.signed": "Signed session",
      "auth.point.ondemand": "AI on demand",
      "auth.live": "Continuity that survives the chat",
      "auth.live.body": "Original evidence → clinical twin → health mission → follow-up",
      "auth.login_tab": "Sign in",
      "auth.register_tab": "Create account",
      "auth.welcome": "Welcome back",
      "auth.welcome.body": "Continue your private HealthIA timeline.",
      "auth.email": "Email",
      "auth.password": "Password",
      "auth.login": "Enter HealthIA",
      "auth.create": "Create your account",
      "auth.create.body": "Start with an empty record and build your own continuity.",
      "auth.name": "Patient name",
      "auth.password_hint": "Use at least 10 characters. Passwords are stored only as salted scrypt hashes.",
      "auth.create_button": "Create my account",
      "auth.boundary": "HealthIA does not replace professional evaluation or emergency services.",
      "auth.checking": "Checking…"
    },
    es: {
      "meta.title": "HealthIA ONE · Tu salud nunca empieza de cero",
      "meta.description": "HealthIA ONE — sistema agéntico de continuidad de salud centrado en el paciente",
      "brand.tagline": "Tu salud, con memoria",
      "nav.collapse": "Colapsar navegación",
      "nav.expand": "Expandir navegación",
      "nav.new": "Nueva consulta",
      "nav.main": "Navegación principal",
      "nav.chat": "HealthIA Chat",
      "nav.today": "Hoy",
      "nav.measurements": "Mediciones",
      "nav.results": "Resultados",
      "nav.record": "Mi expediente",
      "nav.missions": "Misiones de salud",
      "rail.areas": "Áreas de salud",
      "rail.history": "Historia",
      "rail.history.sub": "Memoria longitudinal",
      "rail.safety": "Seguridad",
      "rail.safety.sub": "Señales y prioridades",
      "rail.results": "Resultados",
      "rail.results.sub": "Evidencia y explicación",
      "rail.followup": "Seguimiento",
      "rail.followup.sub": "Siguiente paso",
      "account.patient": "Paciente",
      "account.settings": "Cuenta y configuración",
      "account.open": "Cuenta y configuración",
      "top.preparing": "Preparando continuidad",
      "top.ready": "Lista cuando me necesites",
      "top.review": "Revisar continuidad",
      "top.context": "Mostrar u ocultar contexto",
      "chat.eyebrow": "HEALTHIA ONE · CONTINUIDAD PERSONAL",
      "chat.hero": "Tu salud no vuelve a empezar desde cero.",
      "chat.hero.body": "Cuéntame qué te pasa como se lo contarías a una persona. Uso tu memoria autorizada y pregunto solo lo que haga falta.",
      "chat.patient": "Paciente",
      "chat.signals": "Señales autorizadas",
      "chat.open_missions": "Misiones abiertas",
      "chat.prompt.bp": "Registrar presión",
      "chat.prompt.bp.sub": "Con técnica y contexto",
      "chat.prompt.results": "Explicar resultados",
      "chat.prompt.results.sub": "Con el archivo original",
      "chat.prompt.weight": "Revisar mi peso",
      "chat.prompt.weight.sub": "Tendencia y contexto",
      "chat.prompt.visit": "Preparar consulta",
      "chat.prompt.visit.sub": "Historia, documentos y dudas",
      "chat.input": "Cuéntame qué te pasa, pregunta por un resultado o registra algo…",
      "chat.attach": "Adjuntar resultado",
      "chat.voice": "Dictar mensaje",
      "chat.send": "Enviar",
      "chat.boundary": "HealthIA organiza y orienta con tus datos autorizados. No sustituye una evaluación profesional ni prescribe.",
      "today.kicker": "SEGUIMIENTO SOLICITADO O POR EVENTO",
      "today.title": "Hoy",
      "today.body": "Asuntos derivados de tus datos, eventos o revisiones que pediste.",
      "measure.kicker": "SEÑALES AUTORIZADAS",
      "measure.title": "Mediciones",
      "measure.body": "Registra datos con contexto; una tendencia vale más que una cifra aislada.",
      "measure.vitals": "＋ Presión y signos",
      "measure.weight": "＋ Peso",
      "measure.activity": "＋ Actividad",
      "results.kicker": "RESULTADOS CON EVIDENCIA",
      "results.title": "Resultados",
      "results.body": "Carga un estudio; HealthIA conserva el original, identifica lo que puede leer y lo vincula a tu memoria clínica.",
      "results.upload": "Cargar resultado",
      "results.formats": "JSON, CSV, TXT, PDF o imagen · máximo 5 MB",
      "record.kicker": "EXPEDIENTE DEL PACIENTE",
      "record.title": "Mi historia en un solo lugar",
      "record.body": "Datos confirmados, tratamiento registrado, alergias y señales que autorizaste.",
      "missions.kicker": "CONTINUIDAD Y SEGUIMIENTO",
      "missions.title": "Misiones de salud",
      "missions.body": "Asuntos vivos que permanecen abiertos hasta un siguiente paso o cierre verificable.",
      "context.kicker": "CONTEXTO AUTORIZADO",
      "context.title": "Tu salud ahora",
      "context.next": "Próxima acción",
      "context.active": "activo",
      "context.none": "Sin acciones pendientes.",
      "context.bp": "Última presión",
      "context.no_record": "Sin registro",
      "context.weight": "Peso",
      "context.no_trend": "Sin tendencia",
      "context.activity": "Actividad",
      "context.last": "Último registro",
      "context.treatment": "Tratamiento registrado",
      "context.missions": "Misiones activas",
      "context.boundary": "Límite clínico",
      "context.boundary.body": "Las posibilidades que explica HealthIA no son un diagnóstico confirmado. Medicación y decisiones clínicas requieren evaluación profesional.",
      "dialog.kicker": "REGISTRO DEL PACIENTE",
      "dialog.new": "Nueva medición",
      "dialog.close": "Cerrar",
      "dialog.cancel": "Cancelar",
      "dialog.save": "Guardar",
      "app.now": "ahora",
      "app.module": "Módulo de salud",
      "app.modules": "Ver módulos activados",
      "app.active_signals": "activas",
      "app.pulse": "pulso",
      "app.no_missions": "No hay misiones activas.",
      "app.all_quiet": "Todo tranquilo",
      "app.no_proactive": "No hay nuevas intervenciones por evento.",
      "app.bp": "Presión",
      "app.weight": "Peso",
      "app.patient_record": "Registro del paciente",
      "app.steps": "pasos",
      "app.active_minutes": "minutos activos",
      "app.no_measurements": "Sin mediciones.",
      "app.original": "Ver archivo original ↗",
      "app.twin_linked": "Gemelo clínico vinculado",
      "app.no_original": "Sin archivo original vinculado",
      "app.extracted": "datos extraídos",
      "app.no_results": "No has cargado resultados.",
      "app.modules_short": "módulos",
      "app.evidence_short": "evidencias",
      "app.no_missions_yet": "Las misiones aparecerán cuando HealthIA detecte o reciba un asunto de seguimiento.",
      "app.analyzing": "HealthIA analizando tu mensaje…",
      "app.ready": "Listo",
      "app.uploading": "HealthIA identificando y organizando el resultado…",
      "app.result_parsed": "Resultado interpretado, guardado y vinculado al gemelo clínico.",
      "app.result_pending": "Original guardado; análisis multimodal pendiente sin inventar hallazgos.",
      "app.saved": "Medición guardada.",
      "app.event_observation": "HealthIA tiene una nueva observación solicitada por un evento clínico.",
      "app.runtime_error": "HealthIA reportó un error auditable.",
      "app.reconnecting": "La conexión de eventos se reconectará automáticamente.",
      "app.reviewing": "HealthIA revisando continuidad…",
      "app.no_new": "No hay nuevas observaciones.",
      "app.new_count": "observaciones nuevas",
      "app.new_consult": "Nueva consulta lista para iniciar.",
      "app.local": "Modo local · sin API",
      "app.key_missing": "Gemini · falta configuración de API",
      "dialog.vital": "Registrar presión y signos",
      "dialog.weight": "Registrar peso",
      "dialog.activity": "Registrar actividad",
      "field.systolic": "Sistólica",
      "field.diastolic": "Diastólica",
      "field.pulse": "FC · lpm",
      "field.rr": "FR · rpm",
      "field.oxygen": "Oximetría · %",
      "field.temp": "Temperatura · °C",
      "field.glucose": "Glicemia · mg/dL",
      "field.cholesterol": "Colesterol · mg/dL",
      "field.symptoms": "Síntomas separados por coma",
      "field.weight": "Peso en kg",
      "field.note": "Contexto o nota",
      "field.steps": "Pasos",
      "field.minutes": "Minutos activos",
      "field.barrier": "Barrera o contexto",
      "auth.title": "HealthIA ONE · Iniciar sesión",
      "auth.eyebrow": "HEALTHIA ONE · CONTINUIDAD DEL PACIENTE",
      "auth.hero": "Tu salud debería recordarte.",
      "auth.hero.body": "Un espacio privado para tus conversaciones, resultados, dispositivos, misiones de salud y evidencia longitudinal.",
      "auth.point.private": "Datos por paciente",
      "auth.point.signed": "Sesión firmada",
      "auth.point.ondemand": "IA bajo demanda",
      "auth.live": "Continuidad que sobrevive al chat",
      "auth.live.body": "Evidencia original → gemelo clínico → misión de salud → seguimiento",
      "auth.login_tab": "Entrar",
      "auth.register_tab": "Crear cuenta",
      "auth.welcome": "Bienvenido",
      "auth.welcome.body": "Continúa tu línea de tiempo privada en HealthIA.",
      "auth.email": "Correo electrónico",
      "auth.password": "Contraseña",
      "auth.login": "Entrar a HealthIA",
      "auth.create": "Crear tu cuenta",
      "auth.create.body": "Empieza con un expediente vacío y construye tu propia continuidad.",
      "auth.name": "Nombre del paciente",
      "auth.password_hint": "Usa al menos 10 caracteres. La contraseña se almacena únicamente como hash scrypt con sal.",
      "auth.create_button": "Crear mi cuenta",
      "auth.boundary": "HealthIA no sustituye una evaluación profesional ni un servicio de emergencias.",
      "auth.checking": "Comprobando…"
    }
  };

  const supported = new Set(Object.keys(dictionaries));
  const canonical = value => {
    const raw = String(value || "").trim().replace("_", "-");
    if (!raw) return "en";
    const base = raw.split("-")[0].toLowerCase();
    return supported.has(base) ? base : "en";
  };

  function systemLocale() {
    const override = localStorage.getItem("healthia.locale");
    if (override && (override === "auto" || supported.has(canonical(override)))) {
      if (override !== "auto") return canonical(override);
    }
    const candidates = Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language || "en"];
    return canonical(candidates[0]);
  }

  let locale = systemLocale();

  function t(key, vars = {}) {
    const template = dictionaries[locale]?.[key] ?? dictionaries.en[key] ?? key;
    return String(template).replace(/\{(\w+)\}/g, (_, name) => vars[name] ?? `{${name}}`);
  }

  function apply(root = document) {
    document.documentElement.lang = locale;
    document.title = t("meta.title");
    const description = document.querySelector('meta[name="description"]');
    if (description) description.setAttribute("content", t("meta.description"));
    root.querySelectorAll?.("[data-i18n]").forEach(node => { node.textContent = t(node.dataset.i18n); });
    root.querySelectorAll?.("[data-i18n-placeholder]").forEach(node => { node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder)); });
    root.querySelectorAll?.("[data-i18n-aria]").forEach(node => { node.setAttribute("aria-label", t(node.dataset.i18nAria)); });
    root.querySelectorAll?.("[data-i18n-title]").forEach(node => { node.setAttribute("title", t(node.dataset.i18nTitle)); });
    document.dispatchEvent(new CustomEvent("healthia:locale-changed", {detail: {locale}}));
  }

  function setLocale(value) {
    locale = canonical(value);
    localStorage.setItem("healthia.locale", locale);
    apply();
    return locale;
  }

  function setAuto() {
    localStorage.setItem("healthia.locale", "auto");
    locale = systemLocale();
    apply();
    return locale;
  }

  function detectInputLocale(text, fallback = locale) {
    const sample = ` ${String(text || "").toLowerCase()} `;
    const spanishSignals = ["¿", "¡", "ñ", "á", "é", "í", "ó", "ú", " me ", " tengo ", " desde ", " dolor ", " resultados ", " quiero ", " mi ", " que "];
    const englishSignals = [" i ", " my ", " since ", " pain ", " results ", " want ", " have ", " what ", " today ", " please ", " help "];
    const score = signals => signals.reduce((total, signal) => total + (sample.includes(signal) ? 1 : 0), 0);
    const es = score(spanishSignals);
    const en = score(englishSignals);
    if (es >= 2 && es > en) return "es";
    if (en >= 2 && en > es) return "en";
    return canonical(fallback);
  }

  function browserLocaleTag() {
    return locale === "es" ? "es-DO" : "en-US";
  }

  window.HealthIAI18n = {
    t,
    apply,
    setLocale,
    setAuto,
    get locale() { return locale; },
    detectInputLocale,
    browserLocaleTag,
    supported: [...supported],
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => apply(), {once: true});
  else apply();
})();