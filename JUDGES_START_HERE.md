# HealthIA ONE — Judges: Start Here

> **Your health never starts over.**

HealthIA ONE is a **Taskmaster** agent for patient-owned health continuity. It is not a chatbot demo with a long prompt. It turns a patient goal into durable work, preserves the evidence behind that work, advances safe steps autonomously, stops at genuine human authorization boundaries, resumes the **same mission** after the patient decides, and records durable receipts for real external actions.

## The 20-second mental model

```text
patient need
  → safety + patient-scoped context
  → Gemini 3.5 Flash + Google ADK reasoning
  → original evidence preserved before interpretation
  → durable mission in Firestore
  → safe autonomous work
  → explicit human boundary when required
  → same mission resumes after consent
  → real Google tool execution
  → durable receipt / patient-visible outcome
```

HealthIA deliberately uses three forms of decision-making:

1. **AI reasoning** when interpretation or planning is valuable.
2. **Deterministic logic** when intent must be exact.
3. **Human consent** when the decision belongs to the patient.

That separation is the core product idea.

---

## What to judge first

### 1. A mission survives the chat

A mission is not `COMPLETED` because an LLM generated convincing text. Completion requires a durable, evidence-backed outcome.

Patient-scoped mission state is stored in Firestore. Original clinical evidence is preserved in private Google Cloud Storage before AI interpretation. Result/twin provenance, human decisions and selected resources survive logout/login and process replacement.

### 2. Autonomy stops before the human boundary

In the Wave 4 resource-navigation proof, HealthIA creates the mission but performs **zero Google Places searches before mission-scoped location consent**.

After consent, the same mission resumes and performs bounded real Google Places discovery. The patient can then say only:

> **“The second one.”**

HealthIA deterministically selects exactly the second candidate that was shown rather than spending another model call reinterpreting a bounded ordinal choice.

### 3. Real action requires a real receipt

The preserved Google Health Constellation LIVE proof demonstrates the extended action loop against real Google services:

```text
Safety
→ Mission Router
→ Google Places
→ Gmail send
→ Gmail watch
→ Pub/Sub
→ Gmail history / exact thread correlation
→ Calendar FreeBusy
→ Calendar event
→ Google Task
→ durable receipts
→ COMPLETED
```

The proof includes a real Gmail send, real reply recovery through Pub/Sub + Gmail history, a Calendar event created and reread, a Google Task created and reread, and idempotent handling of duplicate Pub/Sub delivery.

**Authorization is not execution evidence.** HealthIA only projects an external action as completed when the connector returns a durable outcome.

### 4. Evidence exists before interpretation

For a synthetic PDF or image:

1. original bytes are stored first in private GCS;
2. Gemini 3.5 Flash on Vertex AI performs bounded multimodal extraction;
3. structured patient state is written to Firestore;
4. the clinical twin links derived state back to the original;
5. extraction failure stays pending/fails closed rather than inventing a finding.

---

## Exact proof lineage

### Current Wave 4 product candidate

- Exact tested SHA: `a48710eeb5a2e8429a91f5004129064e5af37c1a`
- Final Wave 4 PR: `#41`
- Full verification / CI run: `31562277991` — **SUCCESS**
- Wave 4 real Google Places proof: `31562277909` — **SUCCESS**
- Opportunity Autopilot contract: `31562277915` — **SUCCESS**
- `main` incorporates the exact Wave 4 SHA as a merge parent; the tested SHA was not rewritten.

Wave 4 LIVE resource proof recorded:

- 0 external Places searches before location consent;
- 4 bounded real Places searches after consent;
- 9 deduplicated real candidates;
- 9/9 Google Maps URIs;
- 6 website URIs returned by Google;
- 9 phone numbers returned by Google;
- resource families spanning care, community support, government/financial support and general support.

### Preserved real Google action-loop ancestor

- Golden LIVE SHA: `891745e1ab93dc78b9aa4e54d65b315befa885f2`
- Evidence PR: `#37`
- This SHA is an ancestor of the Wave 4 candidate above.

The Golden proof verified real Google OAuth, Places, Gmail send/watch/history, authenticated Pub/Sub push, exact reply correlation, Calendar FreeBusy + event creation/reread, Google Tasks creation/reread and durable receipts.

The older PR is closed only to reduce repository clutter; the commit lineage and evidence remain preserved.

---

## Google architecture

| Layer | HealthIA ONE |
|---|---|
| Agent reasoning | Gemini 3.5 Flash on Vertex AI |
| Agent framework | Google Agent Development Kit (ADK) + Google GenAI SDK |
| Runtime | Cloud Run |
| Durable state | Firestore |
| Original evidence | Private Google Cloud Storage |
| Secrets | Secret Manager |
| Resource navigation | Google Places / Maps Platform |
| External workflow | Gmail + Pub/Sub + Calendar + Google Tasks |
| Device path | Android / Health Connect bridge + Firebase/FCM contracts |

Cloud execution uses service identity / ADC rather than embedding a Gemini API key in Cloud Run.

## Why the architecture is intentionally not a permanent agent swarm

HealthIA is demand/event-driven. Work begins from a patient message, evidence upload, device event, explicit follow-up or authorized external event. This reduces unnecessary model calls, makes tool execution easier to audit and keeps patient consent visible.

The code separates:

- authentication and policy;
- deterministic clinical safety;
- Gemini/ADK reasoning;
- canonical durable state;
- original evidence;
- external connector execution;
- receipts and idempotency.

---

## Opportunity Autopilot

HealthIA also contains an evidence-bounded opportunity layer for research and support resources.

It can watch patient/family topics, discover scientific opportunities from sources such as PubMed/NLM, Europe PMC and ClinicalTrials.gov, and surface assistance-program candidates. Program eligibility is not treated as known until requirements are verified against an official source; status remains `MATCHED`, `UNMET` or `UNKNOWN`.

HealthIA does **not** claim an external benefits/application submission unless a real adapter returns a durable receipt.

---

## Reproduce locally without Google AI spend

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --port 8000
```

Windows also includes:

```powershell
.\deployment\run-local-secure.ps1
```

Run the technical gate:

```bash
pytest
python scripts/full_system_check.py
python scripts/dialogbench.py
python scripts/judge_omega.py
```

Controlled Cloud proofs are explicit opt-in and request-capped.

---

## Where to inspect next

- `README.md` — project overview and reproducible setup.
- `docs/ARCHITECTURE.md` — architecture and evidence-flow diagrams.
- `docs/GOOGLE_HEALTH_CONSTELLATION.md` — real Google action-loop architecture/evidence.
- `docs/OPPORTUNITY_AUTOPILOT.md` — evidence-bounded opportunity system.
- `docs/WINNING_ONE_TAKE.md` — the judge-demo north star.
- `hackathon/evidence/` — sanitized permanent machine-readable evidence.
- `scripts/record_submission_demo.py` — continuous real-browser judge journey.

---

## Clinical truth boundary

HealthIA ONE is a patient continuity system and hackathon prototype. It is not a physician, emergency service or autonomous prescription engine. It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

Hackathon demonstrations use synthetic patient data.

---

## The one sentence to remember

**HealthIA does not win by talking longer: it wins by carrying unfinished health work forward, doing every safe step it can prove, stopping exactly where the human must decide, and preserving the outcome so the patient never starts over.**
