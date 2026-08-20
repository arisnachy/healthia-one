# HealthIA ONE — Final Devpost Submission Package

This document is the canonical text/form package for the **All Things Agentic Hackathon 2026** submission.

## Core submission

- **Project:** HealthIA ONE
- **Category:** Taskmaster
- **Tagline:** Your health never starts over — a patient-owned AI agent that turns evidence into durable, consent-aware missions and real-world action.
- **Official live product demo (~3:17):** https://youtu.be/44LfVn9pPdU
- **Public Judge Mode:** https://healthia-one-judge-1038180719788.us-central1.run.app
- **Repository:** https://github.com/arisnachy/healthia-one
- **Judge entry point:** https://github.com/arisnachy/healthia-one/blob/main/JUDGES_START_HERE.md
- **Architecture:** https://github.com/arisnachy/healthia-one/blob/main/docs/ARCHITECTURE.md
- **ONE SAFETY proof manifest:** https://github.com/arisnachy/healthia-one/blob/main/hackathon/evidence/one_safety_final_proof.json

Older 3:55 and 2:47 masters remain historical proof lineage only. V5 is the current judge-facing demo.

## Judge pitch

HealthIA ONE is a patient-owned, event-driven health continuity agent. Most health AI waits for the next prompt. HealthIA carries unfinished health work forward because the patient's authorized longitudinal state changed.

It combines Gemini 3.5 Flash + Google ADK for reasoning, deterministic policy for exact bounded decisions, durable Firestore state for continuity, and explicit human authority for consent and clinically sensitive boundaries.

The strongest V5 proof is not a chat response. It is a real autonomous external loop:

```text
no new chat prompt
→ overdue blood-pressure mission
→ Eventarc wakes a private worker
→ real Gmail message
→ controlled patient reply in the same thread
→ Gmail users.watch
→ authenticated Pub/Sub
→ VitalRecord 128/80 (source_type=patient_email_reply)
→ same durable mission COMPLETED
```

Completion is derived from durable external evidence, not from a model saying that something happened.

## What the V5 demo proves

### 1. Treatment-aware Result Guardian

A synthetic patient already has clinician-confirmed losartan treatment in the Patient Twin. A renal-function result containing creatinine arrives through the real Results workspace. Potassium evidence is still missing, so HealthIA opens a durable treatment-aware mission without a new chat prompt.

When potassium evidence arrives later, HealthIA links it to the same mission and closes that mission from durable evidence. HealthIA does not diagnose kidney disease or alter medication.

### 2. Appointment Guardian

A family-medicine appointment requires recent results, an active medication list and insurance. HealthIA verifies what already exists in longitudinal state, detects that insurance is missing, and creates a preparation mission. Uploading the insurance document causes the same mission to close.

### 3. Post-Visit Guardian

When the appointment becomes completed but no attributable consultation/discharge document exists, HealthIA opens a post-visit continuity mission rather than inventing the encounter. When the consultation note arrives, the mission closes from persisted evidence.

### 4. Live Gemini 3.5 Flash + Google ADK adaptive interview

Inside the real HealthIA Chat, Gemini 3.5 Flash generates a bounded adaptive interview. The recording gate requires a live `gemini_dynamic` response with exactly five case-specific questions before the scene is accepted.

### 5. Real autonomous external action

The V5 film then shows the overdue BP continuity path continuing outside chat: Eventarc, a private worker, Gmail, same-thread reply, Gmail users.watch, authenticated Pub/Sub, a 128/80 VitalRecord, and the same mission completing.

## Core HealthIA loop

```text
Signal / new evidence
→ Patient Twin
→ Guardian evaluation
→ durable mission
→ safe action or evidence wait
→ connector result / durable evidence
→ verified closure
→ updated Twin
```

Chat is one interface into the system. It is not the source of truth.

## Durable continuity

Firestore stores patient-scoped missions, treatment context, consent, evidence references, appointments, connector outcomes, device signals and longitudinal state. The Patient Twin is derived from canonical state rather than prompt history, so the health story survives process replacement and the end of a conversation.

## Evidence before interpretation

For supported synthetic clinical PDFs/images, original bytes are preserved first in private Google Cloud Storage. Gemini performs bounded extraction where appropriate, structured results are persisted with provenance, and unreliable extraction fails closed instead of fabricating a finding.

## ONE SAFETY — authorization is not execution evidence

```text
Sense / Request
→ Reason
→ Authorize
→ ONE SAFETY / deterministic Safety Kernel
→ one-use HealthActionTicket
→ real connector
→ durable receipt
→ OpenTelemetry / Google Cloud Trace
→ mission outcome
```

A model-generated success message cannot establish that the outside world changed. A connector outcome and durable receipt are required.

## Prompt-injection boundary

HealthIA uses Google Model Armor plus a local fail-closed ingress policy. The adversarial proof requires:

- Google Model Armor detects the controlled jailbreak probe;
- HTTP 400 at prompt ingress;
- `model_called == false`;
- zero new HealthActionTickets;
- zero patient-state mutation.

## Google technology

- Gemini 3.5 Flash on Vertex AI / Google GenAI
- Google Agent Development Kit (ADK)
- Google GenAI SDK
- Cloud Run
- Firestore
- private Google Cloud Storage
- Eventarc
- Gmail API + Gmail users.watch
- Pub/Sub
- Secret Manager + service identity / ADC
- Google Model Armor
- Google Places / Maps Platform
- Google Calendar
- Google Tasks
- OpenTelemetry + Google Cloud Trace
- Android / Health Connect bridge contracts

## Demo integrity

The V5 judging film is composed from a real continuous product recording. Long infrastructure wait periods caused by Cloud Run/Eventarc/Gmail/Pub/Sub latency were removed to fit the judging window. **No Guardian transition, Gemini answer, Gmail send, patient reply, 128/80 VitalRecord or mission completion was recreated or substituted.** The functional truth gate had to pass before the film could be accepted.

## Reproducible setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --port 8000
```

Verification:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
python scripts/smoke_test.py
```

Local deterministic verification can run with zero Google AI request budget. Controlled live/Cloud proofs are separate, explicit and request-capped.

## Devpost form values

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
| Google Cloud service(s) | **Cloud Run; Firestore; Pub/Sub; Eventarc; Cloud Storage; Secret Manager; Cloud Trace** |
| Google AI models | **Gemini 3.5 Flash (required core); Vertex AI Veo 3.1 Fast / `veo-3.1-fast-generate-001` (bonus lineage)** |
| Architecture diagram | **Required Devpost file upload; canonical architecture is `docs/ARCHITECTURE.md`** |
| Bonus public content | **https://github.com/arisnachy/healthia-one/issues/93** |
| Bonus social post | **https://x.com/i/status/2089481967821545835** |

## Bonus points

- Public build article: https://github.com/arisnachy/healthia-one/issues/93
- Social post: https://x.com/i/status/2089481967821545835
- Vertex AI Veo 3.1 Fast LIVE proof lineage: https://github.com/arisnachy/healthia-one/pull/43

## Clinical truth boundary

HealthIA ONE is a synthetic hackathon prototype and patient continuity system. It is not a physician, emergency service, autonomous prescription engine, regulated medical device or clinical-effectiveness study. It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

## Feature freeze

The judging runtime is frozen. Remaining edits are limited to reproducibility, evidence integrity and synchronization of public judge-facing materials.