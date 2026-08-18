# HealthIA ONE — Final Devpost Submission Package

This document is the canonical text/form package for the **All Things Agentic Hackathon 2026** submission.

## Core submission

- **Project:** HealthIA ONE
- **Category:** Taskmaster
- **Tagline:** Your health never starts over — a patient-owned AI agent that turns evidence into durable, consent-aware missions and real-world action.
- **Official demo video (3:55):** https://youtu.be/v7SJUkzzRxw
- **Public Judge Mode:** https://healthia-one-judge-1038180719788.us-central1.run.app
- **Repository:** https://github.com/arisnachy/healthia-one
- **Judge entry point:** https://github.com/arisnachy/healthia-one/blob/main/JUDGES_START_HERE.md
- **Architecture:** https://github.com/arisnachy/healthia-one/blob/main/docs/ARCHITECTURE.md
- **Final proof manifest:** https://github.com/arisnachy/healthia-one/blob/main/hackathon/evidence/one_safety_final_proof.json

## Judge pitch

HealthIA ONE is a patient-owned, event-driven health continuity agent. It turns fragmented clinical evidence and unfinished health work into durable missions that survive the chat window. Gemini 3.5 Flash + Google ADK reason when interpretation or planning adds value; deterministic policy protects exact bounded choices; human authority owns consent and clinically sensitive decisions; and ONE SAFETY requires a one-use execution ticket plus a real connector receipt before external work can be represented as complete.

The final proof package demonstrates real Google Cloud execution, Google Model Armor prompt-injection blocking, Firestore continuity, bounded Google Places action, OpenTelemetry/Cloud Trace correlation, and event-driven unattended follow-up behavior using synthetic patient data.

## What it does

```text
patient need / health signal / clinical evidence
  → patient identity + patient-scoped durable context
  → prompt ingress safety: Google Model Armor + local policy
  → Gemini 3.5 Flash + Google ADK when reasoning is useful
  → deterministic policy when exactness is safer
  → human authority when the decision belongs to the patient
  → durable mission
  → ONE SAFETY / Safety Kernel
  → one-use HealthActionTicket
  → real Google connector
  → durable receipt
  → OpenTelemetry / Google Cloud Trace
  → Patient Twin + longitudinal outcome
```

### Durable continuity

Firestore stores patient-scoped missions, consent, evidence references, connector outcomes, device signals and longitudinal state. The Patient Twin is derived from canonical state rather than prompt history, so the same patient story survives logout/login and process replacement.

### Evidence before interpretation

For supported synthetic clinical PDFs/images, original bytes are preserved first in private Google Cloud Storage. Gemini then performs bounded multimodal extraction, structured results are persisted, and the Patient Twin preserves provenance. Unreliable extraction fails closed instead of inventing a finding.

### Human authority + real Google action

HealthIA can create a resource-navigation mission before location consent but performs no Places search merely because the mission exists. After mission-scoped consent, the same durable mission resumes and the real Google Places connector may execute.

Exact bounded choices such as **“The second one”** are resolved deterministically from the ordered candidate list rather than sent through another probabilistic model call.

### ONE SAFETY

A real external action follows:

```text
Sense / Request
→ Reason
→ Authorize
→ ONE SAFETY
→ HealthActionTicket
→ Connector
→ Receipt
→ Cloud Trace
```

Authorization is not execution evidence. The final proof correlates a real Places execution across:

- Cloud Trace `eec691300b7bb1c1c0564e95fb090e4f`
- HealthActionTicket `hat_021b1b6b1b4542e2`
- action `maps.search_nearby`
- receipt `receipt_95ba26286e6f4e15`
- outcome `completed`

The promotion gate queried Google Cloud Trace using that exact Trace ID and required the guarded execution span `google.action.guarded_execute`.

### Prompt-injection boundary

The final adversarial proof requires:

- real Google Model Armor `MATCH_FOUND` for the controlled jailbreak probe;
- HTTP `400` at HealthIA `prompt_ingress`;
- `model_called = false`;
- zero new HealthActionTickets;
- zero patient-state mutation.

### Unattended continuity

For an opted-in synthetic patient, an overdue blood-pressure follow-up can become durable work without a fresh chat prompt. Event-driven Google infrastructure wakes the worker, authorized work proceeds, a real reply can return through authenticated event infrastructure, and HealthIA resumes the same mission.

## Google technology

- Gemini 3.5 Flash on Vertex AI / Google GenAI
- Google Agent Development Kit (ADK)
- Google GenAI SDK
- Cloud Run
- Firestore
- private Google Cloud Storage
- Secret Manager + service identity / ADC
- Google Model Armor
- Google Places / Maps Platform
- Gmail API
- Pub/Sub
- Google Calendar
- Google Tasks
- OpenTelemetry + Google Cloud Trace
- Android / Health Connect bridge contracts

## Reproducible setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --port 8000
```

Windows:

```powershell
.\deployment\run-local-secure.ps1
```

Verification:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
python scripts/smoke_test.py
```

Local deterministic verification can run with zero Google AI request budget. Controlled Cloud/live proofs are separate, explicit and request-capped.

## Exact final proof package

| Item | Value |
|---|---|
| Runtime candidate under Cloud proof | `a851947c9e1476d2fed05f74b2b40383c408387f` |
| Proof harness | `51c641d89a4c59bd57275ffa6ef98820394f9634` |
| Model Armor adversarial run | `32051146784` — SUCCESS |
| Enhanced ONE SAFETY run | `32054818666` — SUCCESS |
| Enhanced artifact ID | `9296123186` |
| Enhanced artifact ZIP SHA-256 | `253a474e7a8bd7fce373f3ff1f5697e0522f27810fe76d33dd4a902366cd9365` |
| Validated base master SHA-256 | `809d35ff7b2a3242eb61f52443c64f48a0ca45fc2e078ad1165ae76f724b1565` |
| Final 3:55 MP4 SHA-256 | `2c82929888c613960cb44ba7cb0c111b22e8a205cf38643d3199f3a1c5e542cf` |
| Charon audio SHA-256 | `3a78b5e3b98c441b138b691d803e2f3859e51e2a2795db22314d6ea4b230cc16` |

## Devpost form values

These are the canonical values to use when editing/re-submitting the Devpost form.

| Devpost field | Canonical answer |
|---|---|
| Submitter Type | **Individuals** |
| Submitter country of residence | **Dominican Republic** |
| Category | **Taskmaster** |
| Organization name | **N/A — individual submission** |
| Project start date | **08-05-26** |
| Code repository | **https://github.com/arisnachy/healthia-one** |
| Reproducible Testing instructions in README | **Yes** |
| Hosted project URL | **https://healthia-one-judge-1038180719788.us-central1.run.app** |
| Google SDK(s) | **Agent Development Kit (ADK); Google GenAI SDK (google-genai)** |
| Google Cloud service(s) | **Cloud Run; Firestore; Pub/Sub** |
| Google AI models | **Gemini 3.5 Flash (required core); Vertex AI Veo 3.1 Fast / `veo-3.1-fast-generate-001` (bonus integration lineage)** |
| Architecture diagram | **Required Devpost file upload; diagram source is `docs/ARCHITECTURE.md`** |
| Bonus public content | **https://github.com/arisnachy/healthia-one/issues/93** |
| Bonus social post | **https://x.com/i/status/2089481967821545835** |

### Testing instructions for judges

Public Judge Mode is synthetic, read-only and credential-free. Operational workers remain private. All hackathon patient/device examples use synthetic data. The repository contains zero-spend local setup and deterministic verification commands. Exact Cloud proof identifiers and sanitized evidence are linked from `JUDGES_START_HERE.md` and `hackathon/evidence/one_safety_final_proof.json`.

## Architecture upload guidance

The Devpost architecture attachment should visibly show:

```text
Patient / Signal / Upload
→ HealthIA ONE UI
→ FastAPI on Cloud Run
→ identity + scoped context
→ Model Armor + local prompt policy
→ decision mode
   ↳ Google ADK + Gemini 3.5 Flash
   ↳ deterministic policy
   ↳ human authority
→ Firestore durable mission / Patient Twin
→ ONE SAFETY
→ one-use HealthActionTicket
→ Google connectors
→ durable receipt
→ OpenTelemetry
→ Google Cloud Trace
```

The canonical architecture and failure semantics are in `docs/ARCHITECTURE.md`.

## Bonus points

### Public build content

https://github.com/arisnachy/healthia-one/issues/93

The public article contains the required declaration that it was created for the purpose of entering the All Things Agentic Hackathon 2026.

### Social post

https://x.com/i/status/2089481967821545835

The prepared/published post includes `#AllThingsAgenticHackathon`.

### Additional Google AI model

HealthIA Explain has an implemented and LIVE-proven **Vertex AI Veo 3.1 Fast** path preserved in PR #43. It uses a prevalidated generic educational prompt and the proof records `synthetic_only: true` and `patient_data_sent: false`. This bonus lineage is intentionally separate from the frozen final ONE SAFETY runtime.

## Clinical truth boundary

HealthIA ONE is a synthetic hackathon prototype and patient continuity system. It is not a physician, emergency service, autonomous prescription engine, regulated medical device or clinical-effectiveness study. It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

## Feature freeze

The judging runtime is frozen. Remaining edits are limited to reproducibility, evidence integrity and synchronization of public judge-facing materials.
