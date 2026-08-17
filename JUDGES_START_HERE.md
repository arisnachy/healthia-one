# HealthIA ONE — Judges: Start Here

> **Your health never starts over.**

HealthIA ONE is a **Taskmaster** system for patient-owned health continuity. It is not a chatbot with medical memory. It turns changing health context into durable, consent-aware missions; preserves original evidence; completes safe work through real connectors; stops at genuine human authority boundaries; and carries the same patient story across sessions.

## Start with HealthIA ONE

**Latest enhanced judge master (3:55, synthetic data only):**  
https://github.com/arisnachy/healthia-one/releases/download/healthia-one-autonomous-winner-demo-2026/HealthIA-ONE-Autonomous-Taskmaster-Charon-ONE-SAFETY.mp4

**Embedded Devpost/YouTube demo:** the project page contains the current public YouTube submission. The GitHub Release master above is the byte-verifiable exact-candidate evidence artifact and includes the ONE SAFETY proof overlay.

**Public read-only synthetic Judge Mode:**  
https://healthia-one-judge-1038180719788.us-central1.run.app

The core mental model is:

```text
Sense
  → Understand
  → Decide
  → Authorize
  → ONE SAFETY
  → one-time HealthActionTicket
  → real connector
  → durable receipt
  → Patient Twin continues
```

HealthIA deliberately separates four things that an LLM must never be allowed to collapse:

```text
authorization != execution ticket != connector execution != completion evidence
```

The model may reason. The patient owns sensitive authority. ONE SAFETY grants one exact execution attempt. A real connector performs the action. Only durable evidence can close the loop.

---

## What to judge first

### 1. The patient story is durable, not prompt-local

Patient-owned state is persisted in Firestore. Original clinical evidence is stored in private Google Cloud Storage **before** AI interpretation. Device signals, clinical results, missions, consent, selected resources, external-action receipts and the longitudinal Patient Twin survive logout/login and process replacement.

A convincing model response cannot mark a mission complete by itself.

### 2. Autonomy has a non-bypassable execution boundary

A mutating or consent-scoped Google action does not jump from Gemini to a connector.

```text
patient/event intent
  → deterministic policy
  → patient authorization when required
  → ONE SAFETY kernel
  → short-lived exact-intent HealthActionTicket
  → connector
  → durable receipt
```

`HealthActionTicket` is bound to patient, mission, action, exact material payload, authorization, idempotency key and expiry. It can be consumed only once. The ticket authorizes an **attempt**; it is not proof that the outside world changed.

### 3. Trace → Ticket → Receipt is visible and correlated

The enhanced proof creates a real patient-scoped Google navigation mission, authorizes location, performs a bounded real Google Places discovery, and persists the active OpenTelemetry Trace ID into the one-time HealthActionTicket. The same execution records the connector receipt ID.

The protected ONE SAFETY console renders:

```text
Cloud Trace ID → HealthActionTicket → durable receipt → connector outcome
```

The proof harness then reads the **same trace ID back from Google Cloud Trace** and requires a `google.action.guarded_execute` span before promotion.

No prompt text, clinical content or PHI is exported as trace attributes.

### 4. Prompt injection fails before model or execution authority

HealthIA uses two ingress layers:

1. deterministic local policy;
2. Google Model Armor in Cloud.

The real Model Armor adversarial gate sends a synthetic instruction asking the system to ignore prior instructions, reveal hidden rules, bypass authorization and execute tools without consent. Promotion requires Google Model Armor to return `MATCH_FOUND` on its prompt-injection/jailbreak filter.

A separate application proof submits a controlled hostile chat request and requires all of the following:

- HTTP `400` at `prompt_ingress`;
- `model_called=false`;
- **zero new HealthActionTickets**;
- **zero patient-state mutation**;
- **zero connector execution**.

### 5. Human boundaries remain human

In resource navigation, HealthIA can create durable work before it has permission to use location. It does not perform Google Places discovery until mission-scoped location consent exists. After consent the **same mission** resumes.

For bounded intent, HealthIA deliberately avoids unnecessary model calls. A patient can say:

> **“The second one.”**

and deterministic policy selects exactly the second candidate already shown.

### 6. Evidence exists before interpretation

For a synthetic clinical PDF or image:

1. original bytes are preserved in private GCS;
2. Gemini 3.5 Flash on Vertex AI performs bounded multimodal extraction;
3. structured state is persisted in Firestore;
4. the Patient Twin links derived observations back to the original source;
5. unreadable/failed extraction stays pending or fails closed rather than inventing a finding.

---

## ONE SAFETY: current exact proof lineage

### Exact product candidate used for the final live proof

- Candidate SHA: `a851947c9e1476d2fed05f74b2b40383c408387f`
- Final live exact-candidate workflow: `32051146792`
- Continuous real-browser demo: **PASS**
- Charon master: **PASS**
- CUTLOCK: **PASS**
- Base master duration: **235.000 s**
- Base master SHA-256: `809d35ff7b2a3242eb61f52443c64f48a0ca45fc2e078ad1165ae76f724b1565`
- Narration voice: Google Cloud TTS `en-US-Chirp3-HD-Charon`, male, no fallback

The enhanced master overlays ONE SAFETY visually during the existing authorization/receipt narration. It does **not** add or accelerate speech. The pipeline requires the AAC Charon stream hash to remain byte-identical to the validated base master and requires the total duration to remain 3:55.

### Real Google Model Armor adversarial gate

- Workflow: `32051146784`
- Regional template: `healthia-one-safety` in `us-central1`
- Prompt-injection/jailbreak adversarial probe: **PASS / MATCH_FOUND**
- Temporary provisioning privilege removed after the proof

### Enhanced Trace → Ticket → Receipt proof

- Workflow: `32053089428`
- Proof harness: current `main`
- Runtime under test: exact candidate `a851947c9e1476d2fed05f74b2b40383c408387f`
- Real Google Places action: required
- Canonical 32-hex Trace ID on `HealthActionTicket`: required
- Durable connector receipt correlation: required
- Exact Google Cloud Trace read-back: required
- Controlled prompt-injection no-model/no-ticket/no-mutation proof: required
- Charon audio byte-identity gate: required
- Enhanced 3:55 Release publication: required

The proof harness and product candidate are intentionally separated: current judge tooling may improve without silently changing the exact product runtime being demonstrated.

---

## Broader autonomous action proof

HealthIA also preserves an unattended blood-pressure continuation proof:

> **HealthIA noticed the follow-up was overdue. Nobody prompted it.**

For an opted-in synthetic patient, a deterministic clock creates durable work. Eventarc wakes a private Cloud Run worker. Gmail sends under standing consent. Gmail `users.watch` and authenticated Pub/Sub recover the reply. Gmail history correlates the exact thread. HealthIA stores a canonical VitalRecord and completes the same mission only after durable evidence exists.

The preserved broader Google action loop includes:

```text
Safety
→ Mission Router
→ Google Places
→ Gmail send
→ Gmail watch
→ Pub/Sub
→ Gmail history / exact thread correlation
→ Calendar FreeBusy
→ Calendar event create + reread
→ Google Task create + reread
→ durable receipts
→ COMPLETED
```

Authorization is never treated as proof of execution.

---

## Google architecture

| Layer | HealthIA ONE |
|---|---|
| Reasoning | Gemini 3.5 Flash on Vertex AI |
| Agent framework | Google Agent Development Kit (ADK) + Google GenAI SDK |
| Runtime | Cloud Run |
| Durable patient state | Firestore |
| Original clinical evidence | Private Google Cloud Storage |
| Secrets | Secret Manager |
| AI ingress defense | Google Model Armor + deterministic local policy |
| Execution authority | ONE SAFETY + one-time HealthActionTicket |
| Observability | OpenTelemetry + Google Cloud Trace |
| Resource navigation | Google Places / Maps Platform |
| External workflow | Gmail + Pub/Sub + Calendar + Google Tasks |
| Device path | Android / Health Connect + Firebase/FCM contracts |
| Specialist reasoning | KIRA Health Google ADK fleet, demand-driven |

Cloud execution uses service identity / ADC. HealthIA does not embed a Gemini API key in Cloud Run.

HealthIA is intentionally event/demand-driven rather than a permanently active model swarm. More model calls are not automatically more agentic.

---

## Living System is a proof surface, not a separate product

`/living` is an isolated synthetic evaluator circuit **inside the HealthIA evidence strategy**. It is not another app and it is no longer the recommended starting point.

Open only if you want to inspect a bounded deterministic replay:

https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app/living

With the privately supplied evaluation capability, the synthetic replay advances to event `10/14`, stops at `WAITING_HUMAN`, accepts one explicitly synthetic human measurement receipt, resumes the **same mission**, advances the Twin to v3 and closes at `14/14` with zero model calls in that deterministic safety circuit.

That circuit demonstrates an observable human authority boundary; the broader HealthIA product proves Gemini/ADK, multimodal evidence, real Google connectors and durable continuity.

---

## Reproduce locally without Google AI spend

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --port 8000
```

Run the deterministic technical gates:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
```

Cloud proof workflows are isolated, synthetic, request-bounded and fail closed.

---

## Feature freeze

HealthIA is now in **evidence-first hackathon feature freeze**. Until judging, accepted changes are limited to verified bugs, security, reliability, tests, exact proof and judge-facing clarity. New agents, new connector families, new clinical autonomy and architectural rewrites wait unless a verified judging gap requires them.

See: `docs/HACKATHON_FEATURE_FREEZE.md`.

---

## Where to inspect next

- `docs/ARCHITECTURE.md` — current architecture and ONE SAFETY trust boundaries.
- `docs/AUTONOMOUS_CONTINUITY.md` — unattended continuation proof.
- `docs/GOOGLE_HEALTH_CONSTELLATION.md` — real Google action-loop design.
- `docs/HACKATHON_FEATURE_FREEZE.md` — competition freeze contract.
- `healthia_one/safety_kernel.py` — one-time execution ticket.
- `healthia_one/model_armor.py` — local + Google Model Armor ingress gate.
- `healthia_one/observability.py` — sanitized OpenTelemetry / Cloud Trace.
- `web/operations/security.html` — judge-visible Trace → Ticket → Receipt surface.

---

## Clinical truth boundary

HealthIA ONE is a patient continuity system and hackathon prototype. It is not a physician, emergency service, regulated medical device or autonomous prescription engine. It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

Hackathon demonstrations use synthetic patient data.

---

## The one sentence to remember

**HealthIA carries health forward: signals become evidence, evidence becomes safe missions, authorized missions become verifiable action, and the patient never starts over.**
