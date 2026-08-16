# HealthIA ONE — Final Devpost Package

## Category

**Taskmaster**

## Tagline

**Your health never starts over — a patient-owned AI agent that turns evidence into durable, consent-aware missions and real-world action.**

## Judge pitch

HealthIA ONE turns fragmented patient evidence into durable work: **Gemini + Google ADK reason when needed, deterministic logic preserves exact human choices, and real Google tools act only after the required patient boundary is satisfied.**

## The problem

A patient's health story is scattered across conversations, laboratory reports, images, medications, appointments, devices, care resources and support programs. Most health chat experiences can discuss one fragment. HealthIA ONE is designed to **carry unfinished health work forward**.

## The Taskmaster workflow

```text
patient need
→ safety + authorized patient context
→ Gemini 3.5 Flash + Google ADK reasoning
→ original evidence preserved
→ durable mission
→ safe autonomous work
→ human authorization boundary
→ same mission resumes
→ real Google action
→ exact human choice
→ durable receipt/outcome
```

### Evidence first, interpretation second

For a synthetic clinical PDF/image, original bytes are stored first in private Google Cloud Storage. Gemini 3.5 Flash on Vertex AI then performs bounded multimodal extraction, structured state is stored in Firestore and the clinical twin/timeline keeps provenance to the original. Extraction uncertainty fails closed instead of inventing a result.

### Durable missions, not prompt memory

A mission is not complete because an LLM produced text. The requested outcome must exist in durable patient-scoped state. Mission state, evidence, selections and decisions survive logout/login and Cloud Run process replacement.

### Human boundary → same mission resumes

For location-dependent resource navigation, HealthIA creates the mission but performs **0 Google Places searches before mission-scoped consent**.

After authorization, the **same durable mission resumes** and performs bounded real Google Places discovery.

Wave 4 LIVE proof verified 4 bounded searches, 9 deduplicated real candidates, 9/9 Maps URIs, 6 websites and 9 phone numbers returned by Google.

The patient can then say:

> **“The second one.”**

HealthIA deterministically selects exactly the second displayed candidate. It does not spend another LLM call guessing a bounded ordinal choice.

### Preserved real Google action loop

The Google Health Constellation Golden LIVE proof demonstrated:

```text
Safety
→ Mission Router
→ Places
→ Gmail send
→ Gmail users.watch
→ authenticated Pub/Sub
→ Gmail users.history.list / exact reply correlation
→ Calendar FreeBusy
→ Calendar event create + reread
→ Google Task create + reread
→ durable receipts
→ COMPLETED
```

External mutations are tied to exact authorization. A planned action is never represented as executed merely because a model described it; real completion requires a connector outcome/receipt.

## Opportunity Autopilot

HealthIA can maintain patient/family watch topics and discover relevant scientific/practical opportunities from sources including PubMed/NLM, Europe PMC and ClinicalTrials.gov. Assistance-program requirements are not treated as fact until verified against an official source. Eligibility remains `MATCHED`, `UNMET` or `UNKNOWN`.

HealthIA does not claim an external benefits/application submission unless a real external adapter returns a durable receipt.

## Google technology

- Gemini 3.5 Flash on Vertex AI
- Google Agent Development Kit (ADK)
- Google GenAI SDK
- Cloud Run
- Firestore
- private Google Cloud Storage
- Secret Manager
- Google Places / Maps Platform
- Gmail API
- Pub/Sub
- Google Calendar
- Google Tasks
- Firebase/FCM + Android/Health Connect bridge contracts

Cloud execution uses service identity / ADC rather than embedding a Gemini API key in Cloud Run.

## Architecture

See `JUDGES_START_HERE.md` and `docs/ARCHITECTURE.md`.

```text
Patient Web UI
→ Cloud Run / FastAPI
→ Auth + deterministic policy/safety
→ Demand-driven orchestrator
   ↳ Google ADK → Gemini 3.5 Flash
   ↳ Multimodal pipeline → private GCS → Gemini extraction
   ↳ Google mission runtime → Places/Gmail/Calendar/Tasks
→ Firestore canonical patient + mission state
→ Clinical twin / provenance
→ durable receipts + patient-visible outcome
```

## Production-minded boundaries

- patient-scoped durable state;
- cross-patient evidence isolation;
- original evidence stored before AI interpretation;
- fail-closed multimodal/reference behavior;
- mission-scoped location consent;
- exact authorization for external writes;
- deterministic bounded selection;
- bounded model-request budgets;
- secrets through Secret Manager;
- event-driven Gmail continuation through Pub/Sub rather than permanent mailbox polling;
- idempotent duplicate-event handling;
- synthetic data only in hackathon demonstrations;
- no autonomous diagnosis, prescribing or medication changes.

## Exact evidence

### Wave 4 current product candidate

- tested SHA: `a48710eeb5a2e8429a91f5004129064e5af37c1a`
- Wave 4 final lineage: PR `#41`, integrated into `main` without rewriting the tested head
- full verification / JUDGE run `31562277991` — **SUCCESS**
- real Places Wave 4 run `31562277909` — **SUCCESS**
- Opportunity Autopilot run `31562277915` — **SUCCESS**

### Preserved full external-action proof

- Golden LIVE SHA: `891745e1ab93dc78b9aa4e54d65b315befa885f2`
- evidence lineage: PR `#37`
- relationship: Golden SHA is an ancestor of the Wave 4 candidate

This proof includes real OAuth, Places, Gmail send/watch/history, authenticated Pub/Sub push, exact reply correlation, Calendar FreeBusy, Calendar event creation/reread, Google Tasks creation/reread and durable receipts.

## Reproducible setup

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

Verification:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
```

## Hosted project

A public hosted application URL is **not claimed unless anonymous/judge access is explicitly verified**. Controlled Cloud proofs are request-capped and may retain an IAM boundary to avoid unnecessary exposure.

## Video truth and replacement gate

The Devpost project currently selects its YouTube judge video. Separately, the repository preserves a **public byte-verified fallback** whose exact video SHA is locked by CI:

https://github.com/arisnachy/healthia-one/releases/download/healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm

The replacement contract is `docs/WINNING_ONE_TAKE.md`.

A replacement must show the real app continuously — not append a slide deck — with this centerpiece:

**durable mission → no Places before consent → explicit consent → real Places → “The second one” → exact deterministic selection → durable continuity**.

The full Gmail/Calendar/Tasks connector loop is shown as LIVE only when the recording account is genuinely provisioned. Nothing simulated is presented as execution evidence.

## Findings and learnings

1. **Autonomy needs boundaries, not just more tools.**
2. **Evidence should exist before interpretation.**
3. **Authorization is not execution evidence.**
4. **Bounded human choices often need deterministic logic, not another LLM call.**
5. **Durability must cross sessions/processes, not just prompts.**
6. **Event-driven agents can be cheaper and easier to audit than permanent swarms.**
7. **Fail-closed behavior is a product feature when longitudinal evidence is ambiguous.**

## Public build content

`docs/BUILDING_HEALTHIA_ONE_ALL_THINGS_AGENTIC.md` contains the public hackathon build article and the required statement that it was created for entering the All Things Agentic Hackathon 2026.

## Repository

https://github.com/arisnachy/healthia-one

## Clinical truth boundary

HealthIA ONE is a patient continuity system and hackathon prototype. It is not a physician, emergency service or autonomous prescription engine. It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

All hackathon demonstrations use synthetic patient data.
