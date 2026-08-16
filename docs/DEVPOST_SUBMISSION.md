# HealthIA ONE — Final Devpost Package

## Category

**Taskmaster**

## Tagline

**Your health never starts over — a patient-owned AI agent that turns evidence into durable, consent-aware missions and real-world action.**

## One-line judge pitch

**HealthIA ONE turns fragmented patient evidence into durable work: Gemini + Google ADK reason when needed, deterministic logic preserves exact human choices, and real Google tools act only after the required patient boundary is satisfied.**

## The problem

A patient's health story is scattered across conversations, laboratory reports, images, medications, appointments, devices, care resources and support programs. The patient is often the only person carrying unfinished context from one interaction to the next.

Most health chat experiences can discuss one fragment. HealthIA ONE is designed to **carry unfinished health work forward**.

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

### Adaptive clinical conversation

HealthIA asks for missing information instead of immediately generating a generic answer. It fails closed when an ambiguous reference cannot be anchored safely and uses deterministic safety controls before routine orientation.

### Evidence first, interpretation second

When a synthetic clinical PDF/image is uploaded:

1. original bytes are stored first in private Google Cloud Storage;
2. Gemini 3.5 Flash on Vertex AI performs bounded multimodal extraction;
3. structured patient state is stored in Firestore;
4. the clinical twin/timeline keeps provenance to the original;
5. extraction failure stays pending instead of inventing a result.

### Durable missions, not prompt memory

A mission is not complete because an LLM produced text. The requested outcome must exist in durable patient-scoped state. Mission state, evidence, selections and decisions survive logout/login and Cloud Run process replacement.

### Human boundary → same mission resumes

For location-dependent resource navigation, HealthIA creates the mission but performs **zero Google Places searches before mission-scoped consent**.

After the patient authorizes location, the same durable mission resumes and performs bounded real Google Places discovery.

The patient can then say only:

> **“The second one.”**

HealthIA deterministically selects exactly the second displayed candidate. It does not spend another LLM call guessing a bounded ordinal choice.

### Real Google action loop

The preserved Google Health Constellation LIVE proof demonstrated:

```text
Safety
→ Mission Router
→ Places
→ Gmail send
→ Gmail watch
→ Pub/Sub
→ Gmail history / exact reply correlation
→ Calendar FreeBusy
→ Calendar event
→ Google Task
→ durable receipts
→ COMPLETED
```

External mutations are tied to exact authorization. A planned action is never represented as executed merely because the model described it; real completion requires a connector outcome/receipt.

## Opportunity Autopilot

HealthIA can maintain patient/family watch topics and discover relevant scientific/practical opportunities from sources including PubMed/NLM, Europe PMC and ClinicalTrials.gov.

Assistance-program requirements are not treated as fact until verified against an official source. Eligibility remains `MATCHED`, `UNMET` or `UNKNOWN`. HealthIA does not claim an external benefits/application submission unless a real external adapter returns a durable receipt.

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

See `docs/ARCHITECTURE.md` and `JUDGES_START_HERE.md`.

Core boundaries:

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
→ Receipts + patient-visible durable outcome
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
- Wave 4 final PR: `#41` — integrated into `main` without rewriting the tested head
- full verification / JUDGE run: `31562277991` — **SUCCESS**
- real Places Wave 4 run: `31562277909` — **SUCCESS**
- Opportunity Autopilot run: `31562277915` — **SUCCESS**

Wave 4 resource proof verified 0 Places searches before consent, then 4 bounded real searches, 9 deduplicated real candidates, 9/9 Maps URIs, 6 websites and 9 phone numbers returned by Google.

### Preserved full external-action proof

- Golden LIVE SHA: `891745e1ab93dc78b9aa4e54d65b315befa885f2`
- evidence PR: `#37`
- the Golden SHA is an ancestor of the Wave 4 candidate

This proof includes real OAuth, Places, Gmail send/watch/history, authenticated Pub/Sub push, exact reply correlation, Calendar FreeBusy, Calendar event creation/reread, Google Tasks creation/reread and durable receipts.

## Reproducible setup

### Zero-spend local mode

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --port 8000
```

Windows:

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

A public hosted URL is **not claimed unless anonymous/judge access is explicitly verified**. The hackathon proof includes Google Cloud deployment evidence; controlled proof deployments are request-capped and may retain an IAM boundary to avoid unnecessary cost/exposure.

## Demo strategy

The replacement video contract is `docs/WINNING_ONE_TAKE.md`.

The final take must show the real app continuously, not append a slide deck. Its center is:

**durable mission → no Places before consent → explicit consent → real Places → “The second one” → exact deterministic selection → durable continuity**.

The full Gmail/Calendar/Tasks connector proof must only be shown as LIVE when the recording account is genuinely provisioned for it. Nothing is simulated and presented as execution evidence.

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

`https://github.com/arisnachy/healthia-one`

## Clinical truth boundary

HealthIA ONE is a patient continuity system and hackathon prototype. It is not a physician, emergency service or autonomous prescription engine. It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

All hackathon demonstrations use synthetic patient data.
