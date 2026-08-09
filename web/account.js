if (!window.__HEALTHIA_ACCOUNT__) {
  window.__HEALTHIA_ACCOUNT__ = true;
  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
    const i18n = window.HealthIAI18n;
    const text = (en, es) => i18n?.locale === "es" ? es : en;
    let session = null;
    let googleState = {readiness:null, connection:null};

    async function api(path, options = {}) {
      const headers = new Headers(options.headers || {});
      headers.set("Accept-Language", i18n?.locale || "en");
      const response = await fetch(path, {...options, headers});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `Error ${response.status}`);
      return payload;
    }

    function toast(message) {
      const node = $("#toast");
      if (!node) return;
      node.textContent = message;
      node.hidden = false;
      clearTimeout(toast.timer);
      toast.timer = setTimeout(() => { node.hidden = true; }, 4200);
    }

    function openView(view) {
      const button = document.querySelector(`.main-nav [data-open="${view}"]`) || document.querySelector(`[data-open="${view}"]`);
      if (button) button.click();
    }

    function googleScopeSummary(scopes = []) {
      const normalized = scopes.map(value => String(value).toLowerCase());
      const labels = [];
      if (normalized.some(value => value.includes("gmail"))) labels.push("Gmail");
      if (normalized.some(value => value.includes("calendar"))) labels.push("Calendar");
      if (normalized.some(value => value.includes("tasks"))) labels.push("Tasks");
      if (normalized.some(value => value.includes("contacts"))) labels.push("Contacts");
      if (normalized.some(value => value.includes("drive"))) labels.push("Drive");
      if (normalized.some(value => value.includes("youtube"))) labels.push("YouTube");
      return labels.join(" · ");
    }

    async function loadGoogleState() {
      try {
        const [readiness, capabilities] = await Promise.all([
          api("/api/google-constellation/oauth/readiness"),
          api("/api/google-constellation/capabilities"),
        ]);
        googleState = {
          readiness,
          connection: capabilities?.google_account_connection || null,
        };
      } catch {
        googleState = {readiness:null, connection:null};
      }
      renderGoogleConnection();
      return googleState;
    }

    function renderGoogleConnection() {
      const root = $("#googleAccountConnection");
      if (!root) return;
      const readiness = googleState.readiness;
      const connection = googleState.connection;
      const connected = Boolean(connection?.connected);
      const configured = readiness?.ready === true;
      const scopes = googleScopeSummary(connection?.granted_scopes || []);
      root.dataset.connected = String(connected);
      root.dataset.ready = String(configured);
      if (connected) {
        root.innerHTML = `
          <div class="account-google-status">
            <div><strong>${text("Google connected", "Google conectado")}</strong><span>${esc(connection.google_account || "")}</span>${scopes ? `<small>${esc(scopes)}</small>` : ""}</div>
            <span class="account-google-state">${text("Available for authorized missions", "Disponible para misiones autorizadas")}</span>
          </div>
          <div class="pairing-actions account-google-actions">
            <button id="disconnectGoogleAccount" type="button">${text("Disconnect Google", "Desconectar Google")}</button>
          </div>`;
        $("#disconnectGoogleAccount")?.addEventListener("click", disconnectGoogle);
        return;
      }
      if (configured) {
        root.innerHTML = `
          <div class="account-google-status">
            <div><strong>${text("Google not connected", "Google no conectado")}</strong><span>${text("Connect only when a mission needs Gmail, Calendar or Tasks.", "Conecta sólo cuando una misión necesite Gmail, Calendar o Tasks.")}</span></div>
            <span class="account-google-state">${text("Incremental permissions", "Permisos incrementales")}</span>
          </div>
          <div class="pairing-actions account-google-actions">
            <button id="connectGoogleAccount" type="button">${text("Connect Google", "Conectar Google")}</button>
          </div>`;
        $("#connectGoogleAccount")?.addEventListener("click", () => {
          window.location.assign("/api/google-constellation/oauth/connect");
        });
        return;
      }
      root.innerHTML = `
        <div class="account-google-status">
          <div><strong>${text("Google connection unavailable", "Conexión Google no disponible")}</strong><span>${text("HealthIA is not provisioned for patient Google OAuth yet.", "HealthIA aún no está provisionado para OAuth de Google del paciente.")}</span></div>
          <span class="account-google-state">${text("No secret material is exposed", "No se exponen secretos")}</span>
        </div>`;
    }

    async function disconnectGoogle() {
      const button = $("#disconnectGoogleAccount");
      if (button) {
        button.disabled = true;
        button.textContent = text("Disconnecting…", "Desconectando…");
      }
      try {
        const result = await api("/api/google-constellation/oauth/disconnect", {method:"POST"});
        googleState.connection = {connected:false, google_account:"", granted_scopes:[]};
        renderGoogleConnection();
        toast(result.google_grant_revoked === false
          ? text("Google disconnected from HealthIA. Provider-side Google access can be revoked separately in your Google Account.", "Google fue desconectado de HealthIA. El acceso del proveedor también puede revocarse por separado en tu Cuenta de Google.")
          : text("Google disconnected.", "Google desconectado."));
      } catch (error) {
        toast(error.message || text("Could not disconnect Google.", "No se pudo desconectar Google."));
        renderGoogleConnection();
      }
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
            <section class="account-google-section" aria-labelledby="googleAccountHeading">
              <header><small>${text("GOOGLE ECOSYSTEM", "ECOSISTEMA GOOGLE")}</small><h3 id="googleAccountHeading">${text("Mission connection", "Conexión para misiones")}</h3></header>
              <div id="googleAccountConnection"><span>${text("Checking Google connection…", "Verificando conexión Google…")}</span></div>
            </section>
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

    async function openGoogleConnectionSurface() {
      ensureDialog();
      renderSession();
      await loadGoogleState();
      const dialog = $("#accountDialog");
      if (dialog && !dialog.open) dialog.showModal();
      requestAnimationFrame(() => {
        $("#googleAccountConnection")?.scrollIntoView({block:"center", behavior:"smooth"});
      });
    }

    function handleGoogleReturn() {
      const params = new URLSearchParams(window.location.search);
      if (params.get("google") !== "connected") return;
      history.replaceState({}, "", `${window.location.pathname}${window.location.hash || ""}`);
      setTimeout(async () => {
        await openGoogleConnectionSurface();
        toast(text("Google connected to HealthIA for authorized missions.", "Google fue conectado a HealthIA para misiones autorizadas."));
      }, 0);
    }

    async function boot() {
      ensureDialog();
      try { session = await api("/api/auth/session"); } catch { session = null; }
      renderSession();
      protectAuthenticatedNewConsultation();
      await loadGoogleState();
      handleGoogleReturn();
      const pill = $("#accountPill");
      pill?.addEventListener("click", async () => {
        renderSession();
        await loadGoogleState();
        $("#accountDialog")?.showModal();
      });
    }

    document.addEventListener("healthia:open-google-connection", () => {
      openGoogleConnectionSurface().catch(error => {
        toast(error.message || text("Could not open Google connection controls.", "No se pudieron abrir los controles de conexión de Google."));
      });
    });

    document.addEventListener("healthia:locale-changed", () => {
      renderSession();
      renderGoogleConnection();
    });

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once: true});
    else boot();
  })();
}
