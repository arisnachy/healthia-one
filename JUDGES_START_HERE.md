# HealthIA ONE — Judges: Start Here

> **Your health never starts over.**

HealthIA ONE is a patient-owned, event-driven health continuity system. It is not a chatbot with a long prompt and it is not a collection of disconnected demos. It keeps durable patient state, turns health signals and needs into missions, uses AI only where reasoning adds value, performs bounded real-world work through Google connectors, stops at human authority boundaries, and requires evidence before claiming an external action happened.

## Start here

1. **Official Devpost demo — 3:55:** https://youtu.be/v7SJUkzzRxw
2. **Byte-verifiable final ONE SAFETY master:** https://github.com/arisnachy/healthia-one/releases/download/healthia-one-autonomous-winner-demo-2026/HealthIA-ONE-Autonomous-Taskmaster-Charon-ONE-SAFETY.mp4
3. **Public Judge Mode:** https://healthia-one-judge-1038180719788.us-central1.run.app
4. **Architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
5. **Machine-readable proof:** [`hackathon/evidence/one_safety_final_proof.json`](hackathon/evidence/one_safety_final_proof.json)

The YouTube demo and the Release master represent the same final judging package: a **3:55** HealthIA ONE demo with the ONE SAFETY proof overlay and the validated Google Cloud Charon narration.

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

HealthIA intentionally separates three decision modes:

1. **AI reasoning** for interpretation, multimodal understanding and planning.
2. **Deterministic logic** for exact bounded choices and safety invariants.
3. **Human authority** for consent and clinically sensitive boundaries.

The model is never allowed to establish that a real-world mutation occurred merely because it generated persuasive text.

---

## 1. ONE SAFETY — authorization is not execution evidence

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

- **Prompt ingress:** hostile instructions are screened before model execution.
- **Safety Kernel:** policy evaluates the exact proposed external action.
- **HealthActionTicket:** a one-use execution capability authorizes exactly one bounded action; it is not proof the action happened.
- **Connector:** performs the real external operation.
- **Receipt:** durable execution evidence is required before completion can be projected.
- **Cloud Trace:** execution is correlated independently in Google Cloud.

### Exact live correlation

Enhanced proof run `32054818666` executed a real Google Places action from candidate runtime `a851947c9e1476d2fed05f74b2b40383c408387f` and produced:

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

The real Google Places connector returned 8 candidates. The promotion gate then queried **Google Cloud Trace by that exact Trace ID** and required the exported trace to contain `google.action.guarded_execute`.

That is the core production-readiness proof: authorization, execution evidence and Cloud observability are tied by the same concrete identifiers rather than by a screenshot or model-authored explanation.

---

## 2. Adversarial safety proof

HealthIA has two independent prompt-injection boundaries.

### Google Model Armor

Run `32051146784`, on the same runtime candidate, sent a controlled hostile prompt to the real regional Google Model Armor template in `us-central1`. The workflow only passes when:

- the sanitization invocation succeeds;
- global `filterMatchState == MATCH_FOUND`;
- the `pi_and_jailbreak` filter reports `MATCH_FOUND`;
- temporary template-editor privilege is removed after proof.

### Application no-mutation boundary

The final Cloud proof also sent a controlled hostile request through HealthIA. It required all of these simultaneously:

```text
HTTP 400 at prompt_ingress
AND model_called == false
AND new HealthActionTickets == 0
AND patient-state mutation == 0
```

A blocked instruction therefore does not merely display a warning. It cannot reach the model or obtain an execution capability.

---

## 3. Patient continuity instead of prompt memory

Firestore is the canonical patient-scoped durable state. Missions, consent, evidence references, device signals, selected resources, connector outcomes and longitudinal Patient Twin state survive logout/login and process replacement.

The Patient Twin is derived from canonical state rather than being a second independent database that can drift.

**Chat is an interface to durable work, not the source of truth.**

---

## 4. Evidence first, interpretation second

For supported synthetic clinical documents and images:

1. original bytes are preserved first in private Google Cloud Storage;
2. bounded multimodal extraction uses Gemini on Google Cloud;
3. structured results are stored in Firestore;
4. the Patient Twin links derived state back to original evidence;
5. unreliable extraction fails closed instead of inventing a clinical finding.

---

## 5. Consent is an execution boundary

In the resource-navigation mission, HealthIA can create durable work before location authorization — but it does **not** perform the Google Places search just because a mission exists.

Consent authorizes the next bounded step. After consent, the **same mission resumes** and the real Google Places connector may execute.

Once Places returns an ordered candidate list, a bounded instruction such as **“The second one”** is resolved deterministically. HealthIA does not spend another model call reinterpreting an exact ordinal choice.

---

## 6. Unattended work remains bounded

For an opted-in synthetic patient, an overdue blood-pressure follow-up can become a durable mission without a fresh chat prompt. Event-driven Google infrastructure wakes the worker, authorized connector work proceeds, a real reply can return through authenticated event infrastructure, and HealthIA correlates the reply back to the same mission.

Autonomy does not remove consent, receipts, idempotency or safety boundaries.

---

## 7. Living is an observability probe inside HealthIA

`/living` is a deterministic observability probe of one human-authority circuit. It advances a synthetic replay, stops at `WAITING_HUMAN`, accepts an explicitly synthetic human-entered measurement receipt, resumes the **same mission**, and closes with zero model calls.

It is not a separate product and judges do **not** need to start there to understand HealthIA ONE.

---

## Current Google architecture

| Concern | Current implementation |
|---|---|
| Agent reasoning | Gemini 3.5 Flash on Vertex AI / Google GenAI |
| Agent framework | Google Agent Development Kit (ADK) |
| Runtime | Cloud Run |
| Durable patient state | Firestore |
| Original clinical evidence | Private Google Cloud Storage |
| Prompt-injection boundary | Google Model Armor + local fail-closed policy |
| Action authorization | ONE SAFETY / deterministic Safety Kernel |
| Execution capability | One-use HealthActionTicket |
| Resource discovery | Google Places / Maps Platform |
| External workflows | Gmail + Pub/Sub + Calendar + Google Tasks |
| Secrets / identity | Secret Manager + ADC / dedicated service accounts |
| Execution evidence | Durable connector receipts |
| Observability | OpenTelemetry + Google Cloud Trace |
| Device path | Android / Health Connect bridge contracts |

Cloud execution uses service identity / ADC rather than embedding Gemini credentials in Cloud Run.

---

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
| Enhanced 3:55 MP4 SHA-256 | `2c82929888c613960cb44ba7cb0c111b22e8a205cf38643d3199f3a1c5e542cf` |
| Charon audio SHA-256 | `3a78b5e3b98c441b138b691d803e2f3859e51e2a2795db22314d6ea4b230cc16` |
| Cloud Trace | `eec691300b7bb1c1c0564e95fb090e4f` |
| HealthActionTicket | `hat_021b1b6b1b4542e2` |
| Execution receipt | `receipt_95ba26286e6f4e15` |

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

## Bonus evidence

Optional bonus evidence is isolated from the frozen final runtime:

- Public build article: https://github.com/arisnachy/healthia-one/issues/93
- Public X post: https://x.com/i/status/2089481967821545835
- Vertex AI Veo 3.1 Fast LIVE proof lineage: https://github.com/arisnachy/healthia-one/pull/43

See [`docs/HACKATHON_BONUS_POINTS.md`](docs/HACKATHON_BONUS_POINTS.md).

---

## Clinical truth boundary

HealthIA ONE is a synthetic hackathon prototype and patient continuity system. It is not a physician, emergency service, autonomous prescription engine, regulated medical device or clinical-effectiveness study. Green software and Cloud proofs establish tested software behavior; they do not establish medical efficacy, regulatory approval or universal security certification.

## Feature freeze

The judging build is under **feature freeze**. New product capabilities are not being added for score. Remaining work is restricted to reproducibility, evidence integrity and keeping public judge materials synchronized with the tested system.

## Historical provenance

Older Wave 4 and Golden LIVE proof anchors remain in repository history to preserve lineage. They are **not** the current judge entry point. The current judging package is HealthIA ONE + ONE SAFETY above.

---

## The one sentence to remember

**HealthIA carries unfinished patient work forward, does every safe step it can prove, stops exactly where the human must decide, and requires real evidence before claiming the outside world changed.**
