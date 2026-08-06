if (!window.__HEALTHIA_CONNECTIVITY__) {
  window.__HEALTHIA_CONNECTIVITY__ = true;
  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const WORKFLOW_URL = "https://github.com/arisnachy/healthia-one/actions/workflows/android-bridge.yml";
    const GUIDE_URL = "https://github.com/arisnachy/healthia-one/blob/main/docs/CONNECT_ANDROID.md";
    const SOURCE_URL = "https://github.com/arisnachy/healthia-one/tree/main/android-health-bridge";

    async function api(path, options = {}) {
      const response = await fetch(path, options);
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

    function friendlyAiError(value) {
      const text = String(value || "");
      if (/429|resource_exhausted|quota/i.test(text)) return "La cuota de Google AI está agotada por ahora.";
      if (/401|403|api.?key|permission|unauth/i.test(text)) return "La clave de Google AI es inválida o no tiene acceso al modelo.";
      if (/not_configured|falta configurar/i.test(text)) return "Google AI no está configurado en este proceso.";
      return "Google AI no respondió. Revisa la terminal para ver el detalle técnico.";
    }

    function setAiButton(button, label, state) {
      if (!button) return;
      button.dataset.state = state;
      button.innerHTML = `<span class="ai-live-dot" aria-hidden="true"></span><span>${label}</span>`;
    }

    function installAiControl() {
      const actions = $(".topbar-actions");
      if (!actions || $("#googleAiCheck")) return;
      const button = document.createElement("button");
      button.id = "googleAiCheck";
      button.type = "button";
      button.className = "ai-status-button";
      button.title = "Ejecutar una solicitud real y mínima con Google AI";
      setAiButton(button, "Google AI · comprobando", "checking");
      actions.prepend(button);

      button.addEventListener("click", async () => {
        button.disabled = true;
        setAiButton(button, "Google AI · probando", "checking");
        try {
          const result = await api("/api/ai/test", {method: "POST"});
          if (!result.ok) throw new Error(result.error || result.status);
          setAiButton(button, `${result.model} · activo`, "ready");
          toast("Google AI respondió a una solicitud real. El chat está usando el modelo configurado.");
        } catch (error) {
          setAiButton(button, "Google AI · revisar", "error");
          toast(friendlyAiError(error.message));
        } finally {
          button.disabled = false;
        }
      });

      api("/api/readiness").then(readiness => {
        if (readiness.llm_backend !== "gemini_api") {
          setAiButton(button, "Google AI · modo local", "off");
        } else if (readiness.ai_ready) {
          setAiButton(button, "Google AI · clave detectada", "configured");
        } else {
          setAiButton(button, "Google AI · falta clave", "error");
        }
      }).catch(() => setAiButton(button, "Google AI · sin estado", "error"));
    }

    function installRailHandle() {
      const expand = $("#expandLeft");
      if (!expand) return;
      expand.textContent = "›";
      expand.title = "Expandir menú lateral";
      expand.setAttribute("aria-label", "Expandir menú lateral");

      document.addEventListener("keydown", event => {
        if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "b") return;
        event.preventDefault();
        const shell = $("#app");
        if (!shell) return;
        shell.classList.toggle("left-collapsed");
        expand.setAttribute("aria-hidden", String(!shell.classList.contains("left-collapsed")));
      });
    }

    function enhanceDeviceDialog() {
      const dialog = $("#deviceConnectDialog");
      if (!dialog || dialog.dataset.installerReady === "true") return false;
      dialog.dataset.installerReady = "true";

      const actions = $(".pairing-actions", dialog);
      if (actions) {
        const existingLink = $("a", actions);
        if (existingLink) {
          existingLink.href = WORKFLOW_URL;
          existingLink.textContent = "Descargar APK de prueba ↗";
        }
        if (!$("[data-android-guide]", actions)) {
          actions.insertAdjacentHTML(
            "beforeend",
            `<a data-android-guide href="${GUIDE_URL}" target="_blank" rel="noreferrer">Guía paso a paso ↗</a>` +
            `<a data-android-source href="${SOURCE_URL}" target="_blank" rel="noreferrer">Código Android ↗</a>`,
          );
        }
      }

      const steps = $(".device-connect-steps", dialog);
      if (steps && !$("[data-apk-step]", steps)) {
        steps.firstElementChild?.setAttribute("data-apk-step", "true");
        const firstParagraph = $("article:first-child p", steps);
        if (firstParagraph) {
          firstParagraph.textContent = "Abre Descargar APK de prueba, entra en la ejecución más reciente y baja el artefacto HealthIA-Bridge-debug.";
        }
      }

      const panel = $(".pairing-panel", dialog);
      if (panel && !$(".lan-help", dialog)) {
        panel.insertAdjacentHTML(
          "beforebegin",
          '<div class="lan-help"><strong>Teléfono y computadora en la misma Wi‑Fi</strong><span>El teléfono no puede usar 127.0.0.1. Escribe una dirección como http://192.168.1.25:8000.</span></div>',
        );
      }
      return true;
    }

    function enhanceDevicePage() {
      const connect = $("#connectDevice");
      if (connect) {
        connect.textContent = "Conectar teléfono o reloj";
        connect.title = "Instalar el puente Android, generar un código y autorizar Health Connect";
      }
      enhanceDeviceDialog();
    }

    function boot() {
      installAiControl();
      installRailHandle();
      enhanceDevicePage();
      [120, 350, 800, 1600].forEach(delay => setTimeout(enhanceDevicePage, delay));
      document.addEventListener("click", event => {
        const target = event.target.closest('[data-open="devices"], #connectDevice');
        if (target) requestAnimationFrame(() => setTimeout(enhanceDevicePage, 0));
      });
    }

    if (document.readyState === "loading") {
      window.addEventListener("DOMContentLoaded", boot, {once: true});
    } else {
      boot();
    }
  })();
}
