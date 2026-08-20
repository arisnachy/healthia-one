# HealthIA ONE — Judges: Start Here

> **Your health never starts over.**

HealthIA ONE is a patient-owned, event-driven health continuity agent. It is not a chatbot with a long prompt. It keeps canonical patient state, turns new evidence and unfinished health work into durable missions, uses Gemini when reasoning adds value, uses deterministic policy when exactness is safer, and stops at explicit human-authority boundaries.

## Start here

1. **Official live product demo — ~3:17:** https://youtu.be/44LfVn9pPdU
2. **Public Judge Mode:** https://healthia-one-judge-1038180719788.us-central1.run.app
3. **Architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
4. **Canonical Devpost package:** [`docs/DEVPOST_SUBMISSION.md`](docs/DEVPOST_SUBMISSION.md)
5. **ONE SAFETY machine-readable proof:** [`hackathon/evidence/one_safety_final_proof.json`](hackathon/evidence/one_safety_final_proof.json)
6. **Autonomous continuity evidence:** [`docs/AUTONOMOUS_CONTINUITY.md`](docs/AUTONOMOUS_CONTINUITY.md)

The YouTube V5 demo is the current judge-facing film. Older 3:55 and 2:47 masters are historical proof lineage only and are **not** the current entry point.

## What V5 proves inside the real product

All demo patient data is synthetic.

### 1. Result Guardian — longitudinal evidence creates work

A clinician-confirmed losartan treatment already exists in the Patient Twin. A renal-function result containing creatinine arrives through the real Results workspace. HealthIA sees that relevant potassium evidence is still missing and opens a durable treatment-aware mission **without a new chat prompt**.

When potassium evidence arrives later, HealthIA links it to the same mission and closes that mission from durable evidence. It does not diagnose kidney disease or change medication.

### 2. Appointment Guardian — the Twin prepares the visit

A family-medicine appointment requires recent results, an active medication list and insurance. HealthIA can verify the first two from longitudinal state. Insurance is missing, so it creates an appointment-preparation mission. When the insurance document is uploaded through the real Documents workspace, the same mission closes.

### 3. Post-Visit Guardian — continuity survives the encounter

When the appointment becomes completed but no attributable consultation/discharge document exists, HealthIA opens a post-visit continuity mission instead of inventing what happened. When the consultation note arrives, the same mission closes from persisted evidence.

### 4. Live Gemini 3.5 Flash + Google ADK

Inside the real HealthIA Chat, Gemini 3.5 Flash produces a bounded adaptive clinical interview. The recording gate requires the live response to report `gemini_dynamic` and exactly five case-specific questions before the scene is accepted. Google ADK coordinates the clinical capabilities while the Patient Twin remains the continuity layer underneath the conversation.

### 5. Real autonomous external follow-up

This is the strongest Taskmaster proof in V5:

```text
no new chat prompt
→ overdue BP mission
→ Eventarc wakes a private worker
→ real Gmail message sent
→ controlled patient reply in the same thread
→ Gmail users.watch
→ authenticated Pub/Sub
→ VitalRecord 128/80 with source_type=patient_email_reply
→ the same durable mission becomes COMPLETED
```

The trigger path is bounded and does not use the model to decide whether the external action happened. Completion comes from durable external evidence.

## Why this is agentic rather than conversational

```text
Signal / new evidence
→ Patient Twin
→ Guardian evaluation
→ durable mission
→ safe action or evidence wait
→ real evidence / connector result
→ verified closure
→ updated Twin
```

Chat is one interface into this system. It is not the source of truth.

## Safety and authority boundary

HealthIA separates three decision modes:

1. **AI reasoning** — interpretation, multimodal extraction, adaptive questioning.
2. **Deterministic logic** — exact state transitions, idempotency, policy and safety invariants.
3. **Human authority** — consent and clinically sensitive decisions.

HealthIA does **not** autonomously diagnose, prescribe, start/stop/change medication or replace professional or emergency evaluation.

## ONE SAFETY — authorization is not execution evidence

Protected real-world actions cross a narrow audited chain:

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

A model-generated success message cannot make an external mutation true. A connector result and durable receipt are required.

The promoted ONE SAFETY proof also preserves a real Google Places execution correlated across Cloud Trace, HealthActionTicket, connector receipt and completed mission outcome. That older proof remains valuable supporting evidence, but V5 is the current film.

## Prompt-injection boundary

HealthIA uses Google Model Armor plus a local fail-closed ingress policy. The adversarial proof requires all of these simultaneously:

- Google Model Armor detects the controlled jailbreak probe;
- HTTP 400 at prompt ingress;
- `model_called == false`;
- zero new HealthActionTickets;
- zero patient-state mutation.

## Current Google architecture

| Concern | Current implementation |
|---|---|
| Reasoning / multimodal | Gemini 3.5 Flash on Vertex AI / Google GenAI |
| Agent framework | Google Agent Development Kit (ADK) |
| Runtime | Cloud Run |
| Durable patient / mission state | Firestore |
| Original clinical evidence | Private Google Cloud Storage |
| Prompt-injection boundary | Google Model Armor + local fail-closed policy |
| Action authorization | ONE SAFETY / deterministic Safety Kernel |
| Execution capability | One-use HealthActionTicket |
| External continuity | Eventarc + Gmail + Gmail users.watch + Pub/Sub |
| Other bounded workflows | Google Calendar + Google Tasks + Google Places |
| Secrets / identity | Secret Manager + ADC / dedicated service accounts |
| Execution evidence | Durable connector receipts |
| Observability | OpenTelemetry + Google Cloud Trace |
| Device path | Android / Health Connect bridge contracts |

## Demo integrity note

The V5 judging film is composed from a real continuous product recording. Long infrastructure wait periods caused by Cloud Run/Eventarc/Gmail/Pub/Sub latency were removed for the ~4-minute judging format. **No Guardian transition, Gemini answer, Gmail send, patient reply, 128/80 VitalRecord, or mission completion was recreated or substituted.** The recording workflow required the underlying functional gate to pass before the film could be accepted.

## Reproduce without Google AI spend

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --port 8000
```

Technical gates:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
python scripts/smoke_test.py
```

## Bonus evidence

- Public build article: https://github.com/arisnachy/healthia-one/issues/93
- Public X post: https://x.com/i/status/2089481967821545835
- Vertex AI Veo 3.1 Fast LIVE proof lineage: https://github.com/arisnachy/healthia-one/pull/43

See [`docs/HACKATHON_BONUS_POINTS.md`](docs/HACKATHON_BONUS_POINTS.md).

## Clinical truth boundary

HealthIA ONE is a synthetic hackathon prototype and patient continuity system. It is not a physician, emergency service, autonomous prescription engine, regulated medical device or clinical-effectiveness study. Green software and Cloud proofs establish tested software behavior; they do not establish medical efficacy or regulatory approval.

## The one sentence to remember

**HealthIA carries unfinished patient work forward, notices when the authorized Twin changes, does every safe step it can prove, and stops exactly where human authority begins.**