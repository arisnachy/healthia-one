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

The patient describes a problem in natural language. Google ADK runs on demand, executes a real aggregate clinical baseline tool containing deterministic interview + safety checks, and Gemini 3.5 Flash generates exactly five context-specific questions under a structured-output contract. Later blocks receive prior questions/answers so the system avoids asking known facts again and decides when the interview is sufficiently complete to orient the patient to the next safe step.

### Evidence-first multimodal results

When the patient uploads a PDF or clinical image:

1. HealthIA stores the **original bytes first** in private Google Cloud Storage;
2. Gemini 3.5 Flash on Vertex AI extracts only readable/visible evidence into structured JSON;
3. Firestore stores the patient-scoped result/document state;
4. the clinical twin receives provenance linking the derived result to the original;
5. if AI interpretation fails, the original remains available and the result stays pending instead of inventing findings.

PDFs use low visual-media resolution with native PDF text to reduce latency/cost; clinical images retain high visual resolution.

### Closed-loop Taskmaster mission

A later request such as “explain the result I just uploaded” retrieves the **persisted** result and original-document metadata, returns the saved patient explanation/original link and closes a `result_explanation` mission only when the evidence exists. The completed mission retains correlated result/document evidence and survives logout/login and a real Cloud Run revision while remaining invisible to another authenticated patient.

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

The clinical ADK path executes one real function-tool trajectory (`inspect_clinical_baseline`) that runs mandatory interview + safety checks. Tool execution is audited separately, and the runtime reconstructs specialist evidence from what actually executed instead of trusting model prose.

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

No Gemini API key is injected into the Cloud Run proof deployment. The Python dependency boundary uses Google ADK core plus explicitly declared Firestore/GCS clients instead of an unused broad GCP extras bundle.

## Architecture

See `docs/ARCHITECTURE.md` for the Mermaid architecture and evidence-flow diagrams.

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
- explicit opt-in billable Cloud proof/recording/publication workflows.

## What we actually proved

### Continuous final judge demo — PASS

GitHub Actions run **`31265639488`** produced a continuous unmocked WebM after the exact candidate first passed the full repository verification gate.

- candidate SHA: `3f99e511f6518e8dc9b45ebfd0cbdc37aaa9768e`
- artifact: `HealthIA-ONE-final-judge-demo` (`9024139098`)
- artifact digest: `sha256:71ee6e2ce665a9b98e44ca11aae7c7334849b73ac7e756b157afa47b3a249f33`
- video SHA-256: `cfd91b0d08cf6659e1fb924c2e85071cd3b79bd414578b7112908c46f91adb19`
- duration: `290.16 s`
- live revision shown: `healthia-one-demo-00016-mct`
- live model: `gemini-3.5-flash`
- ADK ready: true
- store/evidence: Firestore / GCS
- zero browser console/page errors
- synthetic data only

The recording visibly covers the problem, value proposition, live Gemini+ADK clinical interaction, multimodal result, original-document evidence, clinical twin, completed Taskmaster mission, relogin continuity and the `.run.app` Cloud runtime/readiness proof.

Permanent sanitized evidence: `hackathon/evidence/final_judge_demo_proof.json`.

### Stable public judge video — PASS

The exact WebM above is published as a public GitHub Release asset:

`https://github.com/arisnachy/healthia-one/releases/download/healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm`

Publication proof run **`31267268584`** recovered the original passing artifact, revalidated the source SHA, published the Release asset, then downloaded the public URL without credentials and matched the same SHA-256. Artifact `9024528554` (`HealthIA-ONE-GitHub-release-video-proof`) preserves that proof. Independent public probe run **`31267268597`** also downloaded the full URL without credentials and matched the same bytes; artifact `9024526089` preserves that second proof.

Permanent sanitized evidence: `hackathon/evidence/public_judge_video_proof.json`.

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

1. **Agentic does not mean always-on.** Event-driven/demand-driven agents are easier to audit, cheaper and more natural for patient continuity than a permanent swarm.
2. **Evidence must exist before interpretation.** Persisting original bytes before Gemini creates a recoverable provenance boundary.
3. **Tool evidence should come from execution, not model prose.** HealthIA reconstructs the ADK specialist trace from tools that actually ran.
4. **Latency needs architecture, not bigger timeouts.** One bounded ADK tool call, minimal thinking, structured output and bounded response size made the clinical path reliable.
5. **Multimodal latency is media-dependent.** Low PDF visual resolution + native text and a compact schema removed the live Cloud timeout while retaining high image resolution for clinical images.
6. **Durability must be tested across a process boundary.** The project proves persistence across a genuinely new Cloud Run revision, not just refresh/logout.
7. **Cost control is architecture.** Hidden automatic deployment was removed; billable proofs and the recorder require explicit opt-in.
8. **Demo evidence should be reproducible.** The final judge video is generated by a gated workflow that first requires the same SHA to pass the full technical regression suite, then its public Release bytes are independently revalidated.

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

The proof service is private at the Cloud Run IAM boundary even though the application also has patient authentication. Use the proven deployment only if judge access is intentionally enabled/provided; otherwise omit the optional interactive hosted URL rather than claiming a private endpoint is public.

Proven Cloud URL: `https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app`

## Demo video

**FINAL PUBLIC/JUDGE VIDEO URL:**

`https://github.com/arisnachy/healthia-one/releases/download/healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm`

Release page:

`https://github.com/arisnachy/healthia-one/releases/tag/healthia-one-hackathon-judge-demo-2026`

Video SHA-256: `cfd91b0d08cf6659e1fb924c2e85071cd3b79bd414578b7112908c46f91adb19`.

## Submission status

PR #29 was merged as `a1525ec` after its preserved candidate completed CI/JUDGE. Its **100/100** evidence score applies to that candidate only; the current working tree is not a replacement submission until it receives a fresh exact-head gate.

PR #29 was merged as `a1525ec` after its exact candidate head passed CI/JUDGE. For any later change, the operational sequence is: fresh exact-head CI/JUDGE → preserve or intentionally replace the submission evidence → use this repository, architecture diagram, description and public video URL in Devpost.
