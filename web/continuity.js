if (!window.__HEALTHIA_CONTINUITY__) {
  window.__HEALTHIA_CONTINUITY__ = true;
(() => {
  const $=(selector,root=document)=>root.querySelector(selector), $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const i18n=window.HealthIAI18n, text=(en,es)=>i18n?.locale==="es"?es:en, localeTag=()=>i18n?.browserLocaleTag?.()||"en-US";
  const escapeHtml=value=>String(value??"").replace(/[&<>'"]/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  let snapshot=null;
  async function api(path,options={}){const headers=new Headers(options.headers||{});headers.set("Accept-Language",i18n?.locale||"en");const response=await fetch(path,{...options,headers});if(!response.ok){let detail=`Error ${response.status}`;try{detail=(await response.json()).detail||detail;}catch{}throw new Error(detail);}return response.json();}
  function toast(message){const node=$("#toast");if(!node)return;node.textContent=message;node.hidden=false;setTimeout(()=>{node.hidden=true;},3000);}
  function formatDate(value){const date=new Date(value);return Number.isNaN(date.getTime())?text("No date","sin fecha"):new Intl.DateTimeFormat(localeTag(),{dateStyle:"medium",timeStyle:"short"}).format(date);}
  function activateView(view){$$(".view").forEach(node=>node.classList.toggle("is-active",node.id===`view-${view}`));$$('.main-nav [data-open]').forEach(node=>node.classList.toggle("is-active",node.dataset.open===view));refresh().catch(error=>toast(error.message));}
  const navItems=()=>[["timeline","⌁",text("Health timeline","Línea de salud")],["treatment","✚",text("Treatment","Tratamiento")],["appointments","◫",text("Appointments & visit","Citas y consulta")]];
  function injectNavigation(){const nav=$(".main-nav"),missions=nav?.querySelector('[data-open="missions"]');if(!nav||!missions)return;navItems().forEach(([view,icon,label])=>{let button=nav.querySelector(`[data-open="${view}"]`);if(!button){button=document.createElement("button");button.dataset.open=view;button.addEventListener("click",()=>activateView(view));nav.insertBefore(button,missions);}button.innerHTML=`<span>${icon}</span><b>${label}</b>`;});}
  function injectQuickActions(){const quick=$(".quick-records");if(!quick)return;[["timeline",`⌁ ${text("History","Historia")}`],["treatment",`✚ ${text("Dose","Toma")}`],["appointments",`◫ ${text("Visit","Cita")}`]].forEach(([target,label])=>{let button=quick.querySelector(`[data-continuity="${target}"]`);if(!button){button=document.createElement("button");button.type="button";button.dataset.continuity=target;button.addEventListener("click",()=>activateView(target));quick.append(button);}button.textContent=label;});}
  function injectViews(){const main=$(".conversation-column");if(!main)return;const defs=[["timeline",text("HEALTH CONTINUITY","CONTINUIDAD DE SALUD"),text("Health timeline","Línea de salud"),text("Every event in one provenance-linked chronology.","Todos tus eventos en una cronología con procedencia."),"timelineRoot"],["treatment",text("TREATMENT SAFETY","SEGURIDAD DEL TRATAMIENTO"),text("Treatment & check-ins","Tratamiento y tomas"),text("The prescribed plan and patient-reported adherence without autonomous dose changes.","Registro del esquema indicado y adherencia informada por el paciente."),"treatmentRoot"],["appointments",text("VISIT PREPARATION","PREPARACIÓN DE CONSULTA"),text("Appointments & visit","Citas y consulta"),text("Prepare changes, documents, goals, and questions without starting over.","Prepara cambios, documentos, objetivos y preguntas sin empezar desde cero."),"appointmentsRoot"]];defs.forEach(([id,kicker,title,copy,root])=>{let section=$(`#view-${id}`);if(!section){section=document.createElement("section");section.id=`view-${id}`;section.className="view";main.append(section);}section.innerHTML=`<div class="page-body"><div class="page-kicker">${kicker}</div><h1>${title}</h1><p>${copy}</p><div id="${root}"></div></div>`;});}
  function injectDialog(){$("#appointmentDialog")?.remove();document.body.insertAdjacentHTML("beforeend",`<dialog id="appointmentDialog" class="health-os-dialog"><form id="appointmentForm" class="health-os-form"><header><div><small>${text("PATIENT APPOINTMENT","CITA DEL PACIENTE")}</small><h2>${text("Add appointment","Añadir cita")}</h2></div><button type="button" data-cont-close>×</button></header><div class="health-os-fields"><label>${text("Title","Título")}<input name="title" required placeholder="${text("Family medicine visit","Consulta de medicina familiar")}"></label><label>${text("Specialty","Especialidad")}<input name="specialty"></label><label>${text("Date & time","Fecha y hora")}<input name="scheduled_at" type="datetime-local" required></label><label>${text("Location","Lugar")}<input name="location"></label><label class="wide">${text("Required documents, comma separated","Documentos separados por coma")}<input name="required_documents"></label><label class="wide">${text("Questions, comma separated","Preguntas separadas por coma")}<textarea name="questions" rows="2"></textarea></label></div><footer><button type="button" data-cont-close>${text("Cancel","Cancelar")}</button><button type="submit">${text("Save appointment","Guardar cita")}</button></footer></form></dialog>`);$$('[data-cont-close]').forEach(button=>button.addEventListener("click",()=>$("#appointmentDialog")?.close()));bindAppointmentForm();}
  function renderTimeline(){const root=$("#timelineRoot");if(!root||!snapshot)return;const events=snapshot.timeline||[],packs=snapshot.condition_packs||[];root.innerHTML=`<div class="continuity-layout"><div class="condition-pack-grid">${packs.map(pack=>`<article class="condition-pack"><h3>${escapeHtml(pack.label)}</h3><p>${pack.signals.map(escapeHtml).join(" · ")}</p><ul>${pack.questions.map(q=>`<li>${escapeHtml(q)}</li>`).join("")}</ul></article>`).join("")}</div><div class="timeline-list">${events.length?events.map(event=>`<article class="timeline-event"><div><h3>${escapeHtml(event.title)}</h3><p>${escapeHtml(event.detail)} · ${escapeHtml(event.source)}</p></div><small>${formatDate(event.occurred_at)}</small></article>`).join(""):`<article class="timeline-event"><div><h3>${text("No events yet","Sin eventos")}</h3><p>${text("Record a measurement or upload a document.","Registra una medición o carga un documento.")}</p></div></article>`}</div></div>`;}
  function renderTreatment(){const root=$("#treatmentRoot");if(!root||!snapshot)return;const summary=snapshot.medication_summary||{active_plans:[],counts:{},reported_adherence_percent:null},adherence=summary.reported_adherence_percent;root.innerHTML=`<div class="continuity-layout"><div class="continuity-toolbar"><div><strong>${text("Recorded treatment","Tratamiento registrado")}</strong><p>${text("HealthIA does not autonomously change it.","No se modifica desde HealthIA.")}</p></div></div><div class="treatment-grid">${summary.active_plans.length?summary.active_plans.map(plan=>`<article class="treatment-card"><header><h3>${escapeHtml(plan.name)} ${escapeHtml(plan.strength||"")}</h3><span class="health-status">${text("active","activo")}</span></header><p>${escapeHtml(plan.schedule)} · ${escapeHtml(plan.purpose||text("purpose not recorded","propósito no registrado"))}</p><small>${escapeHtml(plan.instructions||text("Follow professional instructions","Seguir indicación profesional"))}</small><div class="treatment-actions"><button data-dose="taken" data-medication="${plan.id}">${text("Taken","Tomada")}</button><button data-dose="late" data-medication="${plan.id}">${text("Late","Tarde")}</button><button data-dose="skipped" data-medication="${plan.id}">${text("Skipped","Omitida")}</button></div></article>`).join(""):`<article class="treatment-card"><h3>${text("No structured treatment","Sin tratamiento estructurado")}</h3><p>${text("Record exactly what your professional prescribed.","Registra exactamente lo indicado por tu profesional.")}</p></article>`}</div><article class="brief-card"><h3>${text("Reported adherence","Adherencia informada")}</h3><p>${adherence==null?text("Not enough check-ins yet.","Aún no hay suficientes registros."):`${adherence.toFixed(1)}% ${text("from recorded check-ins","según las tomas registradas")}.`}</p><div class="adherence-meter"><span style="width:${adherence||0}%"></span></div><p>${text("This percentage does not prove absorption or authorize dose changes.","Este porcentaje no demuestra absorción ni autoriza cambios de dosis.")}</p></article></div>`;$$('[data-dose]',root).forEach(button=>button.addEventListener("click",()=>recordDose(button.dataset.medication,button.dataset.dose)));}
  async function recordDose(medicationId,status){try{await api("/api/treatment/checkins",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({medication_id:medicationId,status})});await refresh();toast(text("Check-in recorded without changing treatment.","Toma registrada sin modificar el tratamiento."));}catch(error){toast(error.message);}}
  function renderAppointments(){const root=$("#appointmentsRoot");if(!root||!snapshot)return;const appointments=snapshot.appointments||[],brief=snapshot.consultation_brief||{};root.innerHTML=`<div class="continuity-layout"><div class="continuity-toolbar"><div><strong>${text("Health agenda","Agenda de salud")}</strong><p>${text("The patient controls what is shared.","El paciente controla qué comparte.")}</p></div><button id="addAppointmentButton">＋ ${text("Add appointment","Añadir cita")}</button></div><div class="appointment-grid">${appointments.length?appointments.map(item=>`<article class="appointment-card"><header><h3>${escapeHtml(item.title)}</h3><span class="health-status">${escapeHtml(item.status)}</span></header><p>${formatDate(item.scheduled_at)} · ${escapeHtml(item.location||text("location not recorded","lugar no registrado"))}</p><small>${escapeHtml(item.specialty||text("no specialty","sin especialidad"))}</small></article>`).join(""):`<article class="appointment-card"><h3>${text("No appointments","Sin citas")}</h3><p>${text("Add one to prepare the consultation brief.","Añade una para preparar el resumen.")}</p></article>`}</div>${renderBrief(brief)}</div>`;$("#addAppointmentButton")?.addEventListener("click",()=>$("#appointmentDialog")?.showModal());}
  function renderBrief(brief){if(!brief?.patient)return"";return`<section class="brief-hero"><small>${text("PATIENT-CONTROLLED SUMMARY","RESUMEN CONTROLADO POR EL PACIENTE")}</small><h2>${text("Visit preparation","Preparación de consulta")}</h2><p>${escapeHtml(brief.truth_boundary||text("Review before sharing","Revisar antes de compartir"))}</p><div class="brief-grid"><article class="brief-card"><h3>${text("Confirmed conditions","Condiciones confirmadas")}</h3><p>${brief.confirmed_conditions?.map(escapeHtml).join(" · ")||text("No records","Sin registros")}</p></article><article class="brief-card"><h3>${text("Required documents","Documentos requeridos")}</h3><p>${brief.required_documents?.map(escapeHtml).join(" · ")||text("No requirements recorded","Sin requisitos registrados")}</p></article><article class="brief-card"><h3>${text("Family context","Contexto familiar")}</h3><p>${brief.family_context?.map(escapeHtml).join(" · ")||text("No aggregated patterns","Sin patrones agregados")}</p></article><article class="brief-card"><h3>${text("Priority questions","Preguntas prioritarias")}</h3><ul>${brief.questions?.map(item=>`<li>${escapeHtml(item)}</li>`).join("")||`<li>${text("No questions","Sin preguntas")}</li>`}</ul></article></div></section>`;}
  function hydrateChatActions(){if(!snapshot)return;const byId=new Map((snapshot.messages||[]).map(item=>[item.id,item]));$$("#messageList .message").forEach(article=>{article.querySelector(".v4-message-action")?.remove();const target=byId.get(article.dataset.id)?.metadata?.action_target;if(!["timeline","treatment","appointments"].includes(target))return;const labels={timeline:text("Open health timeline","Abrir línea de salud"),treatment:text("Open treatment","Abrir tratamiento"),appointments:text("Prepare visit","Preparar consulta")},bar=document.createElement("div");bar.className="message-actions v4-message-action";bar.innerHTML=`<button type="button">${labels[target]}</button>`;bar.querySelector("button").addEventListener("click",()=>activateView(target));article.querySelector(".message-content")?.append(bar);});}
  async function refresh(){snapshot=await api("/api/bootstrap");renderTimeline();renderTreatment();renderAppointments();hydrateChatActions();}
  function bindAppointmentForm(){const form=$("#appointmentForm");if(!form||form.dataset.contBound==="true")return;form.dataset.contBound="true";form.addEventListener("submit",async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget).entries()),split=value=>String(value||"").split(",").map(item=>item.trim()).filter(Boolean),payload={...values,scheduled_at:new Date(values.scheduled_at).toISOString(),required_documents:split(values.required_documents),questions:split(values.questions)};try{await api("/api/appointments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});event.currentTarget.reset();$("#appointmentDialog")?.close();await refresh();toast(text("Appointment added and brief updated.","Cita añadida y resumen actualizado."));}catch(error){toast(error.message);}});}
  function boot(){injectNavigation();injectQuickActions();injectViews();injectDialog();const list=$("#messageList");if(list)new MutationObserver(hydrateChatActions).observe(list,{childList:true});refresh().catch(error=>toast(error.message));}
  document.addEventListener("healthia:locale-changed",()=>{injectNavigation();injectQuickActions();injectViews();injectDialog();renderTimeline();renderTreatment();renderAppointments();hydrateChatActions();});
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();
}

if (!window.__HEALTHIA_CHAT_OS_CONTROLLER__) {
  window.__HEALTHIA_CHAT_OS_CONTROLLER__ = true;
  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
    let lastAppliedMessageId = "";
    let armed = false;
    let retries = 0;
    let scheduled = null;

    function showToast(message) {
      const node = $("#toast");
      if (!node) return;
      node.textContent = message;
      node.hidden = false;
      clearTimeout(showToast.timer);
      showToast.timer = setTimeout(() => { node.hidden = true; }, 2400);
    }

    function openView(view) {
      if (!view) return false;
      const section = document.getElementById(`view-${view}`);
      if (!section) return false;
      $$(".view").forEach(node => node.classList.toggle("is-active", node === section));
      $$('.main-nav [data-open], .primary-action[data-open]').forEach(node => node.classList.toggle("is-active", node.dataset.open === view));
      $("#app")?.classList.remove("menu-open");
      section.scrollIntoView({block: "start"});
      return true;
    }

    function executeUiAction(message) {
      const action = message?.metadata?.ui_action;
      if (!armed || !action || !message?.id || message.id === lastAppliedMessageId) return false;
      if (action.view && !openView(String(action.view))) return false;

      if (action.type === "open_dialog" && action.dialog) {
        const trigger = document.querySelector(`[data-dialog="${String(action.dialog).replace(/"/g, "\\\"")}"]`);
        if (!trigger) return false;
        trigger.click();
        showToast(document.documentElement.lang === "es" ? "Abrí el registro que pediste." : "I opened the entry you asked for.");
      } else if (action.type === "pick_file" && action.picker === "result") {
        const input = $("#resultFilePage") || $("#resultFile");
        if (!input) return false;
        input.click();
        showToast(document.documentElement.lang === "es" ? "Selecciona el resultado que quieres cargar." : "Choose the result you want to upload.");
      } else if (action.type === "open_view") {
        showToast(document.documentElement.lang === "es" ? "Listo, abrí esa parte de HealthIA." : "Done, I opened that part of HealthIA.");
      }

      lastAppliedMessageId = message.id;
      armed = false;
      retries = 0;
      return true;
    }

    async function applyLatestAction() {
      if (!armed) return;
      try {
        const response = await fetch("/api/bootstrap", {headers: {Accept: "application/json", "Accept-Language": window.HealthIAI18n?.locale || "en"}});
        if (!response.ok) return;
        const data = await response.json();
        const latestAssistant = [...(data.messages || [])].reverse().find(message => message.role === "assistant");
        if (!latestAssistant?.metadata?.ui_action) {
          armed = false;
          return;
        }
        if (!executeUiAction(latestAssistant) && retries < 8) {
          retries += 1;
          scheduled = setTimeout(applyLatestAction, 80);
        }
      } catch {
        armed = false;
      }
    }

    function scheduleApply() {
      if (!armed) return;
      clearTimeout(scheduled);
      scheduled = setTimeout(applyLatestAction, 30);
    }

    function armForChatResponse() {
      armed = true;
      retries = 0;
      scheduleApply();
    }

    function boot() {
      const list = $("#messageList");
      if (list) new MutationObserver(scheduleApply).observe(list, {childList: true});
      document.addEventListener("healthia:chat-settled", armForChatResponse);
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once: true});
    else boot();
  })();
}
