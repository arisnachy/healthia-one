# HealthIA ONE

> **Your health never starts over.**

**All Things Agentic Hackathon 2026 · Taskmaster**

HealthIA ONE is a patient-owned health continuity agent that turns fragmented evidence into **durable, consent-aware missions and real-world action**. It is designed to do more than generate a good answer and disappear: unfinished work persists, evidence keeps provenance, safe actions advance autonomously, human decisions remain human, and external execution requires a real connector receipt.

> **Judges:** start with [`JUDGES_START_HERE.md`](JUDGES_START_HERE.md). It separates the current Wave 4 proof from the preserved full Google action-loop LIVE proof and maps each claim to evidence.

## The 20-second product model

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

HealthIA deliberately combines **AI reasoning**, **deterministic exact logic**, and **human consent**. More model calls are not automatically more agentic.

## Current winning proof: nobody prompted it

> **HealthIA noticed the follow-up was overdue. Nobody prompted it.**

For an explicitly opted-in synthetic patient, deterministic reconciliation created one durable blood-pressure follow-up mission before any external action. The mission crossed **5 durable boundaries**: Firestore commit, Eventarc delivery, private Cloud Run worker, real Gmail plus authenticated Pub/Sub reply recovery, and canonical measurement persistence on the same completed mission. Detecting that the follow-up was due required **0 model calls**.

- Public exact-head Judge Mode: https://healthia-one-judge-1038180719788.us-central1.run.app
- Architecture and safety contract: [`docs/AUTONOMOUS_CONTINUITY.md`](docs/AUTONOMOUS_CONTINUITY.md)
- Final continuous demo with Google Cloud male voice `en-US-Chirp3-HD-Charon`: https://github.com/arisnachy/healthia-one/releases/download/healthia-one-autonomous-winner-demo-2026/HealthIA-ONE-Autonomous-Taskmaster-Charon.mp4

The public Judge Mode is read-only, synthetic and credential-free; the operational workers remain private.

## Flagship Taskmaster proof

A patient asks HealthIA to find useful support nearby.

**Before mission-scoped location consent:** HealthIA may create the mission and determine the next step, but it performs **0 Google Places searches**.

**After consent:** the **same durable mission resumes** and performs bounded real Google Places discovery.

Wave 4 LIVE proof verified:

- 4 bounded real Places searches after consent;
- 9 deduplicated real candidates;
- 9/9 candidates with Google Maps URIs;
- website returned for 6 candidates;
- phone returned for 9 candidates;
- multiple resource families spanning care, community support, government/financial support and general support.

The patient can then say:

> **“The second one.”**

HealthIA deterministically selects exactly the second candidate shown instead of spending another LLM round guessing a bounded ordinal choice.

## Evidence first, interpretation second

For a synthetic clinical PDF/image:

1. original bytes are persisted first in private Google Cloud Storage;
2. Gemini 3.5 Flash on Vertex AI performs bounded multimodal extraction;
3. structured patient state is written to Firestore;
4. the clinical twin/timeline preserves provenance back to the original;
5. ambiguous or unreadable evidence fails closed rather than producing an invented finding.

Longitudinal references follow the same rule: if “that result” cannot be anchored to durable evidence, HealthIA asks instead of guessing.

## Preserved real Google action loop

The Golden Google Health Constellation LIVE proof demonstrates:

```text
Safety
→ Mission Router
→ Google Places
→ Gmail send
→ Gmail users.watch
→ authenticated Pub/Sub push
→ Gmail users.history.list / exact thread correlation
→ Calendar FreeBusy
→ Calendar event create + reread
→ Google Task create + reread
→ durable receipts
→ COMPLETED
```

**Authorization is not execution evidence.** Gemini cannot self-authorize a mutation and HealthIA does not claim Gmail/Calendar/Tasks changed unless the real connector returned a durable outcome.

## Google architecture

| Concern | Implementation |
|---|---|
| Reasoning / multimodal | **Gemini 3.5 Flash on Vertex AI** |
| Agent framework | **Google Agent Development Kit (ADK)** + Google GenAI SDK |
| Runtime | **Cloud Run** |
| Durable patient + mission state | **Firestore** |
| Original clinical evidence | **private Google Cloud Storage** |
| Sensitive configuration | **Secret Manager** |
| Resource discovery | **Google Places / Maps Platform** |
| External workflow | **Gmail + Pub/Sub + Calendar + Google Tasks** |
| Device path | Android / Health Connect + Firebase/FCM contracts |

Cloud execution uses service identity / ADC rather than embedding a Gemini API key in Cloud Run.

## The broader Patient OS is still here

The final judge story is intentionally narrow, but the underlying patient system retains the release-proven capabilities that make continuity useful beyond one demo:

- **pathological family genogram with provenance**;
- **multimodal result ingestion with original evidence retention**;
- **treatment and medication check-ins without autonomous prescribing**;
- **patient-controlled consent, snooze, audit and JSON export**;
- longitudinal results, documents, measurements, family context, device paths and patient controls;
- the earlier **Closed-loop Taskmaster result mission**, preserved as a tested capability rather than used as the Wave 4 flagship.

The smoke path remains `scripts/smoke_test.py`. Local deterministic mode can run with **zero Google AI calls**.

## Exact evidence

### Current Wave 4 tested product candidate

- SHA: `a48710eeb5a2e8429a91f5004129064e5af37c1a`
- Wave 4 final lineage: PR `#41`
- Full verification / JUDGE: run `31562277991` — **SUCCESS**
- Real resource-navigation proof: run `31562277909` — **SUCCESS**
- Opportunity Autopilot: run `31562277915` — **SUCCESS**

`main` incorporates this exact SHA as a merge parent; the tested candidate was not rewritten.

### Preserved full Google external-action LIVE proof

- Golden SHA: `891745e1ab93dc78b9aa4e54d65b315befa885f2`
- evidence lineage: PR `#37`
- relationship: Golden SHA is an **ancestor** of the Wave 4 candidate

This distinction is deliberate: a current product claim and an earlier LIVE proof are not presented as the same execution.

## Judge video truth

The Devpost submission currently selects the YouTube judge video maintained on the project page. Separately, the repository preserves a **byte-verified public fallback** whose exact SHA-256 is locked by CI:

https://github.com/arisnachy/healthia-one/releases/download/healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm

That fallback remains valid until a replacement Wave 4 one-take passes its own exact-head Cloud/browser/publication gates. See [`docs/WINNING_ONE_TAKE.md`](docs/WINNING_ONE_TAKE.md).

## Opportunity Autopilot

HealthIA can maintain patient/family watch topics and discover scientific/practical opportunities from sources such as PubMed/NLM, Europe PMC and ClinicalTrials.gov. Program requirements must be verified against an official source before eligibility can be treated as known; status remains `MATCHED`, `UNMET` or `UNKNOWN`.

HealthIA does **not** claim an external benefits/application submission unless a real external adapter returns a durable receipt.

## Production-minded boundaries

- patient-scoped Firestore state and private GCS evidence paths;
- cross-patient evidence isolation;
- original evidence stored before AI interpretation;
- fail-closed multimodal/reference behavior;
- deterministic clinical safety before routine agent routing;
- mission-scoped location consent;
- exact authorization for external writes;
- bounded model-request budgets;
- secrets through Secret Manager;
- event-driven Gmail continuation through Pub/Sub rather than permanent mailbox polling;
- idempotent duplicate-event handling;
- demand/event-driven agents rather than a permanent model swarm;
- synthetic patient data only in hackathon demonstrations.

## Zero-spend local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --port 8000
```

Windows helper:

```powershell
.\deployment\run-local-secure.ps1
```

Full verification:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
python scripts/smoke_test.py
```

Frontend static checks:

```bash
node --check web/app.js
node --check web/patient-record.js
node --check web/family-documents.js
node --check web/continuity.js
node --check web/privacy-controls.js
node --check web/profile-devices.js
node --check web/icons.js
```

Cloud/live proofs are separate opt-in gates with bounded request budgets. A public hosted application URL is **not claimed merely because a Cloud Run service exists**; anonymous/judge access must be explicitly verified first.

## Repository map

- [`JUDGES_START_HERE.md`](JUDGES_START_HERE.md) — judge-first claim/evidence map
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture
- [`docs/AUTONOMOUS_CONTINUITY.md`](docs/AUTONOMOUS_CONTINUITY.md) — unattended five-boundary mission and public Judge Mode
- [`docs/GOOGLE_HEALTH_CONSTELLATION.md`](docs/GOOGLE_HEALTH_CONSTELLATION.md) — current Google mission/action truth table
- [`docs/OPPORTUNITY_AUTOPILOT.md`](docs/OPPORTUNITY_AUTOPILOT.md) — evidence-bounded opportunity layer
- [`docs/WINNING_ONE_TAKE.md`](docs/WINNING_ONE_TAKE.md) — replacement-video contract
- [`docs/DEVPOST_SUBMISSION.md`](docs/DEVPOST_SUBMISSION.md) — aligned submission package
- [`docs/BUILDING_HEALTHIA_ONE_ALL_THINGS_AGENTIC.md`](docs/BUILDING_HEALTHIA_ONE_ALL_THINGS_AGENTIC.md) — public build article
- [`hackathon/evidence/`](hackathon/evidence/) — sanitized permanent evidence

## Clinical truth boundary

HealthIA ONE is a patient continuity system and hackathon prototype. It is not a physician, emergency service or autonomous prescription engine. It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

All hackathon demonstrations use synthetic patient data.

---

**HealthIA does not win by talking longer. It wins by carrying unfinished health work forward, doing every safe step it can prove, stopping exactly where the human must decide, and preserving the outcome so the patient never starts over.**
