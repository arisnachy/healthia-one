from __future__ import annotations

import html
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from healthia_one.autonomous_continuity import judge_proof


app = FastAPI(title="HealthIA ONE Judge Mode", docs_url=None, redoc_url=None, openapi_url=None)

SOURCE_SHA = os.getenv("HEALTHIA_JUDGE_SOURCE_SHA", "candidate-not-stamped")
LIVE_PROOF_RUN = os.getenv("HEALTHIA_JUDGE_LIVE_PROOF_RUN", "pending-exact-head-proof")
REPO_URL = "https://github.com/arisnachy/healthia-one"
WAVE4_VIDEO = "https://github.com/arisnachy/healthia-one/releases/download/healthia-one-autonomous-winner-demo-2026/HealthIA-ONE-Autonomous-Taskmaster-Charon.mp4"


SYNTHETIC_STATE = {
    "patient": "Synthetic judge patient",
    "result": {
        "status": "preserved",
        "provenance": "Original evidence → private GCS → bounded interpretation → durable patient state",
    },
    "mission": {
        "type": "blood-pressure follow-up",
        "status_path": ["DUE", "WAITING_PATIENT", "EXTERNAL_EVENT_RECEIVED", "COMPLETED"],
        "human_boundary": "Patient explicitly opts into BP follow-up, Guardian email auto-send, and reply processing.",
    },
    "truth_boundary": "Read-only synthetic evidence surface. It cannot send email, call a model, mutate clinical state, or modify a Google account.",
}


def _health_payload() -> dict:
    return {
        "status": "ok",
        "mode": "judge_read_only_synthetic",
        "source_sha": SOURCE_SHA,
        "live_proof_run": LIVE_PROOF_RUN,
        "mutations": False,
        "model_calls": False,
        "secrets": False,
    }


@app.get("/judge-health")
async def judge_health() -> dict:
    # Dedicated public verification endpoint.  Cloud Run's edge returned an
    # infrastructure 404 for /healthz on the reused service even while / served
    # the app correctly, so competition proof uses an unambiguous app-owned path.
    return _health_payload()


@app.get("/healthz")
async def healthz() -> dict:
    return _health_payload()


@app.get("/api/proof")
async def proof() -> dict:
    return {
        **judge_proof(),
        "source_sha": SOURCE_SHA,
        "live_proof_run": LIVE_PROOF_RUN,
        "judge_mode": "read_only_synthetic_evidence",
        "wave4_video": WAVE4_VIDEO,
        "repository": REPO_URL,
    }


@app.get("/api/synthetic-state")
async def synthetic_state() -> dict:
    return SYNTHETIC_STATE


def _page() -> str:
    proof_value = judge_proof()
    boundaries = "".join(
        f'<li><span class="n">{index}</span><span>{html.escape(item)}</span></li>'
        for index, item in enumerate(proof_value["durable_boundaries"], start=1)
    )
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HealthIA ONE — Judge Mode</title>
<style>
:root{{--bg:#07101c;--panel:#0d1a2a;--panel2:#101f31;--ink:#eef6ff;--muted:#9fb2c7;--line:#233952;--blue:#67b7ff;--green:#67e0a3;--amber:#ffd37d}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 20% 0%,#112a45 0,#07101c 34%,#050b13 100%);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}}
a{{color:var(--blue);text-decoration:none}} .wrap{{max-width:1180px;margin:auto;padding:34px 24px 56px}}
.top{{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:38px}} .brand{{font-weight:800;letter-spacing:.08em}} .badge{{border:1px solid #2f5677;background:#0b2033;border-radius:999px;padding:8px 12px;font-size:12px;color:#bfe4ff}}
.hero{{display:grid;grid-template-columns:1.25fr .75fr;gap:22px;align-items:stretch}} .card{{background:linear-gradient(180deg,rgba(17,35,54,.94),rgba(10,23,38,.94));border:1px solid var(--line);border-radius:20px;box-shadow:0 18px 60px rgba(0,0,0,.25)}} .heroMain{{padding:42px}}
h1{{font-size:52px;line-height:1.02;margin:0 0 16px;letter-spacing:-.04em}} .lead{{font-size:21px;line-height:1.5;color:#cad8e7;max-width:760px}} .trigger{{margin-top:28px;padding:18px 20px;border-left:4px solid var(--green);background:#0a1b2a;border-radius:12px;font-size:19px;font-weight:700}}
.metric{{padding:30px;display:flex;flex-direction:column;justify-content:center}} .big{{font-size:62px;font-weight:850;line-height:.95;color:var(--green)}} .metric p{{font-size:18px;line-height:1.45;color:#cbd9e8}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:22px}} .section{{padding:28px}} h2{{font-size:22px;margin:0 0 16px}} .small{{color:var(--muted);font-size:14px;line-height:1.55}}
ol{{list-style:none;padding:0;margin:18px 0 0}} li{{display:grid;grid-template-columns:38px 1fr;gap:12px;align-items:center;padding:13px 0;border-top:1px solid var(--line);color:#dce9f6}} .n{{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:#123b59;color:#dff3ff;font-weight:800}}
.flow{{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}} .pill{{padding:9px 11px;border:1px solid #294968;background:#0a1928;border-radius:10px;color:#cde7fb;font-size:13px}} .arrow{{color:#6384a0;align-self:center}}
.truth{{margin-top:22px;padding:20px 24px;border:1px solid #5b4e2b;background:#1b180e;border-radius:16px;color:#f5e4b7}} footer{{margin-top:28px;color:#8299ae;font-size:12px;display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap}}
@media(max-width:850px){{.hero,.grid{{grid-template-columns:1fr}}h1{{font-size:40px}}.big{{font-size:50px}}}}
</style>
</head>
<body><main class="wrap">
<div class="top"><div class="brand">HEALTHIA ONE</div><div class="badge">JUDGE MODE · READ ONLY · SYNTHETIC</div></div>
<section class="hero"><div class="card heroMain"><h1>Your health never starts over.</h1><p class="lead">A patient-owned continuity agent that preserves evidence, carries unfinished work across time, stops where human authority begins, resumes after consent, and requires durable execution evidence before it claims completion.</p><div class="trigger">{html.escape(proof_value['trigger'])}</div></div>
<div class="card metric"><div class="big">5</div><p><strong>durable boundaries</strong><br>{html.escape(proof_value['metric'])}</p><div class="small">0 model calls are required to detect the overdue follow-up or to decide that it is due.</div></div></section>
<section class="grid"><div class="card section"><h2>The unattended mission</h2><ol>{boundaries}</ol></div>
<div class="card section"><h2>What the judge can verify here</h2><div class="flow"><span class="pill">Evidence provenance</span><span class="arrow">→</span><span class="pill">Durable mission</span><span class="arrow">→</span><span class="pill">Consent boundary</span><span class="arrow">→</span><span class="pill">Google receipts</span><span class="arrow">→</span><span class="pill">Continuity</span></div><p class="small" style="margin-top:22px">This surface is intentionally non-operational: it exposes evidence and architecture without carrying credentials or mutation capability. The private autonomous workers remain behind Cloud Run IAM.</p><p><a href="{REPO_URL}">Inspect repository</a> · <a href="{WAVE4_VIDEO}">Open current autonomous Charon demo</a></p></div>
<div class="card section"><h2>Evidence-first</h2><p>Original synthetic clinical evidence is retained before AI interpretation. Structured state keeps provenance back to the source rather than turning a model answer into the source of truth.</p><div class="flow"><span class="pill">Original bytes</span><span class="arrow">→</span><span class="pill">Private GCS</span><span class="arrow">→</span><span class="pill">Bounded Gemini</span><span class="arrow">→</span><span class="pill">Firestore state</span></div></div>
<div class="card section"><h2>Google execution plane</h2><p>HealthIA has separate verified Google action evidence across Places, Gmail, Pub/Sub, Calendar and Tasks. External work is complete only after the real connector returns a durable resource or receipt.</p><div class="flow"><span class="pill">Places</span><span class="pill">Gmail</span><span class="pill">Pub/Sub</span><span class="pill">Calendar</span><span class="pill">Tasks</span></div></div></section>
<div class="truth"><strong>Clinical truth boundary.</strong> HealthIA does not autonomously diagnose, prescribe, change medication, or declare blood-pressure control. The promoted autonomous path is measurement continuity for an explicitly opted-in patient.</div>
<footer><span>Candidate source: {html.escape(SOURCE_SHA)}</span><span>Exact-head autonomy proof: {html.escape(LIVE_PROOF_RUN)}</span><span>GET-only evidence surface</span></footer>
</main></body></html>'''


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return _page()
