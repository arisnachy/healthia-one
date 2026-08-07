if (!window.__HEALTHIA_RUNTIME_INTEGRATIONS__) {
  window.__HEALTHIA_RUNTIME_INTEGRATIONS__ = true;

  (() => {
    const $ = selector => document.querySelector(selector);
    const APK_WORKFLOW_URL = "https://github.com/arisnachy/healthia-one/actions/workflows/android-bridge.yml";
    const ANDROID_GUIDE_URL = "https://github.com/arisnachy/healthia-one/blob/main/docs/CONNECT_ANDROID.md";
    const ANDROID_SOURCE_URL = "https://github.com/arisnachy/healthia-one/tree/main/android-health-bridge";

    function toast(message) {
      const node = $("#toast");
      if (!node) return;
      node.textContent = message;
      node.hidden = false;
      clearTimeout(toast.timer);
      toast.timer = setTimeout(() => { node.hidden = true; }, 4200);
    }

    async function json(path, options = {}) {
      const response = await (window.healthiaFetch || fetch)(path, options);
      let payload = {};
      try { payload = await response.json(); } catch {}
      if (!response.ok) throw new Error(payload.detail || `Error ${response.status}`);
      return payload;
    }

    function friendlyAiError(value) {
      const text = String(value || "");
      if (/429|resource_exhausted|quota/i.test(text)) return "La cuota de Google AI está agotada por ahora.";
      if (/401|403|api.?key|permission|unauth/i.test(text)) return "La clave de Google AI es inválida o no tiene acceso al modelo.";
      if (/not_configured|falta configurar/i.test(text)) return "Google AI no está configurado en este proceso.";
      if (/model|not found|404/i.test(text)) return "El modelo configurado no está disponible para esta clave.";
      return "Google AI no respondió. Revisa el detalle en la terminal.";
    }

    function setAiState(label, text, state, title) {
      if (!label) return;
      label.textContent = text;
      label.dataset.aiState = state;
      label.title = title || text;
    }

    async function loadGoogleAiState() {
      const label = $("#runtimeLabel");
      if (!label) return;
      try {
        const readiness = await json("/api/readiness");
        if (readiness.llm_backend !== "gemini_api") {
          setAiState(label, "Modo local · sin API", "off", "Iniciado con -Mock. Haz clic para revisar el estado.");
          return;
        }
        if (!readiness.ai_ready) {
          setAiState(label, "Gemini · falta API key", "error", "Inicia con deployment/run-local-secure.ps1 y proporciona la clave mediante entrada protegida.");
          return;
        }
        setAiState(
          label,
          `${readiness.model} · clave detectada`,
          "configured",
          "El lanzador verifica una solicitud real al iniciar. Haz clic aquí para repetir la prueba.",
        );
      } catch (error) {
        setAiState(label, "Gemini · sin estado", "error", error.message);
      }
    }

    async function verifyGoogleAi(announce = true) {
      const label = $("#runtimeLabel");
      if (!label) return;
      setAiState(label, "Gemini · probando…", "checking", "Ejecutando una solicitud mínima real.");
      try {
        const result = await json("/api/ai/test", {method: "POST"});
        if (!result.ok) throw new Error(result.detail || result.status || "No disponible");
        setAiState(
          label,
          `${result.model} · Google AI activo`,
          "ready",
          `Solicitud real completada · google-genai ${result.sdk_version || "—"} · store=false`,
        );
        if (announce) toast("Google AI respondió a una solicitud real. El chat está usando el modelo configurado.");
      } catch (error) {
        setAiState(label, "Gemini · revisar", "error", error.message);
        if (announce) toast(friendlyAiError(error.message));
      }
    }

    function setupGoogleAiControl() {
      const label = $("#runtimeLabel");
      if (!label) return;
      label.classList.add("runtime-ai-control");
      label.setAttribute("role", "button");
      label.setAttribute("tabindex", "0");
      label.setAttribute("aria-label", "Probar conexión real con Google AI");
      label.addEventListener("click", () => verifyGoogleAi(true));
      label.addEventListener("keydown", event => {
        if (!["Enter", " "].includes(event.key)) return;
        event.preventDefault();
        verifyGoogleAi(true);
      });
      loadGoogleAiState();
    }

    function setupRailReopen() {
      const shell = $("#app");
      const reopen = $("#expandLeft");
      const collapse = $("#collapseLeft");
      if (!shell || !reopen) return;
      reopen.textContent = "›";
      const sync = () => {
        const collapsed = shell.classList.contains("left-collapsed");
        reopen.setAttribute("aria-expanded", String(!collapsed));
        reopen.title = collapsed ? "Abrir barra lateral" : "Barra lateral abierta";
        reopen.setAttribute("aria-label", collapsed ? "Abrir barra lateral" : "Barra lateral abierta");
      };
      reopen.addEventListener("click", () => requestAnimationFrame(sync));
      collapse?.addEventListener("click", () => requestAnimationFrame(sync));
      document.addEventListener("keydown", event => {
        if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "b") return;
        event.preventDefault();
        shell.classList.toggle("left-collapsed");
        sync();
      });
      sync();
    }

    function setupVoiceInput() {
      const button = $("#voiceButton");
      const input = $("#chatInput");
      if (!button || !input) return;

      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) {
        button.title = "El dictado no está disponible en este navegador";
        button.addEventListener("click", () => toast("El dictado de voz no está disponible en este navegador."));
        return;
      }

      const recognition = new Recognition();
      recognition.lang = navigator.language?.startsWith("es") ? navigator.language : "es-DO";
      recognition.continuous = false;
      recognition.interimResults = true;
      let listening = false;
      let prefix = "";

      const setListening = active => {
        listening = active;
        button.classList.toggle("is-listening", active);
        button.setAttribute("aria-pressed", String(active));
        button.setAttribute("aria-label", active ? "Detener dictado" : "Dictar mensaje");
        button.title = active ? "Detener dictado" : "Dictar mensaje";
      };

      recognition.onstart = () => {
        prefix = input.value.trim();
        setListening(true);
      };
      recognition.onresult = event => {
        let transcript = "";
        for (let index = 0; index < event.results.length; index += 1) {
          transcript += event.results[index][0]?.transcript || "";
        }
        input.value = [prefix, transcript.trim()].filter(Boolean).join(prefix ? " " : "");
        input.dispatchEvent(new Event("input", {bubbles: true}));
      };
      recognition.onerror = event => {
        const message = event.error === "not-allowed"
          ? "Permite el micrófono en el navegador para usar el dictado."
          : `No pude iniciar el dictado (${event.error || "error"}).`;
        toast(message);
      };
      recognition.onend = () => setListening(false);

      button.addEventListener("click", () => {
        try {
          if (listening) recognition.stop();
          else recognition.start();
        } catch (error) {
          toast(error.message || "No pude iniciar el dictado.");
          setListening(false);
        }
      });
    }

    function enhanceDeviceConnection() {
      const connect = $("#connectDevice");
      if (connect) {
        connect.textContent = "Conectar teléfono o reloj";
        connect.title = "Instalar el puente Android, generar un código y autorizar Health Connect";
      }

      const dialog = $("#deviceConnectDialog");
      if (!dialog || dialog.dataset.connectionEnhanced === "true") return Boolean(dialog);
      dialog.dataset.connectionEnhanced = "true";

      const actions = dialog.querySelector(".pairing-actions");
      if (actions) {
        const existing = actions.querySelector("a");
        if (existing) {
          existing.href = APK_WORKFLOW_URL;
          existing.textContent = "Descargar APK de prueba ↗";
        }
        actions.insertAdjacentHTML(
          "beforeend",
          `<a href="${ANDROID_GUIDE_URL}" target="_blank" rel="noreferrer">Guía paso a paso ↗</a>` +
          `<a href="${ANDROID_SOURCE_URL}" target="_blank" rel="noreferrer">Código Android ↗</a>`,
        );
      }

      const firstStep = dialog.querySelector(".device-connect-steps article:first-child p");
      if (firstStep) {
        firstStep.textContent = "Abre Descargar APK de prueba, entra en la ejecución más reciente y baja el artefacto HealthIA-Bridge-debug.";
      }

      const panel = dialog.querySelector(".pairing-panel");
      if (panel && !dialog.querySelector(".lan-help")) {
        panel.insertAdjacentHTML(
          "beforebegin",
          '<div class="lan-help"><strong>Teléfono y computadora en la misma Wi‑Fi</strong><span>El teléfono no puede usar 127.0.0.1. Usa la dirección LAN que imprime el lanzador, por ejemplo http://192.168.1.25:8000.</span></div>',
        );
      }
      return true;
    }

    function setupDeviceConnection() {
      enhanceDeviceConnection();
      [120, 350, 800, 1600].forEach(delay => setTimeout(enhanceDeviceConnection, delay));
      document.addEventListener("click", event => {
        const target = event.target.closest?.('[data-open="devices"], #connectDevice');
        if (target) requestAnimationFrame(() => setTimeout(enhanceDeviceConnection, 0));
      });
    }

    function init() {
      setupRailReopen();
      setupVoiceInput();
      setupGoogleAiControl();
      setupDeviceConnection();
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init, {once: true});
    } else {
      init();
    }
  })();
}
