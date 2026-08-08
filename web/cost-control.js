if (!window.__HEALTHIA_COST_CONTROL__) {
  window.__HEALTHIA_COST_CONTROL__ = true;

  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    let status = null;

    function ensureStylesheet() {
      if ($('link[data-cost-control-style]')) return;
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/assets/cost-control.css';
      link.dataset.costControlStyle = 'true';
      document.head.append(link);
    }

    function ensureUi() {
      const actions = $('.topbar-actions');
      if (!actions) return;
      if (!$('#costGuardButton')) {
        const button = document.createElement('button');
        button.id = 'costGuardButton';
        button.type = 'button';
        button.className = 'cost-guard-pill';
        button.addEventListener('click', openDialog);
        actions.prepend(button);
      }
      if (!$('#costGuardDialog')) {
        const dialog = document.createElement('dialog');
        dialog.id = 'costGuardDialog';
        dialog.className = 'cost-guard-dialog';
        dialog.innerHTML = `
          <form method="dialog" class="cost-guard-card">
            <header>
              <div><small>CONTROL DE CONSUMO</small><h2>Google AI bajo llave</h2></div>
              <button class="cost-close" value="cancel" aria-label="Cerrar">×</button>
            </header>
            <section class="cost-state">
              <div><span>Modo</span><strong id="costMode">—</strong></div>
              <div><span>Solicitudes usadas</span><strong id="costUsed">—</strong></div>
              <div><span>Restantes</span><strong id="costRemaining">—</strong></div>
              <div><span>Salida máxima</span><strong id="costTokens">—</strong></div>
            </section>
            <label class="cost-switch-row">
              <div><strong>Permitir llamadas a Google AI</strong><small id="costSwitchHelp">El modo local no genera llamadas facturables.</small></div>
              <span class="cost-switch"><input id="costGuardToggle" type="checkbox"><i></i></span>
            </label>
            <p id="costTruth" class="cost-truth"></p>
            <div class="cost-actions">
              <button id="costRefresh" type="button">Actualizar</button>
              <button id="costProbe" type="button" class="primary">Probar 1 solicitud</button>
            </div>
            <p id="costFeedback" class="cost-feedback" role="status"></p>
          </form>`;
        document.body.append(dialog);
        $('#costGuardToggle', dialog).addEventListener('change', event => setEnabled(event.target.checked));
        $('#costRefresh', dialog).addEventListener('click', loadStatus);
        $('#costProbe', dialog).addEventListener('click', runProbe);
      }
    }

    function modeLabel(value) {
      return ({local: 'Local seguro', guarded: 'Prueba controlada', cloud_demo: 'Demo Cloud'})[value] || value || 'Desconocido';
    }

    function renderRuntimeLabel() {
      const label = $('#runtimeLabel');
      if (!label || !status) return;
      if (status.mode === 'local') {
        label.textContent = 'Modo local · cero llamadas';
        label.dataset.aiState = 'off';
        label.title = 'La interfaz y los flujos deterministas funcionan sin consumir Google AI.';
        return;
      }
      if (!status.api_key_configured) {
        label.textContent = 'Gemini · falta clave';
        label.dataset.aiState = 'error';
        label.title = 'Reinicia con -GuardedAi y proporciona la clave mediante entrada protegida.';
        return;
      }
      label.textContent = status.enabled
        ? `${status.model} · IA controlada activa`
        : `${status.model} · IA controlada apagada`;
      label.dataset.aiState = status.enabled ? 'ready' : 'configured';
      label.title = status.enabled
        ? `Quedan ${status.requests_remaining} solicitudes antes del bloqueo automático.`
        : 'La clave está cargada, pero el control de costos impide llamadas hasta que lo actives.';
    }

    function render() {
      ensureUi();
      if (!status) return;
      const pill = $('#costGuardButton');
      const remaining = Number(status.requests_remaining || 0);
      pill.dataset.enabled = String(Boolean(status.enabled));
      pill.dataset.mode = status.mode || 'local';
      pill.textContent = status.mode === 'local'
        ? 'Local · 0 llamadas'
        : status.enabled
          ? `IA activa · ${remaining} restantes`
          : `IA apagada · ${remaining} restantes`;
      pill.title = 'Abrir control de consumo de Google AI';
      renderRuntimeLabel();

      $('#costMode').textContent = modeLabel(status.mode);
      $('#costUsed').textContent = `${status.requests_used || 0} / ${status.request_limit || 0}`;
      $('#costRemaining').textContent = String(remaining);
      $('#costTokens').textContent = `${status.max_output_tokens || 0} tokens`;
      $('#costTruth').textContent = status.truth_boundary || '';

      const toggle = $('#costGuardToggle');
      toggle.checked = Boolean(status.enabled);
      toggle.disabled = !status.mutable || !status.api_key_configured || !status.ui_control_available || remaining <= 0;
      $('#costSwitchHelp').textContent = status.mode === 'local'
        ? 'Reinicia con -GuardedAi para cargar una clave sin activar consumo.'
        : !status.api_key_configured
          ? 'No hay una clave configurada en este proceso.'
          : status.mutable
            ? 'Puedes apagarlo en cualquier momento. Al llegar al límite se apaga solo.'
            : 'En Cloud el modo se fija al desplegar y no puede cambiarse desde el navegador.';
      $('#costProbe').disabled = !status.enabled || remaining <= 0;
    }

    async function requestJson(url, options = {}) {
      const response = await (window.healthiaFetch || fetch)(url, options);
      let payload = {};
      try { payload = await response.json(); } catch {}
      if (!response.ok) throw new Error(payload.detail || `Error ${response.status}`);
      return payload;
    }

    async function loadStatus() {
      try {
        status = await requestJson('/api/cost-control');
        render();
        const feedback = $('#costFeedback');
        if (feedback) feedback.textContent = '';
      } catch (error) {
        const feedback = $('#costFeedback');
        if (feedback) feedback.textContent = error.message;
      }
    }

    async function setEnabled(enabled) {
      const toggle = $('#costGuardToggle');
      toggle.disabled = true;
      try {
        status = await requestJson(`/api/cost-control?enabled=${enabled ? 'true' : 'false'}`, {method: 'POST'});
        $('#costFeedback').textContent = enabled
          ? 'Google AI activado dentro del límite de esta ejecución.'
          : 'Google AI apagado. El flujo determinista continúa funcionando.';
      } catch (error) {
        $('#costFeedback').textContent = error.message;
        await loadStatus();
      }
      render();
    }

    async function runProbe() {
      const button = $('#costProbe');
      button.disabled = true;
      $('#costFeedback').textContent = 'Ejecutando una solicitud real y descontándola del límite…';
      try {
        const result = await requestJson('/api/ai/test', {method: 'POST'});
        $('#costFeedback').textContent = result.ok
          ? 'Prueba completada. La solicitud quedó contabilizada.'
          : `Prueba no completada: ${result.detail || result.status}`;
      } catch (error) {
        $('#costFeedback').textContent = error.message;
      }
      await loadStatus();
    }

    async function openDialog() {
      ensureUi();
      await loadStatus();
      $('#costGuardDialog')?.showModal();
    }

    async function boot() {
      ensureStylesheet();
      ensureUi();
      await loadStatus();
      setInterval(loadStatus, 15000);
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot, {once: true});
    } else {
      boot();
    }
    document.addEventListener('healthia:ui-updated', () => setTimeout(loadStatus, 80));
  })();
}
