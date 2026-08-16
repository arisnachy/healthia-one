# HealthIA ONE

> **Your health never starts over.**

**All Things Agentic Hackathon 2026 · Taskmaster**

HealthIA ONE is a patient-owned health continuity agent that turns fragmented evidence into **durable, consent-aware missions and real-world action**. It is designed to do more than generate a good answer and disappear: unfinished work persists, evidence keeps provenance, safe actions advance autonomously, human decisions remain human, and real external execution requires a real receipt.

> **Judges:** start with [`JUDGES_START_HERE.md`](JUDGES_START_HERE.md). It separates the current Wave 4 proof from the preserved full Google action-loop LIVE proof and maps each claim to evidence.

## Why this is not a health chatbot

```text
patient need
→ deterministic safety + authorized patient context
→ Gemini 3.5 Flash + Google ADK reasoning
→ original evidence preserved before interpretation
→ durable patient-scoped mission
→ every safe step the system can prove
→ explicit human boundary when required
→ same mission resumes after consent
→ real Google tool action
→ durable receipt / patient-visible outcome
```

HealthIA deliberately combines three kinds of intelligence:

- **AI reasoning** when interpretation, multimodal understanding or planning is valuable.
- **Deterministic logic** when the answer must be exact.
- **Human consent** when the decision belongs to the patient.

That division is intentional. More model calls are not automatically more agentic.

---

## Flagship Taskmaster flow

A patient asks HealthIA to find useful support near them.

### Before location consent

HealthIA can create the durable mission and determine the next step, but it **does not call Google Places**. The authorization boundary is stored in the mission and surfaced to the patient.

### After consent

The patient authorizes location for that mission. HealthIA resumes the **same mission** and performs bounded real Google Places discovery.

The Wave 4 LIVE proof verified:

- **0** external Places searches before consent;
- **4** bounded real Places searches after consent;
- **9** deduplicated real candidates;
- **9/9** candidates with Google Maps URIs;
- website returned for **6** candidates;
- phone returned for **9** candidates;
- multiple resource families: care, community support, government/financial support and general support.

The patient can then say:

> **“The second one.”**

HealthIA deterministically selects exactly the second candidate that was shown. It does not spend another LLM round guessing a bounded ordinal choice.

---

## Evidence first, interpretation second

For a synthetic clinical PDF or image:

1. original bytes are persisted first in private Google Cloud Storage;
2. Gemini 3.5 Flash on Vertex AI performs bounded multimodal extraction;
3. structured patient-scoped result state is written to Firestore;
4. the clinical twin/timeline preserves provenance back to the original;
5. if evidence cannot be interpreted reliably, the workflow stays pending/fails closed rather than manufacturing a finding.

Longitudinal references are bounded in the same way. A phrase such as “that result” must resolve to evidence-backed recent context. If the referent cannot be proven, HealthIA asks for clarification instead of attaching new reasoning to the wrong event.

---

## Real Google action loop

The preserved Google Health Constellation LIVE proof demonstrates that the architecture can carry an authorized mission beyond discovery:

```text
Safety
→ Mission Router
→ Google Places
→ Gmail send
→ Gmail watch
→ authenticated Pub/Sub push
→ Gmail history / exact reply correlation
→ Calendar FreeBusy
→ Calendar event
→ Google Task
→ durable receipts
→ COMPLETED
```

That proof includes real Google OAuth, a real Gmail send, a real mission-linked reply recovered through Pub/Sub + Gmail history, a Calendar event created and reread, a Google Task created and reread, five durable mission receipts and idempotent duplicate-event handling.

**Authorization is not execution evidence.** Gemini cannot self-authorize a mutation and HealthIA does not claim that Gmail/Calendar/Tasks changed unless the real connector returned a durable outcome.

---

## Opportunity Autopilot

HealthIA also contains an evidence-bounded opportunity layer for scientific and practical support.

It can maintain patient/family watch topics, discover scientific opportunities from sources such as PubMed/NLM, Europe PMC and ClinicalTrials.gov, and surface assistance-program candidates.

Program requirements must be verified against an official source before eligibility can be treated as known. Eligibility remains `MATCHED`, `UNMET` or `UNKNOWN`, and missing documents are represented separately.

HealthIA can prepare assistance/application state for human review, but it does **not** claim an external government/benefits application was submitted unless a real adapter returns a durable receipt.

---

## Google architecture

| Concern | Implementation |
|---|---|
| Reasoning / multimodal | **Gemini 3.5 Flash on Vertex AI** |
| Agent framework | **Google Agent Development Kit (ADK)** + Google GenAI SDK |
| Application runtime | **Cloud Run** |
| Durable patient + mission state | **Firestore** |
| Original clinical evidence | **private Google Cloud Storage** |
| Sensitive configuration | **Secret Manager** |
| Resource discovery | **Google Places / Maps Platform** |
| External workflow | **Gmail + Pub/Sub + Calendar + Google Tasks** |
| Device path | Android / Health Connect + Firebase/FCM contracts |

Cloud execution uses service identity / ADC rather than embedding a Gemini API key in the Cloud Run runtime.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the architecture/evidence-flow diagrams and [`docs/GOOGLE_HEALTH_CONSTELLATION.md`](docs/GOOGLE_HEALTH_CONSTELLATION.md) for the Google mission loop.

---

## Durable state, not prompt memory

A HealthIA mission is not `COMPLETED` because a language model produced persuasive prose. The requested outcome must exist in durable state.

Patient-scoped state includes, where applicable:

- conversation context;
- results and original documents;
- clinical-twin provenance;
- measurements and authorized signals;
- durable missions;
- authorization boundaries;
- selected resources;
- connector receipts;
- opportunity/watch state.

The project includes continuity checks across logout/login and across real Cloud Run process/revision boundaries.

---

## Production-minded boundaries

- signed patient sessions and authenticated boundaries;
- patient-scoped Firestore state;
- private patient-scoped GCS evidence paths;
- cross-patient evidence isolation;
- original evidence stored before AI interpretation;
- fail-closed multimodal and reference handling;
- deterministic clinical safety before routine agent routing;
- mission-scoped location consent;
- exact authorization for external writes;
- bounded model-request budgets;
- Secret Manager for sensitive configuration;
- no permanent Gmail polling: external continuation is event-driven through watch/Pub/Sub/history;
- idempotent duplicate Pub/Sub delivery;
- demand/event-driven agents rather than a permanent agent swarm;
- synthetic patient data only in hackathon demonstrations.

HealthIA ONE is a patient continuity system and hackathon prototype. It is **not** a physician, emergency service or autonomous prescription engine. It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

---

## Exact hackathon evidence

### Current Wave 4 tested product candidate

- SHA: `a48710eeb5a2e8429a91f5004129064e5af37c1a`
- Wave 4 final submission PR: `#41`
- Full verification / JUDGE run: `31562277991` — **SUCCESS**
- Wave 4 real resource-navigation proof: `31562277909` — **SUCCESS**
- Opportunity Autopilot contract: `31562277915` — **SUCCESS**

`main` incorporates this exact SHA as a merge parent; the tested candidate was not rebased or rewritten during final consolidation.

### Preserved full Google external-action LIVE proof

- Golden SHA: `891745e1ab93dc78b9aa4e54d65b315befa885f2`
- evidence PR: `#37`
- relationship: the Golden SHA is an **ancestor** of the Wave 4 candidate

This distinction is deliberate: a current product claim and an earlier LIVE proof are not presented as if they were the same execution.

For the compact proof map, see [`JUDGES_START_HERE.md`](JUDGES_START_HERE.md).

---

## Local setup — zero Google AI spend by default

### Python 3.12

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

Start the app in deterministic zero-spend mode:

```bash
HEALTHIA_LLM_BACKEND=mock \
HEALTHIA_COST_MODE=local \
HEALTHIA_AI_REQUEST_LIMIT=0 \
uvicorn app.main:app --port 8000
```

Windows PowerShell:

```powershell
$env:HEALTHIA_LLM_BACKEND = "mock"
$env:HEALTHIA_COST_MODE = "local"
$env:HEALTHIA_AI_REQUEST_LIMIT = "0"
uvicorn app.main:app --port 8000
```

Or use the secured local helper:

```powershell
.\deployment\run-local-secure.ps1
```

Open:

```text
http://127.0.0.1:8000
```

---

## Verification

Run the normal local gate:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
```

Cloud/live proof workflows are intentionally separate from the zero-spend local path. Billable or external-mutation proofs use explicit gates, bounded request budgets and isolated synthetic/demo accounts.

The repository also contains browser, mission, connector, OAuth, Google Places, Firestore/GCS continuity, Android/FCM and external-event contracts.

---

## Controlled Cloud deployment

A bounded proof deployment can be created with the existing deployment tooling after Google Cloud APIs, identities and secrets are configured:

```powershell
.\deployment\deploy-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -RequestLimit 20
```

The proof environment is designed to fail closed when required Cloud configuration is missing. Do not put OAuth material, API keys, refresh tokens or patient secrets into the repository.

A public hosted URL is **not claimed merely because a Cloud Run service exists**. Anonymous/judge access must be explicitly verified before it is advertised as publicly testable.

---

## Demo contract

[`docs/WINNING_ONE_TAKE.md`](docs/WINNING_ONE_TAKE.md) is the final replacement-video contract.

The centerpiece is not a slide deck. It is the live product showing:

**mission → explicit boundary → real Google action → exact human choice → durable continuity**.

The currently published judge video remains the fallback until a replacement take passes its exact-head technical, Cloud, browser, duration, publication and byte-verification gates.

---

## Repository map

- [`JUDGES_START_HERE.md`](JUDGES_START_HERE.md) — judge-first claim/evidence map
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system architecture
- [`docs/GOOGLE_HEALTH_CONSTELLATION.md`](docs/GOOGLE_HEALTH_CONSTELLATION.md) — real Google mission/action loop
- [`docs/OPPORTUNITY_AUTOPILOT.md`](docs/OPPORTUNITY_AUTOPILOT.md) — opportunity layer
- [`docs/WINNING_ONE_TAKE.md`](docs/WINNING_ONE_TAKE.md) — final demo contract
- [`docs/DEVPOST_SUBMISSION.md`](docs/DEVPOST_SUBMISSION.md) — aligned submission package
- [`docs/BUILDING_HEALTHIA_ONE_ALL_THINGS_AGENTIC.md`](docs/BUILDING_HEALTHIA_ONE_ALL_THINGS_AGENTIC.md) — public hackathon build article
- [`hackathon/evidence/`](hackathon/evidence/) — sanitized permanent evidence
- [`scripts/record_submission_demo.py`](scripts/record_submission_demo.py) — continuous browser judge journey

---

## The idea

**HealthIA does not win by talking longer. It wins by carrying unfinished health work forward, doing every safe step it can prove, stopping exactly where the human must decide, and preserving the outcome so the patient never starts over.**
