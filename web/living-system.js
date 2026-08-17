(() => {
  "use strict";
  const $ = selector => document.querySelector(selector);
  const refs = {
    accessPanel: $("#accessPanel"), accessForm: $("#accessForm"), accessKey: $("#accessKey"),
    controlPanel: $("#controlPanel"), activate: $("#activateButton"), replay: $("#replayButton"),
    runtime: $("#runtime"), error: $("#errorBanner"), status: $("#systemStatus"),
    twinVersion: $("#twinVersion"), eventCount: $("#eventCount"), parent: $("#parentVersion"),
    current: $("#currentVersion"), twinBadge: $("#twinBadge"), signals: $("#signalGrid"),
    anatomy: $("#anatomyState"), medication: $("#medicationState"), organ: $("#organState"),
    obligation: $("#obligationState"), missionTitle: $("#missionTitle"), missionStatus: $("#missionStatus"),
    missionAction: $("#missionAction"), agentPlan: $("#agentPlan"), humanForm: $("#humanForm"),
    eventFeed: $("#eventFeed"), truth: $("#truthBoundary"), receipt: $("#receiptState"),
  };
  let accessKey = "";
  let sessionId = "";
  let revealTimer = null;

  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  const label = value => String(value || "").replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("X-HealthIA-Evaluation-Key", accessKey);
    if (options.body) headers.set("Content-Type", "application/json");
    const response = await fetch(path, {...options, headers});
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return response.json();
  }

  function setBusy(active, text = "WORKING") {
    refs.activate.disabled = active;
    refs.replay.disabled = active;
    refs.status.textContent = text;
    document.body.classList.toggle("is-processing", active);
  }

  function showError(error) {
    refs.error.textContent = error.message || String(error);
    refs.error.hidden = false;
    setBusy(false, "SAFE STOP");
  }

  function signalCards(twin) {
    const deviations = twin.deviations || [];
    refs.signals.innerHTML = deviations.slice(-4).map(item => `
      <div class="signal-card">
        <span>${escapeHtml(label(item.metric))}</span>
        <strong>${escapeHtml(item.observed_value)} <small>${escapeHtml(item.unit)}</small></strong>
        <em class="${item.direction === "lower" ? "down" : "up"}">${item.direction === "lower" ? "↓" : "↑"} from ${escapeHtml(item.baseline_value)}</em>
      </div>`).join("") || '<p class="empty-state">Four synthetic signals will appear here after activation.</p>';
  }

  function renderEvents(events, animate = false) {
    clearTimeout(revealTimer);
    refs.eventFeed.replaceChildren();
    const add = (event, index) => {
      const item = document.createElement("li");
      item.className = `event-item ${event.status === "blocked" ? "is-boundary" : ""}`;
      item.innerHTML = `<span class="event-index">${String(index + 1).padStart(2, "0")}</span><span class="event-node"></span><div><strong>${escapeHtml(label(event.event_type))}</strong><small>${escapeHtml(event.actor)} · ${escapeHtml(label(event.policy_decision))}</small></div><em>${escapeHtml(label(event.status))}</em>`;
      refs.eventFeed.append(item);
      refs.eventCount.textContent = `${index + 1} / 14`;
    };
    if (!animate) { events.forEach(add); return; }
    let index = 0;
    const revealNext = () => {
      add(events[index], index);
      index += 1;
      if (index < events.length) revealTimer = setTimeout(revealNext, 180);
    };
    if (events.length) revealNext();
  }

  function render(data, animate = false) {
    refs.runtime.hidden = false;
    const session = data.session || {};
    const twin = data.twin || {};
    const mission = data.mission;
    sessionId = session.id || sessionId;
    const completed = session.status === "completed";
    const waiting = session.status === "waiting_human";
    refs.status.textContent = completed ? "VERIFIED" : waiting ? "WAITING FOR HUMAN" : label(session.status || "READY").toUpperCase();
    refs.activate.disabled = completed;
    refs.activate.textContent = completed ? "Cycle complete · replay preserved" : "Activate Living System";
    refs.twinVersion.textContent = `v${twin.version || "—"}`;
    refs.parent.textContent = twin.parent_version ? `v${twin.parent_version}` : "origin";
    refs.current.textContent = twin.version ? `v${twin.version}` : "—";
    refs.twinBadge.textContent = completed ? "LEARNED FROM RECEIPT" : waiting ? "VERSIONED" : "READY";
    signalCards(twin);
    refs.anatomy.textContent = twin.anatomy_state?.[0]?.modification || "No anatomy modification";
    refs.medication.textContent = twin.medication_expectations?.[0]?.expected_outcome || "No active expectation";
    refs.organ.textContent = `${twin.organ_system_state?.length || 0} systems correlated`;
    refs.obligation.textContent = String((twin.obligations || []).filter(item => item.status !== "completed").length);
    refs.missionTitle.textContent = mission?.title || "No mission opened";
    refs.missionStatus.textContent = label(mission?.status || "idle").toUpperCase();
    refs.missionStatus.className = `state-badge ${mission ? "" : "muted"}`;
    refs.missionAction.textContent = mission?.next_action || "HealthIA will act only after evidence arrives and policy allows it.";
    refs.agentPlan.innerHTML = (mission?.agent_plan || []).map(step => `<div><span>${escapeHtml(step.agent)}</span><strong>${escapeHtml(step.action)}</strong><em>${escapeHtml(label(step.status))}</em></div>`).join("");
    refs.humanForm.hidden = !waiting;
    refs.truth.textContent = data.truth_boundary;
    refs.receipt.textContent = completed ? `persisted: ${escapeHtml(mission.closure_evidence?.[0] || "synthetic evidence")}` : "requires persisted receipt";
    renderEvents(data.events || [], animate);
  }

  async function unlock(event) {
    event.preventDefault();
    accessKey = refs.accessKey.value.trim();
    try {
      const state = await api("/api/evaluation/state");
      refs.accessPanel.hidden = true;
      refs.controlPanel.hidden = false;
      refs.error.hidden = true;
      if (state.session) render(state);
      refs.status.textContent = state.session ? label(state.session.status).toUpperCase() : "READY";
    } catch (error) { showError(error); }
  }


  async function activate() {
    refs.error.hidden = true;
    setBusy(true, "ARMING");
    try {
      const armed = await api("/api/evaluation/arm", {method: "POST"});
      sessionId = armed.session.id;
      render(armed);
      setBusy(true, "SENSING");
      const result = await api("/api/evaluation/run", {method: "POST", body: JSON.stringify({session_id: sessionId})});
      render(result, true);
      setBusy(false, "WAITING FOR HUMAN");
    } catch (error) { showError(error); }
  }

  async function replay() {
    setBusy(true, "REREADING");
    try { const data = await api("/api/evaluation/state"); render(data, true); setBusy(false, label(data.session?.status || "READY").toUpperCase()); }
    catch (error) { showError(error); }
  }

  async function complete(event) {
    event.preventDefault();
    setBusy(true, "PERSISTING RECEIPT");
    try {
      const data = await api("/api/evaluation/complete", {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          systolic: Number($("#systolic").value),
          diastolic: Number($("#diastolic").value),
          pulse: Number($("#pulse").value) || null,
        }),
      });
      render(data, true);
      setBusy(false, "VERIFIED");
    } catch (error) { showError(error); }
  }

  refs.accessForm.addEventListener("submit", unlock);
  refs.activate.addEventListener("click", activate);
  refs.replay.addEventListener("click", replay);
  refs.humanForm.addEventListener("submit", complete);
})();
