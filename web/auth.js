(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const i18n = window.HealthIAI18n;
  const t = key => i18n?.t(key) || key;
  const text = (en, es) => i18n?.locale === "es" ? es : en;
  const loginTab = $("#loginTab");
  const registerTab = $("#registerTab");
  const loginForm = $("#loginForm");
  const registerForm = $("#registerForm");
  const localeToggle = $("#localeToggle");

  const loginCopy = {
    en: {
      kicker: "SECURE ACCESS",
      hero: "Your health continues.",
      heroBody: "Results, evidence and follow-up in one place.",
      previewHello: "Hello, Ana",
      previewSub: "Your health continues.",
      missionLabel: "ACTIVE MISSION",
      missionValue: "Lab result",
      evidenceLabel: "EVIDENCE",
      evidenceValue: "Lipid profile",
      consentLabel: "CONSENT",
      consentValue: "Nearby resources",
      continuityLabel: "CONTINUITY",
      continuityValue: "Follow-up restored",
      security: "Protected session and patient-scoped data.",
      showPassword: "Show password",
      hidePassword: "Hide password",
      switchLanguage: "Cambiar a español",
    },
    es: {
      kicker: "ACCESO SEGURO",
      hero: "Tu salud continúa.",
      heroBody: "Resultados, evidencia y seguimiento en un solo lugar.",
      previewHello: "Hola, Ana",
      previewSub: "Tu salud continúa.",
      missionLabel: "MISIÓN ACTIVA",
      missionValue: "Resultado de laboratorio",
      evidenceLabel: "EVIDENCIA",
      evidenceValue: "Perfil lipídico",
      consentLabel: "CONSENTIMIENTO",
      consentValue: "Recursos cercanos",
      continuityLabel: "CONTINUIDAD",
      continuityValue: "Seguimiento recuperado",
      security: "Sesión protegida y datos aislados por paciente.",
      showPassword: "Mostrar contraseña",
      hidePassword: "Ocultar contraseña",
      switchLanguage: "Switch to English",
    },
  };

  function locale() {
    return i18n?.locale || "en";
  }

  function translatedLoginCopy() {
    const lang = locale();
    if (loginCopy[lang]) return loginCopy[lang];
    return {
      kicker: t("auth.login.kicker"), hero: t("auth.hero"), heroBody: t("auth.login.hero_body"),
      previewHello: t("auth.login.preview_hello"), previewSub: t("auth.login.preview_sub"),
      missionLabel: t("auth.login.mission_label"), missionValue: t("auth.login.mission_value"),
      evidenceLabel: t("auth.login.evidence_label"), evidenceValue: t("auth.login.evidence_value"),
      consentLabel: t("auth.login.consent_label"), consentValue: t("auth.login.consent_value"),
      continuityLabel: t("auth.login.continuity_label"), continuityValue: t("auth.login.continuity_value"),
      security: t("auth.login.security"), showPassword: t("auth.login.show_password"),
      hidePassword: t("auth.login.hide_password"), switchLanguage: "Use English",
    };
  }

  function applyLoginCopy() {
    const lang = locale();
    const copy = translatedLoginCopy();
    $$("[data-auth-copy]").forEach(node => {
      const value = copy[node.dataset.authCopy];
      if (value) node.textContent = value;
    });
    if (localeToggle) {
      localeToggle.textContent = lang === "en" ? "ES" : "EN";
      localeToggle.setAttribute("aria-label", copy.switchLanguage);
      localeToggle.title = copy.switchLanguage;
    }
    $$(".password-toggle").forEach(button => {
      const input = button.closest(".field-control")?.querySelector("input");
      const visible = input?.type === "text";
      button.setAttribute("aria-label", visible ? copy.hidePassword : copy.showPassword);
      button.title = visible ? copy.hidePassword : copy.showPassword;
    });
  }

  function setMode(mode) {
    const registering = mode === "register";
    document.body.dataset.authMode = registering ? "register" : "login";
    loginTab.classList.toggle("is-active", !registering);
    registerTab.classList.toggle("is-active", registering);
    loginTab.setAttribute("aria-selected", String(!registering));
    registerTab.setAttribute("aria-selected", String(registering));
    loginForm.hidden = registering;
    registerForm.hidden = !registering;
    (registering ? registerForm : loginForm).querySelector("input")?.focus();
  }

  async function api(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", "Accept-Language": i18n?.locale || "en"},
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Error ${response.status}`);
    return data;
  }

  async function authenticatedSession() {
    const response = await fetch("/api/auth/session", {
      credentials: "same-origin",
      headers: {"Accept-Language": i18n?.locale || "en"},
      cache: "no-store",
    });
    const session = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(session.detail || `Error ${response.status}`);
    return session;
  }

  function formPayload(form) {
    return Object.fromEntries(new FormData(form).entries());
  }

  function submit(form, path, errorSelector) {
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const error = $(errorSelector);
      const button = form.querySelector("button[type='submit']");
      const label = button.querySelector("span") || button;
      error.hidden = true;
      button.disabled = true;
      const original = label.textContent;
      label.textContent = t("auth.checking");
      try {
        await api(path, formPayload(form));
        const session = await authenticatedSession();
        if (!session.authenticated) {
          throw new Error(text(
            "The secure session could not be established. Please try again.",
            "No se pudo establecer la sesión segura. Inténtalo de nuevo."
          ));
        }
        window.location.replace("/");
      } catch (exc) {
        error.textContent = exc.message;
        error.hidden = false;
      } finally {
        button.disabled = false;
        label.textContent = original;
      }
    });
  }

  loginTab.addEventListener("click", () => setMode("login"));
  registerTab.addEventListener("click", () => setMode("register"));

  localeToggle?.addEventListener("click", () => {
    if (!i18n) return;
    i18n.setLocale(i18n.locale === "en" ? "es" : "en");
    applyLoginCopy();
  });

  $$(".password-toggle").forEach(button => {
    button.addEventListener("click", () => {
      const input = button.closest(".field-control")?.querySelector("input");
      if (!input) return;
      input.type = input.type === "password" ? "text" : "password";
      applyLoginCopy();
      input.focus();
    });
  });

  document.addEventListener("healthia:locale-changed", applyLoginCopy);
  applyLoginCopy();
  submit(loginForm, "/api/auth/login", "#loginError");
  submit(registerForm, "/api/auth/register", "#registerError");

  authenticatedSession()
    .then(session => {
      if (session.authenticated) window.location.replace("/");
      registerTab.hidden = session.allow_registration === false;
      if (session.allow_registration === false && document.body.dataset.authMode === "register") setMode("login");
    })
    .catch(() => {});
})();