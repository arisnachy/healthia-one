(() => {
  const $ = selector => document.querySelector(selector);
  const i18n = window.HealthIAI18n;
  const t = key => i18n?.t(key) || key;
  const loginTab = $("#loginTab");
  const registerTab = $("#registerTab");
  const loginForm = $("#loginForm");
  const registerForm = $("#registerForm");

  function setMode(mode) {
    const registering = mode === "register";
    loginTab.classList.toggle("is-active", !registering);
    registerTab.classList.toggle("is-active", registering);
    loginForm.hidden = registering;
    registerForm.hidden = !registering;
    (registering ? registerForm : loginForm).querySelector("input")?.focus();
  }

  async function api(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json", "Accept-Language": i18n?.locale || "en"},
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Error ${response.status}`);
    return data;
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
  submit(loginForm, "/api/auth/login", "#loginError");
  submit(registerForm, "/api/auth/register", "#registerError");

  fetch("/api/auth/session", {headers: {"Accept-Language": i18n?.locale || "en"}})
    .then(response => response.json())
    .then(session => {
      if (session.authenticated) window.location.replace("/");
      registerTab.hidden = session.allow_registration === false;
    })
    .catch(() => {});
})();