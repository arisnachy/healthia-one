if (!window.__HEALTHIA_RUNTIME_INTEGRATIONS__) {
  window.__HEALTHIA_RUNTIME_INTEGRATIONS__ = true;

  (() => {
    const $ = selector => document.querySelector(selector);

    function toast(message) {
      const node = $("#toast");
      if (!node) return;
      node.textContent = message;
      node.hidden = false;
      clearTimeout(toast.timer);
      toast.timer = setTimeout(() => { node.hidden = true; }, 3600);
    }

    async function json(path, options = {}) {
      const response = await fetch(path, options);
      let payload = {};
      try { payload = await response.json(); } catch {}
      if (!response.ok) throw new Error(payload.detail || `Error ${response.status}`);
      return payload;
    }

    async function verifyGoogleAi() {
      const label = $("#runtimeLabel");
      if (!label) return;
      try {
        const readiness = await json("/api/readiness");
        if (readiness.llm_backend !== "gemini_api") {
          label.textContent = "Modo local · sin API";
          return;
        }
        if (!readiness.ai_ready) {
          label.textContent = "Gemini · falta API key";
          label.title = "Inicia con deployment/run-local-secure.ps1 y proporciona tu clave.";
          return;
        }
        label.textContent = `${readiness.model} · verificando Google AI…`;
        const result = await json("/api/ai/test", {method: "POST"});
        if (!result.ok) throw new Error(result.detail || result.status || "No disponible");
        label.textContent = `${result.model || readiness.model} · Google AI conectado`;
        label.title = result.sdk_version ? `google-genai ${result.sdk_version}` : "Google AI listo";
      } catch (error) {
        label.textContent = "Gemini · conexión pendiente";
        label.title = error.message;
      }
    }

    function setupRailReopen() {
      const shell = $("#app");
      const reopen = $("#expandLeft");
      const collapse = $("#collapseLeft");
      if (!shell || !reopen) return;
      const sync = () => {
        const collapsed = shell.classList.contains("left-collapsed");
        reopen.setAttribute("aria-expanded", String(!collapsed));
        reopen.title = collapsed ? "Abrir barra lateral" : "Barra lateral abierta";
      };
      reopen.addEventListener("click", () => requestAnimationFrame(sync));
      collapse?.addEventListener("click", () => requestAnimationFrame(sync));
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
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
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

    function init() {
      setupRailReopen();
      setupVoiceInput();
      verifyGoogleAi();
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init, {once: true});
    } else {
      init();
    }
  })();
}
