# HealthIA ONE — Devpost submission draft

## Category

**The Taskmaster**

## One-line pitch

**HealthIA ONE turns a patient's scattered health evidence into durable, patient-scoped missions: it asks what is missing, preserves the original, uses Gemini + Google ADK to do the work, updates a longitudinal clinical twin, and closes the task only when the evidence-backed outcome actually exists.**

## The problem

A patient's health context is fragmented across PDFs, images, laboratory portals, medications, devices, family history and memory. Most AI health experiences are still transient chat: they can discuss a result once but do not reliably preserve the original evidence, reconnect it to longitudinal state, or prove that a multi-step task was actually completed.

HealthIA ONE treats continuity itself as the job.

## What HealthIA ONE does

### Adaptive patient interview

The patient describes a problem in natural language. Google ADK runs on demand, executes a real aggregate clinical baseline tool containing deterministic interview + safety checks, and Gemini 3.5 Flash generates exactly five context-specific questions under a structured-output contract. Later blocks receive the prior questions/answers so the system can avoid asking known facts again and decide when the interview is sufficiently complete to orient the patient to the next safe step.

### Evidence-first multimodal results

When the patient uploads a PDF or clinical image:

1. HealthIA stores the **original bytes first** in private Google Cloud Storage;
2. Gemini 3.5 Flash on Vertex AI extracts only readable/visible evidence into structured JSON;
3. Firestore stores the patient-scoped result/document state;
4. the clinical twin receives provenance linking the derived result to the original;
5. if AI interpretation fails, the original remains available and the result stays pending instead of inventing findings.

PDFs use Gemini 3 low visual-media resolution with native PDF text to reduce latency/cost; clinical images retain high visual resolution.

### Closed-loop Taskmaster mission

A later request such as “explain the result I just uploaded” retrieves the **persisted** result and original-document metadata, returns the saved patient explanation/original link and closes a `result_explanation` mission only when the evidence exists. The completed mission retains correlated `result_id`, `document_id` and closure markers.

That closed outcome survives logout/login and a real Cloud Run revision while remaining invisible to another authenticated patient.

## Why it is agentic

HealthIA is not a permanent swarm and not a prompt wrapper. Work is event-driven and demand-driven:

```text
patient/event goal
  → auth + deterministic safety boundary
  → load patient-scoped longitudinal state
  → Google ADK / Gemini action only when needed
  → durable outcome + evidence
  → patient-visible state update
```

The clinical ADK path executes one real function-tool trajectory (`inspect_clinical_baseline`) that runs mandatory interview + safety checks. Tool execution is audited separately, and the runtime reconstructs specialist evidence from what actually executed instead of trusting the model to claim it did.

## Google technologies

- **Gemini 3.5 Flash**
- **Vertex AI** through Google Cloud ADC/service identity
- **Google Agent Development Kit (ADK)**
- **Cloud Run**
- **Firestore**
- **Google Cloud Storage**
- **Secret Manager**
- **Cloud Build**
- Google GenAI SDK / Interactions transport

No Gemini API key is injected into the Cloud Run proof deployment.

## Architecture

See `docs/ARCHITECTURE.md` for the Mermaid architecture and evidence-flow diagrams.

High-level path:

```text
Patient UI
  → Cloud Run / FastAPI
  → patient auth + policy boundary
     ↳ Google ADK Runner → interview+safety tool → Gemini 3.5 structured questions
     ↳ multimodal pipeline → original GCS → Gemini 3.5 extraction
  → Firestore canonical state + missions
  → provenance-linked clinical twin
  → patient UI / persisted outcome
```

## Data sources

The hackathon/demo paths use **synthetic patients and synthetic clinical files only**. The system may also accept patient-entered longitudinal state and a signed Android/Health Connect device bridge contract, but no real patient record is required for the submission demo.

## Production-minded boundaries

- signed `HttpOnly` patient sessions;
- salted `scrypt` account hashes;
- patient-scoped Firestore state;
- private patient-scoped GCS object paths;
- cross-patient document denial;
- signed patient/device/connection identity;
- separate Cloud Build and Cloud Run service identities;
- explicit AI request ceilings;
- Cloud Run min `0`, max `1` for the bounded proof environment;
- proactive agent work disabled by default;
- original evidence persisted before model interpretation;
- fail-closed multimodal behavior;
- explicit opt-in billable Cloud proof workflows.

## What we actually proved

### Exact-candidate Cloud + browser — PASS

GitHub Actions run **`31262429792`** froze candidate SHA `a28955c3641c37a9e5a06f5f0ccf943ccb197bbd`, deployed it to Google Cloud and passed both the strict API proof and a complete unmocked Chromium journey.

- Cloud Run proof revision: `healthia-one-demo-00012-jvl`
- Cloud Run URL: `https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app`
- Gemini 3.5 Flash / Vertex AI / ADC
- real Google ADK tool trajectory
- two adaptive five-question blocks
- multimodal PDF extraction
- Firestore state
- private GCS original evidence
- clinical-twin provenance
- completed Taskmaster mission
- two-patient isolation
- logout/relogin restoration
- zero browser console/page errors

Sanitized permanent evidence: `hackathon/evidence/cloud_exact_candidate_proof.json`.

### Cross-revision continuity — PASS

GitHub Actions run **`31262903731`** prepared durable patient A/B state, forced a genuinely new Cloud Run revision with the **same image**, then reauthenticated and independently read back application/Firestore/GCS state.

- before: `healthia-one-demo-00013-2bz`
- after: `healthia-one-demo-00014-ns8`
- same image: true
- result/document/completed mission/twin persisted
- GCS generation unchanged
- original SHA-256 unchanged
- patient B remained isolated

Sanitized permanent evidence: `hackathon/evidence/cloud_revision_continuity_proof.json`.

### Earlier one-request Vertex proof — PASS

Run `31228561751` demonstrated that after one Gemini multimodal request persists the original/result/twin, HealthIA can retrieve that evidence and close the Taskmaster mission without spending a second Gemini request merely to restate it.

### Evidence excluded

Run `31203021748` ended in HTTP 429 due depleted credits/quota and is **not** counted as passing evidence.

Full index: `docs/EVIDENCE.md`.

## Findings and learnings

1. **Agentic does not mean always-on.** For a patient system, event-driven/demand-driven agents are easier to audit, cheaper and more natural than a permanent swarm.
2. **Evidence must exist before interpretation.** Persisting original bytes before Gemini creates a safe provenance boundary and makes failure recoverable.
3. **Tool evidence should come from execution, not model prose.** HealthIA reconstructs the ADK specialist trace from tools that actually ran.
4. **Latency needs architecture, not bigger timeouts.** The clinical path became reliable after collapsing mandatory checks into one ADK tool call, using Gemini minimal thinking, structured output and bounded response size.
5. **Multimodal latency is media-dependent.** Low PDF visual resolution + native text and a compact schema removed a live Cloud timeout without lowering image fidelity for clinical images.
6. **Durability must be tested across a process boundary.** Logout/login is useful but not enough; the project now proves persistence across a genuinely new Cloud Run revision.
7. **Cost control is part of architecture.** A legacy automatic deployment route discovered during testing was retired; billable evidence workflows now require explicit opt-in.

## Spin-up instructions

### Local zero-spend mode

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --port 8000
```

Windows also includes `deployment/run-local-secure.ps1`.

### Cloud proof deployment

```powershell
.\deployment\deploy-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -RequestLimit 20
```

The project expects required Google Cloud APIs/permissions to be preconfigured and fails closed otherwise. See `README.md` and `deployment/check_cloud_permissions.py`.

## Repository

`https://github.com/arisnachy/healthia-one`

## Hosted project

**Final submission choice:** use the proven Cloud Run deployment only if judge access is intentionally enabled/provided. The current proof service is private at the Cloud Run IAM boundary even though the application itself also has patient authentication.

Proven Cloud URL: `https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app`

If the final Devpost field requires direct interactive judge access, either provide an explicit judge-access mechanism or omit the optional hosted URL rather than claiming that a private endpoint is publicly testable.

## Demo video

**FINAL VIDEO URL: TODO**

Use `docs/DEMO_SCRIPT.md`. The final recording must be approximately four minutes, unedited, and visibly show the live application plus Google Cloud evidence.

## Submission status

Technical hard gates are green. JUDGE Ω currently scores the evidence-backed candidate **98/100** and deliberately withholds the last two Demo & Production Readiness points until the final unedited video/submission package exists.

Do not claim `100/100` or `SUBMISSION_LOCKED` until the video URL/package is present and final CI/JUDGE passes on the exact submission head.
