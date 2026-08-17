# HealthIA ONE — Judges: Start Here

> **Your health never starts over.**

HealthIA ONE is a patient-owned, event-driven health continuity system. It is not a chatbot with a long prompt and it is not a collection of disconnected demos. It keeps a durable Patient Twin, turns needs and signals into missions, uses AI only where reasoning adds value, performs authorized real-world work through Google connectors, stops at human authority boundaries, and preserves evidence that the work actually happened.

## Start with HealthIA ONE

**Final ONE SAFETY judge master (3:55):**

https://github.com/arisnachy/healthia-one/releases/download/healthia-one-autonomous-winner-demo-2026/HealthIA-ONE-Autonomous-Taskmaster-Charon-ONE-SAFETY.mp4

**Official YouTube submission demo:**

https://youtu.be/dOIhP22SxZ8

The Release master is the latest evidence package. It preserves the validated Charon narration bit-for-bit and adds a short ONE SAFETY proof overlay without lengthening the 3:55 cut.

## The 20-second mental model

```text
patient need / health signal / clinical evidence
  → patient identity + patient-scoped durable context
  → prompt ingress safety: Google Model Armor + local policy
  → Gemini 3.5 Flash + Google ADK when reasoning is useful
  → deterministic policy when exactness is safer
  → explicit human authority when the decision belongs to the patient
  → durable mission
  → ONE SAFETY / Safety Kernel
  → one-use HealthActionTicket
  → real Google connector
  → durable receipt
  → OpenTelemetry / Google Cloud Trace
  → Patient Twin + longitudinal outcome
```

HealthIA deliberately separates three kinds of decisions:

1. **AI reasoning** for interpretation and planning.
2. **Deterministic logic** for exact bounded decisions and safety invariants.
3. **Human authority** for consent and clinically sensitive boundaries.

The model is never allowed to declare a real-world action complete merely because it generated convincing text.

---

## ONE SAFETY: Authorization is not execution evidence

A real action must cross a narrow, auditable chain:

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

### What each boundary means

- **Prompt ingress:** hostile instructions are screened before model execution.
- **Safety Kernel:** policy decides whether the exact proposed external action is permitted.
- **HealthActionTicket:** a one-use execution capability authorizes exactly one bounded action; it is not proof the action happened.
- **Connector:** performs the real external operation.
- **Receipt:** durable evidence returned from execution is required before completion can be projected.
- **Cloud Trace:** the action ticket stores a canonical Trace ID so the execution path can be independently correlated in Google Cloud.

### Exact live correlation proved in Google Cloud

Enhanced proof run `32054818666` executed a real Google Places action from candidate runtime `a851947c9e1476d2fed05f74b2b40383c408387f` and produced this correlated chain:

```text
Trace ID
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

The real Google Places lookup returned 8 candidates. The promotion gate then queried **Google Cloud Trace by that exact Trace ID** and required the exported trace to contain the guarded execution span `google.action.guarded_execute`.

This is the core observability claim: the same identifier connects authorization, execution evidence and the Cloud trace rather than relying on a screenshot or a model-authored narrative.

---

## Adversarial safety proof

HealthIA has two independent prompt-injection gates.

### 1. Real Google Model Armor

Cloud run `32051146784`, on the same exact candidate SHA `a851947c9e1476d2fed05f74b2b40383c408387f`, provisioned the regional Model Armor template and sent a controlled hostile prompt. The workflow only passes when:

- Model Armor invocation succeeds;
- `filterMatchState == MATCH_FOUND`;
- the `pi_and_jailbreak` filter itself reports `MATCH_FOUND`;
- the temporary template-editor privilege is removed after the proof.

### 2. Application no-mutation boundary

The enhanced proof then sent a controlled hostile request through HealthIA itself. The gate required all of the following at the same time:

- HTTP `400` at `prompt_ingress`;
- `model_called = false`;
- **zero new HealthActionTickets**;
- **zero patient-state mutation**.

A block is therefore not merely a warning banner: the unsafe instruction does not reach the model and does not create an execution capability.

---

## What to judge next

### 1. A mission survives the chat

Patient-scoped missions live in Firestore. Clinical evidence, device signals, consent decisions, connector receipts and Patient Twin state survive logout/login and process replacement. The conversation is an interface to durable work, not the source of truth.

### 2. Evidence exists before interpretation

For a synthetic clinical document or image:

1. original bytes are preserved first in private Google Cloud Storage;
2. bounded multimodal extraction uses Gemini on Google Cloud;
3. structured results are stored in Firestore;
4. the Patient Twin links derived state back to the original evidence;
5. unreliable extraction fails closed rather than inventing a finding.

### 3. Consent is a boundary, not a checkbox

In the resource-navigation mission, HealthIA can create durable work before location consent but performs no Google Places search merely because the mission exists. Consent authorizes the next bounded step; it is not retrospective proof that a connector ran.

### 4. Intelligence includes knowing when not to call AI

After Google Places returns an ordered candidate list, a bounded instruction such as **“The second one”** is resolved deterministically. HealthIA does not spend another model call reinterpreting an exact ordinal choice.

### 5. Unattended work is still bounded

For an opted-in synthetic patient, an overdue blood-pressure follow-up can become a durable mission without a fresh chat prompt. Event-driven Google infrastructure wakes the worker, authorized connector work executes, and a real reply can resume the same mission. Autonomy does not remove consent, receipts or safety boundaries.

---

## Living is an observability probe inside HealthIA — not a separate product

The `/living` surface exists to make one deterministic human-authority circuit easy to inspect: the replay advances, stops at `WAITING_HUMAN`, accepts an explicitly synthetic human-entered measurement receipt, resumes the **same mission**, and closes with zero model calls.

Judges do **not** need to understand HealthIA by starting at `/living`. It is one transparent probe of the same system described above — useful after the main product and ONE SAFETY architecture are understood.

---

## Current Google architecture

| Concern | Current HealthIA ONE implementation |
|---|---|
| Agent reasoning | Gemini 3.5 Flash on Vertex AI / Google GenAI |
| Agent framework | Google Agent Development Kit (ADK) |
| Runtime | Cloud Run |
| Durable patient state | Firestore |
| Original clinical evidence | Private Google Cloud Storage |
| Secrets / service identity | Secret Manager + ADC / dedicated service accounts |
| Prompt-injection boundary | Google Model Armor + local fail-closed policy |
| Action authorization | ONE SAFETY / deterministic Safety Kernel |
| Execution capability | One-use HealthActionTicket |
| Resource discovery | Google Places / Maps Platform |
| External workflows | Gmail + Pub/Sub + Calendar + Google Tasks |
| Device path | Android / Health Connect bridge contracts |
| Execution evidence | Durable connector receipts |
| Observability | OpenTelemetry + Google Cloud Trace |

Cloud execution uses service identity / ADC rather than embedding a Gemini API key in Cloud Run.

---

## Exact final proof package

| Item | Value |
|---|---|
| Exact runtime candidate | `a851947c9e1476d2fed05f74b2b40383c408387f` |
| Current proof harness | `51c641d89a4c59bd57275ffa6ef98820394f9634` |
| Model Armor adversarial run | `32051146784` — **SUCCESS** |
| Enhanced ONE SAFETY run | `32054818666` — **SUCCESS** |
| Enhanced artifact ID | `9296123186` |
| Enhanced artifact ZIP digest | `253a474e7a8bd7fce373f3ff1f5697e0522f27810fe76d33dd4a902366cd9365` |
| Validated base master SHA-256 | `809d35ff7b2a3242eb61f52443c64f48a0ca45fc2e078ad1165ae76f724b1565` |
| Enhanced 3:55 MP4 SHA-256 | `2c82929888c613960cb44ba7cb0c111b22e8a205cf38643d3199f3a1c5e542cf` |
| Charon audio stream SHA-256 | `3a78b5e3b98c441b138b691d803e2f3859e51e2a2795db22314d6ea4b230cc16` |
| Exact Cloud Trace | `eec691300b7bb1c1c0564e95fb090e4f` |
| HealthActionTicket | `hat_021b1b6b1b4542e2` |
| Execution receipt | `receipt_95ba26286e6f4e15` |

Machine-readable summary: `hackathon/evidence/one_safety_final_proof.json`.

---

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
```

Controlled Cloud proofs are explicit and request-capped.

---

## Where to inspect next

- `docs/ARCHITECTURE.md` — current architecture, state, credentials, failure and observability boundaries.
- `docs/AUTONOMOUS_CONTINUITY.md` — unattended durable mission and human authority boundary.
- `docs/GOOGLE_HEALTH_CONSTELLATION.md` — Google connector action loop.
- `hackathon/evidence/one_safety_final_proof.json` — compact machine-readable final proof.
- `.github/workflows/one-safety-cloud.yml` — real Google Model Armor adversarial gate.
- `.github/workflows/one-safety-enhanced-master.yml` — exact Trace→Ticket→Receipt read-back and final 3:55 master gate.
- `scripts/record_one_safety_judge_proof.py` — live proof recorder.

---

## Clinical truth boundary

HealthIA ONE is a synthetic hackathon prototype and patient continuity system. It is not a physician, emergency service, autonomous prescription engine, regulated medical device or clinical-effectiveness study. Green software and Cloud proofs establish the tested behavior described here; they do not establish medical efficacy, regulatory approval or universal security certification.

## Feature freeze

The judging build is now under **feature freeze**. New product capabilities are not being added to improve the score. Remaining work is limited to reproducibility, evidence integrity and keeping public judge materials synchronized with the tested system.

## Historical provenance anchors — retained, not the current judge entry point

The repository keeps older proof anchors because they establish ancestry and protect against rewriting history. They are **not** the current candidate and do not replace the ONE SAFETY package above.

- Historical Wave 4 candidate: `a48710eeb5a2e8429a91f5004129064e5af37c1a`.
- Preserved Golden LIVE action-loop ancestor: `891745e1ab93dc78b9aa4e54d65b315befa885f2`, an **ancestor of the Wave 4 candidate**.
- That Wave 4 proof established **0 external Places searches before location consent** and then resumed the **same mission** after consent.
- Those demonstrations, like the current judging package, use **synthetic patient data**.

These anchors remain here solely for lineage compatibility. The current judge path is HealthIA ONE + ONE SAFETY above.

## The one sentence to remember

**HealthIA carries unfinished health work forward, does every safe step it can prove, stops exactly where the human must decide, and requires real evidence before claiming the outside world changed.**
