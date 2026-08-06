if (!window.__HEALTHIA_PROVIDER_INTEGRATIONS__) {
  window.__HEALTHIA_PROVIDER_INTEGRATIONS__ = true;

  (() => {
    const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[char]));

    let catalog = null;
    let observer = null;

    const statusLabel = status => ({
      implemented: "Disponible",
      implemented_via_health_connect: "Disponible vía Health Connect",
      planned_optional_adapter: "Adaptador opcional planificado",
      planned_native_ios_bridge: "Puente iOS planificado",
      planned_oauth_adapter: "OAuth planificado",
      planned_partner_oauth_adapter: "Requiere programa del proveedor",
      planned_enterprise_adapter: "Integración institucional planificada",
    }[status] || status);

    const connectionLabel = mode => ({
      native_permission_and_pairing_code: "Permiso del teléfono + código",
      samsung_health_to_health_connect_to_healthia: "Samsung Health → Health Connect → HealthIA",
      native_samsung_permission: "Permiso nativo de Samsung Health",
      native_healthkit_permission: "Permiso nativo de Apple Health",
      oauth2: "Autorización OAuth del proveedor",
      partner_api_oauth: "API de socio + OAuth",
      oauth2_smart_on_fhir: "SMART on FHIR / OAuth",
    }[mode] || mode);

    const accountLabel = value => {
      if (value === "not_shared_with_healthia") return "No comparte la cuenta con HealthIA";
      if (value === "samsung_credentials_remain_inside_samsung_health") return "La cuenta Samsung permanece en Samsung Health";
      if (value === "apple_id_not_shared_with_healthia") return "El Apple ID permanece en Apple";
      if (value === "provider_login_via_oauth") return "Inicio de sesión en la página del proveedor";
      if (value === "organization_authorization_page") return "Autorización en la institución";
      return value;
    };

    async function loadCatalog() {
      if (catalog) return catalog;
      const response = await fetch("/api/devices");
      if (!response.ok) throw new Error(`Error ${response.status}`);
      const payload = await response.json();
      catalog = payload.provider_catalog || null;
      return catalog;
    }

    function renderCatalog() {
      const root = document.querySelector("#deviceRoot");
      if (!root || !catalog || root.querySelector("[data-provider-catalog]")) return;
      const providers = catalog.providers || [];
      const section = document.createElement("section");
      section.className = "provider-catalog";
      section.dataset.providerCatalog = "true";
      section.innerHTML = `
        <header class="provider-catalog-head">
          <div><small>ECOSISTEMA DE FUENTES</small><h2>Cómo se conecta cada plataforma</h2></div>
          <span>${esc(catalog.implemented_count || 0)} rutas disponibles</span>
        </header>
        <p class="provider-principle">${esc(catalog.principle || "")}</p>
        <div class="provider-grid">
          ${providers.map(provider => `
            <article class="provider-card" data-status="${esc(provider.status)}">
              <header><div><strong>${esc(provider.name)}</strong><small>${esc(provider.platform)}</small></div><span>${esc(statusLabel(provider.status))}</span></header>
              <p>${esc(provider.summary)}</p>
              <dl>
                <div><dt>Conexión</dt><dd>${esc(connectionLabel(provider.connection_mode))}</dd></div>
                <div><dt>Cuenta</dt><dd>${esc(accountLabel(provider.account_login))}</dd></div>
              </dl>
              <footer>${esc(provider.patient_step)}</footer>
            </article>`).join("")}
        </div>`;
      root.append(section);
    }

    function observeDeviceRoot() {
      const root = document.querySelector("#deviceRoot");
      if (!root) return;
      observer?.disconnect();
      observer = new MutationObserver(() => renderCatalog());
      observer.observe(root, {childList: true});
      renderCatalog();
    }

    async function boot() {
      try {
        await loadCatalog();
        observeDeviceRoot();
      } catch (error) {
        console.warn("HealthIA provider catalog unavailable", error);
      }
    }

    document.addEventListener("click", event => {
      const target = event.target.closest('[data-open="devices"], #refreshDevices, #demoDeviceSync');
      if (target) setTimeout(() => { observeDeviceRoot(); renderCatalog(); }, 500);
    });

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", boot, {once: true});
    } else {
      boot();
    }
  })();
}
