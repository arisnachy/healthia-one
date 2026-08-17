# HealthIA ONE — Final Devpost Package

## Category

**Taskmaster**

## Tagline

**Your health never starts over — a patient-owned AI agent that turns evidence into durable, consent-aware missions and real-world action.**

## Judge pitch

HealthIA ONE turns fragmented patient evidence into durable work: **Gemini + Google ADK reason when needed, deterministic logic preserves exact human choices, and real Google tools act only after the required patient boundary is satisfied.**

## The winning proof

> **HealthIA noticed the follow-up was overdue. Nobody prompted it.**

For an explicitly opted-in synthetic patient, deterministic reconciliation created one durable blood-pressure follow-up mission before external work. Eventarc woke a private Cloud Run worker. Real Gmail delivered the follow-up under standing consent. The patient's exact-thread reply returned through Gmail `users.watch` and authenticated Pub/Sub. HealthIA stored a canonical measurement and completed the same mission.

That one unattended mission crossed **5 durable boundaries**. Detecting that it was due required **0 model calls**.

The new judge centerpiece makes that operating model directly visible. In the
isolated synthetic `/living` experience, four authorized signals advance a
versioned Patient Twin, create a durable mission and stop at event 10/14 for
human authority. Only a persisted synthetic human receipt may resume the same
mission, advance the Twin to v3 and close event 14/14. This evaluator circuit is
deterministic and spends zero model calls; Gemini and ADK remain available in
the authenticated clinical product where reasoning adds value.

- Public exact-head Judge Mode: https://healthia-one-judge-1038180719788.us-central1.run.app
- Living System: https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app/living
- Final continuous demo, narrated with Google Cloud male voice `en-US-Chirp3-HD-Charon`: https://github.com/arisnachy/healthia-one/releases/download/healthia-one-autonomous-winner-demo-2026/HealthIA-ONE-Autonomous-Taskmaster-Charon.mp4
- Operational workers remain private; Judge Mode is synthetic, GET-only and credential-free.

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

Judge-facing Living System:

https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app/living

The page is anonymously reachable, but the interactive evaluator requires a
private capability supplied to judges. That capability unlocks only the
physically separate synthetic `patient_eval_living` namespace. Anonymous
patient APIs remain rejected, cross-patient access is denied and operational
workers stay private.

The exact candidate SHA, Cloud Run revision, image digest, functional proof and
video hash come from final machine-generated release evidence rather than
hand-copied values in this document.

## Final autonomous winner video

https://github.com/arisnachy/healthia-one/releases/download/healthia-one-autonomous-winner-demo-2026/HealthIA-ONE-Autonomous-Taskmaster-Charon.mp4

The video is one continuous real-browser take against an exact candidate deployed on Cloud Run. It visibly demonstrates the application, Gemini 3.5 Flash, Google ADK, Firestore/GCS durability, mission-scoped consent before real Places, deterministic selection, logout/login continuity, the unattended five-boundary continuity proof, and exact-head Google Cloud evidence. The narration is generated by Google Cloud Text-to-Speech with the explicitly named male voice `en-US-Chirp3-HD-Charon`; the workflow fails closed if that voice is unavailable.

## Prior video truth and Living System replacement gate

The Devpost project may continue showing the earlier YouTube video until the
Living System replacement passes CUTLOCK. Separately, the repository preserves
a **public byte-verified fallback** whose exact video SHA is locked by CI:

https://github.com/arisnachy/healthia-one/releases/download/healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm

The replacement contract is `docs/WINNING_ONE_TAKE.md`.

A valid Living System replacement must show the real app continuously — not
append a slide deck — and include both centerpieces:

**durable mission → no Places before consent → explicit consent → real Places → “The second one” → exact deterministic selection → durable continuity**.

**authorized signals → Twin update → durable mission → event 10/14 human stop → persisted synthetic receipt → Twin v3 → event 14/14 verified closure**.

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
