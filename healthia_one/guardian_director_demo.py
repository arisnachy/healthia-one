from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from healthia_one.appointment_guardian import reconcile_appointment_guardian
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import plan_guardian_notification
from healthia_one.models import (
    Appointment,
    ClinicalDocument,
    DocumentCategory,
    HealthResult,
    MedicationPlan,
    PatientState,
    ResultItem,
)
from healthia_one.postvisit_guardian import reconcile_postvisit_guardian
from healthia_one.result_guardian import reconcile_result_guardian

app = FastAPI(title="HealthIA ONE Guardian Director Demo", docs_url=None, redoc_url=None)
DEMO_NOW = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
STATE: PatientState
NOTIFICATIONS: list[dict[str, Any]]
STEPS: list[dict[str, Any]]


def _new_state() -> PatientState:
    state = PatientState()
    state.profile.name = "Ana — synthetic patient"
    state.profile.email = "ana.synthetic@example.test"
    state.medication_plans = [
        MedicationPlan(
            name="Losartan",
            generic_name="losartan",
            strength="50 mg",
            schedule="daily",
            active=True,
            verification_status="patient_confirmed",
        )
    ]
    state.consent.proactive_enabled = True
    state.consent.signal_types = [
        "results",
        "appointments",
        "documents",
        "guardian_email",
        "guardian_email_auto_send",
    ]
    return state


def reset() -> None:
    global STATE, NOTIFICATIONS, STEPS
    STATE = _new_state()
    NOTIFICATIONS = []
    STEPS = [
        {
            "title": "Patient Twin armed",
            "detail": "Losartan 50 mg daily is registered. Proactive continuity and patient-email auto-send consent are enabled for this synthetic demo.",
            "kind": "twin",
        }
    ]


reset()


def _mission_payload(mission) -> dict[str, Any]:
    return {
        "id": mission.id,
        "type": mission.mission_type,
        "title": mission.title,
        "status": mission.status.value,
        "next_action": mission.next_action,
        "evidence_ids": list(mission.evidence_ids),
        "closure_evidence": list(mission.closure_evidence),
    }


def _latest_intent_for(mission_id: str) -> dict[str, Any] | None:
    for event in reversed(STATE.audit_events):
        if event.action != "autopilot_event_intent":
            continue
        payload = (event.details.get("event") or {}).get("payload") or {}
        if payload.get("mission_id") == mission_id:
            return payload
    return None


def _capture_email_plan(mission_id: str) -> dict[str, Any] | None:
    payload = _latest_intent_for(mission_id)
    if not payload or not payload.get("guardian_assessment"):
        return None
    assessment = GuardianAssessment.model_validate(payload["guardian_assessment"])
    plan = plan_guardian_notification(STATE, assessment, mission_id=mission_id)
    if plan.email is None:
        return None
    item = {
        "mission_id": mission_id,
        "classification": assessment.classification,
        "delivery_mode": plan.email.delivery_mode,
        "subject": plan.email.subject,
        "recipient": plan.email.recipient,
        "changes_treatment": plan.email.changes_treatment,
        "diagnostic_claim": plan.email.diagnostic_claim,
    }
    NOTIFICATIONS.append(item)
    return item


def _append_lab(filename: str, *items: ResultItem) -> tuple[HealthResult, ClinicalDocument]:
    result = HealthResult(
        filename=filename,
        panel="Synthetic metabolic monitoring",
        status="parsed",
        explained=True,
        items=list(items),
    )
    result.uploaded_at = STATE.updated_at + timedelta(seconds=1)
    document = ClinicalDocument(
        title=f"Original evidence — {filename}",
        filename=filename,
        category=DocumentCategory.LABORATORY,
        mime_type="application/json",
        uploaded_at=result.uploaded_at,
        status="parsed",
        related_result_id=result.id,
    )
    STATE.results.append(result)
    STATE.documents.append(document)
    return result, document


def _summary() -> dict[str, Any]:
    active = [m for m in STATE.missions if m.status.value not in {"completed", "cancelled"}]
    return {
        "patient": STATE.profile.name,
        "treatment": [
            {
                "name": m.name,
                "strength": m.strength,
                "schedule": m.schedule,
                "active": m.active,
            }
            for m in STATE.medication_plans
        ],
        "results": [
            {
                "filename": r.filename,
                "items": [f"{i.name}: {i.value} {i.unit or ''}".strip() for i in r.items],
            }
            for r in STATE.results
        ],
        "documents": [
            {"title": d.title, "category": d.category.value, "filename": d.filename}
            for d in STATE.documents
        ],
        "appointments": [
            {
                "id": a.id,
                "title": a.title,
                "status": a.status,
                "scheduled_at": a.scheduled_at.isoformat(),
                "required_documents": list(a.required_documents),
            }
            for a in STATE.appointments
        ],
        "missions": [_mission_payload(m) for m in STATE.missions],
        "active_mission_count": len(active),
        "notifications": list(NOTIFICATIONS),
        "steps": list(STEPS),
        "audit_count": len(STATE.audit_events),
        "chat_prompts_used": 0,
        "guardian_llm_calls": 0,
        "truth_boundary": "Guardian evaluates continuity and evidence completeness. It does not autonomously diagnose, prescribe, or change treatment.",
    }


@app.get("/api/state")
async def api_state() -> dict[str, Any]:
    return _summary()


@app.post("/api/reset")
async def api_reset() -> dict[str, Any]:
    reset()
    return _summary()


@app.post("/api/result-gap")
async def result_gap() -> dict[str, Any]:
    result, _ = _append_lab("renal-function.json", ResultItem(name="Creatinine", value=0.9, unit="mg/dL"))
    report = reconcile_result_guardian(STATE)
    mission = next(m for m in STATE.missions if m.mission_type.startswith("result_guardian"))
    plan = _capture_email_plan(mission.id)
    STEPS.append(
        {
            "title": "Treatment-aware evidence gap detected",
            "detail": "A new renal result arrived. Because Losartan is registered, Guardian checked whether renal-function and potassium evidence were both present. Potassium was missing, so it opened a durable mission without a chat prompt.",
            "kind": "result_gap",
            "mission_id": mission.id,
            "trigger_result_id": result.id,
            "email_mode": (plan or {}).get("delivery_mode"),
        }
    )
    return {"report": report, "state": _summary()}


@app.post("/api/result-resolve")
async def result_resolve() -> dict[str, Any]:
    STATE.updated_at = STATE.results[-1].uploaded_at + timedelta(seconds=2)
    result, _ = _append_lab("potassium.json", ResultItem(name="Potassium", value=4.2, unit="mmol/L"))
    report = reconcile_result_guardian(STATE)
    mission = next(m for m in STATE.missions if m.mission_type.startswith("result_guardian"))
    plan = _capture_email_plan(mission.id)
    STEPS.append(
        {
            "title": "Evidence arrived — same mission closed",
            "detail": "Potassium evidence appeared later. Guardian matched it to the open treatment-context mission, attached durable evidence and a receipt, and closed the mission. Treatment remained unchanged.",
            "kind": "result_resolved",
            "mission_id": mission.id,
            "trigger_result_id": result.id,
            "email_mode": (plan or {}).get("delivery_mode"),
        }
    )
    return {"report": report, "state": _summary()}


@app.post("/api/appointment-gap")
async def appointment_gap() -> dict[str, Any]:
    appointment = Appointment(
        title="Family medicine follow-up",
        specialty="Family medicine",
        scheduled_at=DEMO_NOW + timedelta(hours=36),
        required_documents=["Recent results", "Medication list", "Insurance"],
    )
    STATE.appointments.append(appointment)
    report = reconcile_appointment_guardian(STATE, now=DEMO_NOW)
    mission = next(m for m in STATE.missions if m.mission_type == "appointment_guardian_preparation")
    plan = _capture_email_plan(mission.id)
    STEPS.append(
        {
            "title": "Upcoming visit audited automatically",
            "detail": "Guardian verified the recent laboratory evidence and active medication plan already present in the Twin. Insurance evidence was missing, so it opened a preparation mission instead of sending a generic reminder.",
            "kind": "appointment_gap",
            "mission_id": mission.id,
            "appointment_id": appointment.id,
            "email_mode": (plan or {}).get("delivery_mode"),
        }
    )
    return {"report": report, "state": _summary()}


@app.post("/api/appointment-resolve")
async def appointment_resolve() -> dict[str, Any]:
    document = ClinicalDocument(
        title="Insurance card",
        filename="insurance-card.pdf",
        category=DocumentCategory.INSURANCE,
        mime_type="application/pdf",
        uploaded_at=DEMO_NOW + timedelta(minutes=2),
        status="parsed",
    )
    STATE.documents.append(document)
    report = reconcile_appointment_guardian(STATE, now=DEMO_NOW + timedelta(minutes=3))
    mission = next(m for m in STATE.missions if m.mission_type == "appointment_guardian_preparation")
    plan = _capture_email_plan(mission.id)
    STEPS.append(
        {
            "title": "Visit preparation verified from evidence",
            "detail": "The insurance document arrived. Guardian re-ran the preparation checks and closed the same mission with a receipt. It did not book, cancel, or change the appointment.",
            "kind": "appointment_resolved",
            "mission_id": mission.id,
            "document_id": document.id,
            "email_mode": (plan or {}).get("delivery_mode"),
        }
    )
    return {"report": report, "state": _summary()}


@app.post("/api/postvisit-gap")
async def postvisit_gap() -> dict[str, Any]:
    appointment = STATE.appointments[-1]
    post_now = DEMO_NOW + timedelta(days=1)
    appointment.scheduled_at = post_now - timedelta(hours=1)
    appointment.status = "completed"
    report = reconcile_postvisit_guardian(STATE, now=post_now)
    mission = next(m for m in STATE.missions if m.mission_type == "postvisit_guardian_summary_capture")
    plan = _capture_email_plan(mission.id)
    STEPS.append(
        {
            "title": "Completed visit, missing outcome",
            "detail": "The appointment is now completed, but no consultation or discharge note can be verified. Guardian opens a post-visit continuity mission and explicitly refuses to invent what happened.",
            "kind": "postvisit_gap",
            "mission_id": mission.id,
            "email_mode": (plan or {}).get("delivery_mode"),
        }
    )
    return {"report": report, "state": _summary()}


@app.post("/api/postvisit-resolve")
async def postvisit_resolve() -> dict[str, Any]:
    appointment = STATE.appointments[-1]
    document = ClinicalDocument(
        title="Consultation note",
        filename="consultation-note.pdf",
        category=DocumentCategory.CONSULTATION,
        mime_type="application/pdf",
        uploaded_at=appointment.scheduled_at + timedelta(hours=2),
        status="parsed",
    )
    STATE.documents.append(document)
    report = reconcile_postvisit_guardian(STATE, now=appointment.scheduled_at + timedelta(hours=3))
    mission = next(m for m in STATE.missions if m.mission_type == "postvisit_guardian_summary_capture")
    plan = _capture_email_plan(mission.id)
    STEPS.append(
        {
            "title": "Post-visit loop closed from the note",
            "detail": "The consultation note arrived in the permitted time window. Guardian linked it to the completed visit and closed the same mission with durable evidence. No clinical content was invented.",
            "kind": "postvisit_resolved",
            "mission_id": mission.id,
            "document_id": document.id,
            "email_mode": (plan or {}).get("delivery_mode"),
        }
    )
    return {"report": report, "state": _summary()}


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HealthIA ONE — Guardian Research Build</title>
<style>
:root{--bg:#06111e;--p:#0d1d2f;--p2:#10263c;--ink:#eff7ff;--muted:#9fb5c9;--blue:#66c5ff;--green:#66e0a3;--amber:#ffd274;--line:#29445f}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% 0,#153451,#06111e 38%,#040a11);color:var(--ink);font-family:Inter,system-ui,sans-serif}.wrap{max-width:1320px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px}.brand{font-size:15px;font-weight:900;letter-spacing:.13em}.badge{border:1px solid #356a8c;background:#0c2438;border-radius:999px;padding:8px 12px;color:#cbeeff;font-size:12px}.hero{margin:26px 0;display:grid;grid-template-columns:1.25fr .75fr;gap:18px}.card{background:linear-gradient(180deg,rgba(18,39,61,.96),rgba(8,21,35,.96));border:1px solid var(--line);border-radius:20px;box-shadow:0 18px 54px rgba(0,0,0,.24)}.heroMain{padding:34px}.hero h1{font-size:48px;line-height:1.02;margin:0 0 14px;letter-spacing:-.04em}.lead{color:#cad9e7;font-size:19px;line-height:1.5}.metric{padding:26px;display:flex;flex-direction:column;justify-content:center}.metric strong{font-size:56px;color:var(--green)}.grid{display:grid;grid-template-columns:.9fr 1.1fr;gap:18px}.section{padding:24px}.section h2{margin:0 0 14px;font-size:20px}.twinRow,.mission,.step,.notify{border-top:1px solid var(--line);padding:12px 0}.label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}.value{font-size:16px;margin-top:4px}.mission b{color:var(--blue)}.status{display:inline-block;padding:4px 8px;border-radius:999px;background:#102f3a;color:#89efbf;font-size:11px;margin-left:7px}.timeline{max-height:480px;overflow:auto}.step{display:grid;grid-template-columns:32px 1fr;gap:10px}.n{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:#133f5e;color:#dff4ff;font-weight:800}.step p{margin:4px 0;color:#c9d8e7;line-height:1.4}.truth{margin-top:18px;padding:14px 18px;border:1px solid #6f5c29;background:#1d190d;border-radius:14px;color:#f3e4b4}.controls{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}button{background:#123b59;color:white;border:1px solid #2d6d96;border-radius:10px;padding:8px 11px}.proof{margin-top:18px;padding:18px}.proof code{color:#bfe7ff}.green{color:var(--green)}.amber{color:var(--amber)}@media(max-width:900px){.hero,.grid{grid-template-columns:1fr}.hero h1{font-size:38px}}
</style></head><body><main class="wrap">
<div class="top"><div class="brand">HEALTHIA ONE</div><div class="badge">GUARDIAN RESEARCH BUILD · REAL CODE · SYNTHETIC PATIENT</div></div>
<section class="hero"><div class="card heroMain"><h1>The patient should not have to remember everything.</h1><p class="lead">This surface executes HealthIA Guardian's real treatment-aware, appointment-aware and post-visit continuity rules. The research build is shown separately from the frozen judging runtime.</p><div class="controls"><button onclick="act('/api/reset')">Reset Twin</button><button onclick="act('/api/result-gap')">Renal result</button><button onclick="act('/api/result-resolve')">Potassium arrives</button><button onclick="act('/api/appointment-gap')">Upcoming visit</button><button onclick="act('/api/appointment-resolve')">Insurance arrives</button><button onclick="act('/api/postvisit-gap')">Visit completed</button><button onclick="act('/api/postvisit-resolve')">Consult note arrives</button></div></div>
<div class="card metric"><strong id="promptCount">0</strong><div class="label">chat prompts used by Guardian</div><p class="lead" style="font-size:15px">Deterministic Guardian rules create and close continuity missions from patient state and durable evidence.</p></div></section>
<section class="grid"><div><div class="card section"><h2>Patient Twin</h2><div id="twin"></div></div><div class="card section" style="margin-top:18px"><h2>Durable missions</h2><div id="missions"></div></div><div class="card section" style="margin-top:18px"><h2>Notification intent</h2><div id="notifications"></div></div></div>
<div class="card section"><h2>Autonomous continuity timeline</h2><div class="timeline" id="steps"></div></div></section>
<section class="card proof"><h2>Frozen main — ONE SAFETY proof</h2><p>In the promoted runtime, an outside-world action cannot close from model text alone:</p><p><code>Cloud Trace eec691300b7bb1c1c0564e95fb090e4f → HealthActionTicket hat_021b1b6b1b4542e2 → connector → receipt_95ba26286e6f4e15 → completed</code></p><p class="green">Authorization is not completion. Receipt + trace are required.</p></section>
<div class="truth" id="truth"></div>
</main><script>
async function load(){const s=await fetch('/api/state').then(r=>r.json());render(s)}
async function act(path){const x=await fetch(path,{method:'POST'}).then(r=>r.json());render(x.state||x)}
function esc(x){return String(x??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function render(s){document.querySelector('#promptCount').textContent=s.chat_prompts_used;
 const res=s.results.flatMap(r=>r.items).join(' · ')||'No lab evidence yet';const docs=s.documents.map(d=>d.category+': '+d.filename).join(' · ')||'No documents yet';
 document.querySelector('#twin').innerHTML=`<div class=twinRow><div class=label>Treatment</div><div class=value>${s.treatment.map(m=>esc(m.name+' '+m.strength+' · '+m.schedule)).join('<br>')}</div></div><div class=twinRow><div class=label>Clinical evidence</div><div class=value>${esc(res)}</div></div><div class=twinRow><div class=label>Documents</div><div class=value>${esc(docs)}</div></div><div class=twinRow><div class=label>Audit events</div><div class=value>${s.audit_count}</div></div>`;
 document.querySelector('#missions').innerHTML=s.missions.length?s.missions.map(m=>`<div class=mission><b>${esc(m.title)}</b><span class=status>${esc(m.status)}</span><div class=label style="margin-top:7px">${esc(m.type)}</div><div class=value>${esc(m.next_action)}</div></div>`).join(''):'<div class=value>No Guardian mission yet.</div>';
 document.querySelector('#notifications').innerHTML=s.notifications.length?s.notifications.slice(-3).reverse().map(n=>`<div class=notify><b>${esc(n.subject)}</b><span class=status>${esc(n.delivery_mode)}</span><div class=value>${esc(n.classification)} · to patient profile only</div></div>`).join(''):'<div class=value>No notification intent yet.</div>';
 document.querySelector('#steps').innerHTML=s.steps.map((x,i)=>`<div class=step><div class=n>${i+1}</div><div><b>${esc(x.title)}</b><p>${esc(x.detail)}</p></div></div>`).join('');document.querySelector('#steps').scrollTop=document.querySelector('#steps').scrollHeight;
 document.querySelector('#truth').innerHTML='<b>Truth boundary.</b> '+esc(s.truth_boundary)+' This research build does not claim continuous external medical-literature surveillance.'}
load();
</script></body></html>'''


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return PAGE
