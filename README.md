# HealthIA ONE

> **Your health never starts over.**

**All Things Agentic Hackathon 2026 · Taskmaster**

HealthIA ONE is a patient-owned, event-driven health continuity agent. It turns fragmented health evidence and unfinished work into **durable, consent-aware missions**, uses Gemini only where reasoning adds value, performs bounded real-world actions through Google services, and requires execution evidence before claiming that the outside world changed.

## Judges — start here

- **Official Devpost demo (3:55):** https://youtu.be/v7SJUkzzRxw
- **Byte-verifiable final ONE SAFETY master:** https://github.com/arisnachy/healthia-one/releases/download/healthia-one-autonomous-winner-demo-2026/HealthIA-ONE-Autonomous-Taskmaster-Charon-ONE-SAFETY.mp4
- **Judge guide:** [`JUDGES_START_HERE.md`](JUDGES_START_HERE.md)
- **Public Judge Mode:** https://healthia-one-judge-1038180719788.us-central1.run.app
- **Architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **Machine-readable final proof:** [`hackathon/evidence/one_safety_final_proof.json`](hackathon/evidence/one_safety_final_proof.json)

## The 20-second product model

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

HealthIA deliberately separates **AI reasoning**, **deterministic exact logic**, and **human authority**. More model calls are not automatically more agentic.

## What the final judging package proves

### 1. ONE SAFETY — authorization is not execution evidence

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

The model cannot self-authorize a mutation or declare a connector action complete merely because it generated convincing text. A one-use `HealthActionTicket` authorizes one bounded action; the connector must execute and return a durable receipt before mission state may project completion.

The final Cloud proof correlates the same action across authorization, execution, durable outcome and Google Cloud Trace:

```text
Cloud Trace
  eec691300b7bb1c1c0564e95fb090e4f
        ↓
HealthActionTicket
  hat_021b1b6b1b4542e2
        ↓
action
  maps.search_nearby
        ↓
receipt
  receipt_95ba26286e6f4e15
        ↓
outcome
  completed
```

The promotion gate read the exact Trace ID back from **Google Cloud Trace** and required the guarded span `google.action.guarded_execute`.

### 2. Prompt injection fails before model execution or mutation

HealthIA has two prompt-ingress layers: **Google Model Armor** and a local fail-closed policy. The final adversarial proof requires all of these simultaneously:

- HTTP `400` at `prompt_ingress`;
- `model_called = false`;
- zero new `HealthActionTickets`;
- zero patient-state mutation.

### 3. Patient continuity survives the chat

Firestore is the canonical patient-scoped state. Missions, consent, evidence references, device signals, connector outcomes and longitudinal Patient Twin state survive logout/login and Cloud Run process replacement. Chat is an interface to durable work, not the source of truth.

### 4. Evidence exists before interpretation

For supported synthetic clinical PDFs/images:

1. original bytes are preserved first in private Google Cloud Storage;
2. Gemini 3.5 Flash performs bounded multimodal extraction;
3. structured results are persisted in Firestore;
4. the Patient Twin links derived state back to the original evidence;
5. unreliable extraction fails closed instead of inventing a clinical finding.

### 5. Consent is a real execution boundary

HealthIA may create a durable resource-navigation mission before location consent, but it performs no Google Places search merely because the mission exists. After mission-scoped authorization, the **same mission resumes** and the real Places connector may execute.

An exact instruction such as **“The second one”** is resolved deterministically from the ordered candidate list rather than spending another probabilistic model call.

### 6. Unattended work remains bounded

For an explicitly opted-in synthetic patient, an overdue blood-pressure follow-up can become a durable mission without a fresh chat prompt. Event-driven Google infrastructure wakes the worker, authorized external work proceeds, a real reply can return through authenticated event infrastructure, and HealthIA correlates the reply back to the same mission.

Autonomy does not remove consent, idempotency, receipts or safety boundaries.

## Google technology

| Concern | HealthIA ONE |
|---|---|
| Reasoning / multimodal | **Gemini 3.5 Flash on Vertex AI / Google GenAI** |
| Agent framework | **Google Agent Development Kit (ADK)** |
| Runtime | **Cloud Run** |
| Durable patient / mission state | **Firestore** |
| Original clinical evidence | **Private Google Cloud Storage** |
| Prompt injection boundary | **Google Model Armor + local policy** |
| Secrets / service identity | **Secret Manager + ADC / dedicated service accounts** |
| Resource discovery | **Google Places / Maps Platform** |
| External workflows | **Gmail + Pub/Sub + Google Calendar + Google Tasks** |
| Observability | **OpenTelemetry + Google Cloud Trace** |
| Device path | **Android / Health Connect bridge contracts** |

Cloud execution uses service identity / ADC rather than embedding Gemini credentials in Cloud Run.

## Exact final proof package

| Item | Value |
|---|---|
| Runtime candidate under Cloud proof | `a851947c9e1476d2fed05f74b2b40383c408387f` |
| Proof harness | `51c641d89a4c59bd57275ffa6ef98820394f9634` |
| Model Armor adversarial run | `32051146784` — **SUCCESS** |
| Enhanced ONE SAFETY run | `32054818666` — **SUCCESS** |
| Enhanced artifact ID | `9296123186` |
| Enhanced artifact ZIP SHA-256 | `253a474e7a8bd7fce373f3ff1f5697e0522f27810fe76d33dd4a902366cd9365` |
| Validated base master SHA-256 | `809d35ff7b2a3242eb61f52443c64f48a0ca45fc2e078ad1165ae76f724b1565` |
| Final 3:55 MP4 SHA-256 | `2c82929888c613960cb44ba7cb0c111b22e8a205cf38643d3199f3a1c5e542cf` |
| Charon audio SHA-256 | `3a78b5e3b98c441b138b691d803e2f3859e51e2a2795db22314d6ea4b230cc16` |
| Cloud Trace | `eec691300b7bb1c1c0564e95fb090e4f` |
| HealthActionTicket | `hat_021b1b6b1b4542e2` |
| Receipt | `receipt_95ba26286e6f4e15` |

## Reproduce from scratch — zero Google AI spend

These steps are intentionally written for a judge or reviewer starting from a clean machine.

### Prerequisites

- Git
- Python **3.12 or newer**

No Google Cloud credentials, Gemini key, patient data, or paid API access are required for the local deterministic path below.

### 1. Clone the repository

```bash
git clone https://github.com/arisnachy/healthia-one.git
cd healthia-one
```

### 2. Create and activate a virtual environment

macOS / Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install the application and test dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

### 4. Start HealthIA in deterministic local mode

macOS / Linux:

```bash
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows PowerShell:

```powershell
$env:HEALTHIA_LLM_BACKEND="mock"
$env:HEALTHIA_COST_MODE="local"
$env:HEALTHIA_AI_REQUEST_LIMIT="0"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` in a browser.

Windows users may alternatively use the repository helper:

```powershell
.\deployment\run-local-secure.ps1
```

### 5. Verify the build

From a second terminal with the virtual environment activated:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
python scripts/smoke_test.py
```

Expected result: the deterministic local path runs without Google AI spend. Controlled live/Cloud proofs are intentionally separate, explicit and request-capped; their exact passing evidence is linked above rather than requiring a judge to provision our Cloud environment.

## Bonus evidence

HealthIA also preserves three optional bonus paths without changing the frozen final runtime:

- **Public build article:** https://github.com/arisnachy/healthia-one/issues/93
- **Public X post:** https://x.com/i/status/2089481967821545835
- **Google AI bonus:** Vertex AI **Veo 3.1 Fast** (`veo-3.1-fast-generate-001`) implementation + LIVE proof lineage in PR #43.

See [`docs/HACKATHON_BONUS_POINTS.md`](docs/HACKATHON_BONUS_POINTS.md).

## Repository map

- [`JUDGES_START_HERE.md`](JUDGES_START_HERE.md) — judge-first evidence map
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — final architecture and failure semantics
- [`docs/AUTONOMOUS_CONTINUITY.md`](docs/AUTONOMOUS_CONTINUITY.md) — unattended continuity proof
- [`docs/GOOGLE_HEALTH_CONSTELLATION.md`](docs/GOOGLE_HEALTH_CONSTELLATION.md) — Google connector action loop
- [`docs/DEVPOST_SUBMISSION.md`](docs/DEVPOST_SUBMISSION.md) — final Devpost package and form values
- [`docs/HACKATHON_BONUS_POINTS.md`](docs/HACKATHON_BONUS_POINTS.md) — optional bonus evidence
- [`hackathon/evidence/`](hackathon/evidence/) — sanitized permanent proof material

## Clinical truth boundary

HealthIA ONE is a synthetic hackathon prototype and patient continuity system. It is **not** a physician, emergency service, autonomous prescription engine, regulated medical device or clinical-effectiveness study. It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

All hackathon patient/device demonstrations use synthetic data.

## Feature freeze

The judging build is under **feature freeze**. New product capabilities are not being added for score. Remaining work is restricted to reproducibility, evidence integrity and keeping judge-facing materials synchronized with the tested system.

---

**HealthIA does not win by talking longer. It wins by carrying unfinished patient work forward, doing every safe step it can prove, stopping exactly where the human must decide, and requiring real evidence before claiming the outside world changed.**
