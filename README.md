# HealthIA ONE

> **Your health never starts over.**

**All Things Agentic Hackathon 2026 · Taskmaster**

HealthIA ONE is a patient-owned, event-driven health continuity agent. It turns fragmented health evidence and unfinished work into **durable, consent-aware missions**, uses Gemini only where reasoning adds value, performs bounded real-world actions through Google services, and requires real evidence before claiming that the outside world changed.

## Judges — start here

- **Official live product demo (~3:17):** https://youtu.be/44LfVn9pPdU
- **Judge guide:** [`JUDGES_START_HERE.md`](JUDGES_START_HERE.md)
- **Public Judge Mode:** https://healthia-one-judge-1038180719788.us-central1.run.app
- **Architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **Canonical Devpost package:** [`docs/DEVPOST_SUBMISSION.md`](docs/DEVPOST_SUBMISSION.md)
- **ONE SAFETY proof:** [`hackathon/evidence/one_safety_final_proof.json`](hackathon/evidence/one_safety_final_proof.json)

Older 3:55 / 2:47 videos are historical proof lineage only. **V5 is the current judging demo.**

## The 20-second product model

```text
health signal / new evidence / unfinished work
→ patient-scoped canonical state
→ Patient Twin
→ Guardian evaluation
→ durable mission
→ Gemini 3.5 Flash + Google ADK when reasoning is useful
→ deterministic policy when exactness is safer
→ explicit human authority where required
→ safe action / evidence wait
→ real connector result or durable evidence
→ verified closure
→ updated Twin
```

Chat is one interface into this system. It is not the source of truth.

## What the V5 judging demo proves

### Result Guardian

A clinician-confirmed losartan treatment already exists in the synthetic Patient Twin. When renal-function evidence containing creatinine arrives, HealthIA detects that relevant potassium evidence is still missing and opens a durable mission **without a new chat prompt**. When potassium evidence later arrives, HealthIA closes that same mission from persisted evidence.

### Appointment Guardian

Before a family-medicine visit, HealthIA verifies what the Twin already knows, detects that required insurance evidence is missing, and creates a preparation mission. Uploading the insurance document causes the same mission to close.

### Post-Visit Guardian

When an appointment becomes completed but no attributable consultation/discharge record exists, HealthIA opens a continuity mission instead of inventing the encounter. When the consultation note arrives, that mission closes from durable evidence.

### Live Gemini + Google ADK

Inside the real HealthIA Chat, Gemini 3.5 Flash generates a bounded adaptive interview. The recording gate requires the live response to report `gemini_dynamic` and exactly five case-specific questions before the scene is accepted.

### Real autonomous external follow-up

```text
no new chat prompt
→ overdue BP mission
→ Eventarc wakes a private worker
→ real Gmail message
→ controlled reply in the same thread
→ Gmail users.watch
→ authenticated Pub/Sub
→ VitalRecord 128/80 (source_type=patient_email_reply)
→ same durable mission COMPLETED
```

This path proves autonomy outside the chat window. Completion comes from durable external evidence, not from a model claim.

## Safety model

HealthIA deliberately separates:

1. **AI reasoning** for interpretation, multimodal extraction and adaptive questioning.
2. **Deterministic logic** for exact state transitions, idempotency and safety invariants.
3. **Human authority** for consent and clinically sensitive decisions.

HealthIA does **not** autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

## ONE SAFETY

Protected external actions follow:

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

Authorization is not execution evidence. A model-generated success message cannot make an outside-world mutation true.

## Google technology

| Concern | HealthIA ONE |
|---|---|
| Reasoning / multimodal | **Gemini 3.5 Flash on Vertex AI / Google GenAI** |
| Agent framework | **Google Agent Development Kit (ADK)** |
| Runtime | **Cloud Run** |
| Durable patient / mission state | **Firestore** |
| Original clinical evidence | **Private Google Cloud Storage** |
| Prompt injection boundary | **Google Model Armor + local fail-closed policy** |
| Secrets / service identity | **Secret Manager + ADC / dedicated service accounts** |
| External continuity | **Eventarc + Gmail + Gmail users.watch + Pub/Sub** |
| Other bounded workflows | **Google Places + Calendar + Tasks** |
| Observability | **OpenTelemetry + Google Cloud Trace** |
| Device path | **Android / Health Connect bridge contracts** |

## Demo integrity

The V5 judging film is composed from a real continuous product recording. Long infrastructure wait periods caused by Cloud Run/Eventarc/Gmail/Pub/Sub latency were removed to fit the judging window. **No Guardian transition, Gemini answer, Gmail send, patient reply, 128/80 VitalRecord or mission completion was recreated or substituted.** The functional truth gate had to pass before the film could be accepted.

## Reproduce from scratch — zero Google AI spend

Requirements: Git and Python 3.12+.

```bash
git clone https://github.com/arisnachy/healthia-one.git
cd healthia-one
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verification:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
python scripts/smoke_test.py
```

## Repository map

- [`JUDGES_START_HERE.md`](JUDGES_START_HERE.md) — judge-first evidence map
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture and failure semantics
- [`docs/AUTONOMOUS_CONTINUITY.md`](docs/AUTONOMOUS_CONTINUITY.md) — unattended continuity
- [`docs/DEVPOST_SUBMISSION.md`](docs/DEVPOST_SUBMISSION.md) — canonical submission package
- [`docs/HACKATHON_BONUS_POINTS.md`](docs/HACKATHON_BONUS_POINTS.md) — bonus evidence
- [`hackathon/evidence/`](hackathon/evidence/) — sanitized proof material

## Bonus evidence

- Public build article: https://github.com/arisnachy/healthia-one/issues/93
- Public X post: https://x.com/i/status/2089481967821545835
- Vertex AI Veo 3.1 Fast LIVE proof lineage: https://github.com/arisnachy/healthia-one/pull/43

## Clinical truth boundary

HealthIA ONE is a synthetic hackathon prototype and patient continuity system. It is **not** a physician, emergency service, autonomous prescription engine, regulated medical device or clinical-effectiveness study. All hackathon patient/device demonstrations use synthetic data.

---

**HealthIA carries unfinished patient work forward, notices when the authorized Twin changes, does every safe step it can prove, and stops exactly where human authority begins.**