if (!window.__HEALTHIA_ACCOUNT__) {
  window.__HEALTHIA_ACCOUNT__ = true;
  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
    let session = null;

    async function api(path, options = {}) {
      const response = await fetch(path, options);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `Error ${response.status}`);
      return payload;
    }

    function openView(view) {
      const button = document.querySelector(`[data-open="${view}"]`);
      if (button) button.click();
    }

    function ensureDialog() {
      if ($("#accountDialog")) return;
      document.body.insertAdjacentHTML("beforeend", `
        <dialog id="accountDialog" class="health-os-dialog account-dialog">
          <div class="device-connect-shell">
            <header><div><small>CUENTA DEL PACIENTE</small><h2>Cuenta y configuración</h2></div><button id="closeAccountDialog" type="button">×</button></header>
            <div id="accountIdentity" class="account-identity"></div>
            <div class="device-connect-steps account-settings-list">
              <button type="button" data-account-view="profile"><span>1</span><div><strong>Perfil de salud</strong><p>Datos generales, antecedentes, hábitos y salud reproductiva.</p></div></button>
              <button type="button" data-account-view="control"><span>2</span><div><strong>Permisos y privacidad</strong><p>Señales autorizadas, pausas, auditoría y exportación.</p></div></button>
              <button type="button" data-account-view="devices"><span>3</span><div><strong>Dispositivos</strong><p>Conexiones Health Connect y sincronización autorizada.</p></div></button>
            </div>
            <div class="pairing-actions account-actions">
              <button id="logoutButton" type="button">Cerrar sesión</button>
              <button id="closeAccountButton" type="button">Volver a HealthIA</button>
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
        button.textContent = "Cerrando sesión…";
        try {
          await api("/api/auth/logout", {method: "POST"});
          window.location.replace("/login");
        } catch (error) {
          button.disabled = false;
          button.textContent = "Cerrar sesión";
        }
      });
    }

    function renderSession() {
      const identity = $("#accountIdentity");
      const logout = $("#logoutButton");
      if (!identity) return;
      if (session?.authenticated && session.account) {
        identity.innerHTML = `<strong>${esc(session.account.display_name)}</strong><span>${esc(session.account.email)}</span><small>Expediente separado · sesión ${esc(session.credential_persistence)}</small>`;
        if (logout) logout.hidden = false;
      } else {
        identity.innerHTML = `<strong>Modo demo local</strong><span>Sin cuenta autenticada</span><small>Activa el arranque seguro para probar login y aislamiento.</small>`;
        if (logout) logout.hidden = true;
      }
    }

    async function boot() {
      ensureDialog();
      try { session = await api("/api/auth/session"); } catch { session = null; }
      renderSession();
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