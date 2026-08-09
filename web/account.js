if (!window.__HEALTHIA_ACCOUNT__) {
  window.__HEALTHIA_ACCOUNT__ = true;
  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
    const i18n = window.HealthIAI18n;
    const text = (en, es) => i18n?.locale === "es" ? es : en;
    let session = null;

    async function api(path, options = {}) {
      const headers = new Headers(options.headers || {});
      headers.set("Accept-Language", i18n?.locale || "en");
      const response = await fetch(path, {...options, headers});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `Error ${response.status}`);
      return payload;
    }

    function openView(view) {
      const button = document.querySelector(`.main-nav [data-open="${view}"]`) || document.querySelector(`[data-open="${view}"]`);
      if (button) button.click();
    }

    function ensureDialog() {
      if ($("#accountDialog")) return;
      document.body.insertAdjacentHTML("beforeend", `
        <dialog id="accountDialog" class="health-os-dialog account-dialog">
          <div class="device-connect-shell">
            <header><div><small>${text("PATIENT ACCOUNT", "CUENTA DEL PACIENTE")}</small><h2>${text("Account & settings", "Cuenta y configuración")}</h2></div><button id="closeAccountDialog" type="button" aria-label="${text("Close", "Cerrar")}">×</button></header>
            <div id="accountIdentity" class="account-identity"></div>
            <div class="device-connect-steps account-settings-list">
              <button type="button" data-account-view="profile"><span>1</span><div><strong>${text("Health profile", "Perfil de salud")}</strong><p>${text("General information, history, habits and reproductive health.", "Datos generales, antecedentes, hábitos y salud reproductiva.")}</p></div></button>
              <button type="button" data-account-view="control"><span>2</span><div><strong>${text("Permissions & privacy", "Permisos y privacidad")}</strong><p>${text("Authorized signals, pauses, audit and export.", "Señales autorizadas, pausas, auditoría y exportación.")}</p></div></button>
              <button type="button" data-account-view="devices"><span>3</span><div><strong>${text("Devices", "Dispositivos")}</strong><p>${text("Health Connect connections and authorized synchronization.", "Conexiones Health Connect y sincronización autorizada.")}</p></div></button>
            </div>
            <div class="pairing-actions account-actions">
              <button id="logoutButton" type="button">${text("Sign out", "Cerrar sesión")}</button>
              <button id="closeAccountButton" type="button">${text("Back to HealthIA", "Volver a HealthIA")}</button>
            </div>
          </div>
        </dialog>`);
      $("#closeAccountDialog")?.addEventListener("click", () => $("#accountDialog")?.close());
      $("#closeAccountButton")?.addEventListener("click", () => $("#accountDialog")?.close());
      document.querySelectorAll("[data-account-view]").forEach(button => button.addEventListener("click", () => {
        $("#accountDialog")?.close();
        openView(button.dataset.accountView);
      }));
      $("#logoutButton")?.addEventListener("click", async () => {
        const button = $("#logoutButton");
        button.disabled = true;
        button.textContent = text("Signing out…", "Cerrando sesión…");
        try {
          await api("/api/auth/logout", {method: "POST"});
          window.location.replace("/login");
        } catch (error) {
          button.disabled = false;
          button.textContent = text("Sign out", "Cerrar sesión");
        }
      });
    }

    function renderSession() {
      const identity = $("#accountIdentity");
      const logout = $("#logoutButton");
      if (!identity) return;
      if (session?.authenticated && session.account) {
        identity.innerHTML = `<strong>${esc(session.account.display_name)}</strong><span>${esc(session.account.email)}</span><small>${text("Patient-scoped record · session", "Expediente separado · sesión")} ${esc(session.credential_persistence)}</small>`;
        if (logout) logout.hidden = false;
      } else {
        identity.innerHTML = `<strong>${text("Local demo mode", "Modo demo local")}</strong><span>${text("No authenticated account", "Sin cuenta autenticada")}</span><small>${text("Use secure startup to test login and patient isolation.", "Activa el arranque seguro para probar login y aislamiento.")}</small>`;
        if (logout) logout.hidden = true;
      }
    }

    function protectAuthenticatedNewConsultation() {
      const button = $("#newConsultation");
      if (!button) return;
      if (session?.authenticated) button.dataset.recordPreserving = "true";
    }

    async function boot() {
      ensureDialog();
      try { session = await api("/api/auth/session"); } catch { session = null; }
      renderSession();
      protectAuthenticatedNewConsultation();
      const pill = $("#accountPill");
      pill?.addEventListener("click", () => {
        renderSession();
        $("#accountDialog")?.showModal();
      });
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once: true});
    else boot();
  })();
}
