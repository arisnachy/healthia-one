# HealthIA ONE judge package

## One-sentence pitch

**HealthIA ONE is a patient-owned continuity agent that notices an authorized health event, decides what work is needed, invokes only the necessary clinical-safe tools, persists evidence and keeps the mission alive until the next step is verified or safely escalated.**

## Track

Primary: **The Taskmaster**.

Why: the core demonstration is a complete multi-step workflow rather than text generation: scheduled or health-data event → autonomous decision → tool action → durable state → new evidence → verified closure.

## Problem

Patients repeatedly rebuild the same context across measurements, results, medications, family history and appointments. Standard health chatbots answer the current prompt but usually do not maintain an evidence-backed mission after the conversation ends.

## Value proposition

HealthIA ONE turns fragmented patient-owned data into continuous, consent-bound work while keeping deterministic clinical safety outside the model. It reduces the friction of remembering what changed, preparing the next consultation and following a bounded measurement task without pretending to replace a clinician.

## Technologies

- Gemini 3.6 Flash;
- Google Agent Development Kit (ADK);
- Google Gen AI SDK;
- Cloud Run;
- Pub/Sub authenticated push;
- Firestore;
- Cloud Scheduler;
- Secret Manager;
- Cloud Logging;
- FastAPI + Pydantic;
- browser JavaScript/CSS;
- Android Health Connect companion bridge.

## Four-minute unedited demo plan

**0:00–0:25 — Problem and promise**

Show HealthIA ONE home. Say that normal chat waits; HealthIA maintains patient-owned missions and can work from an event while the patient is doing something else.

**0:25–1:05 — Adaptive conversation**

Enter a short symptom complaint. Show five Gemini-generated questions, answer them, and show the second block change based on the first answers. Mention specialists run on demand rather than all at once.

**1:05–1:50 — Autonomous background action**

Show Cloud Scheduler and manually run the paused proof job. Switch to HealthIA → Ejecución autónoma. Show `Google ADK`, the scheduled event, the bounded action, Firestore persistence and verified closure of the consultation packet.

**1:50–2:45 — Closed-loop event mission**

Submit the synthetic 165/102 measurement. Show the mission become `waiting_patient` without medication advice. Submit 138/88. Show the same mission close, artifact count increase and the public trace end in `Cierre verificado`.

**2:45–3:25 — Google Cloud proof**

Show Cloud Run ready revision and `.run.app` URL, Pub/Sub authenticated subscription, Firestore, then Cloud Logging. Search the correlation ID visible in HealthIA and show the matching log line.

**3:25–3:50 — Safety, privacy and cost**

Show consent controls and the cost pill. State that deterministic safety cannot be downgraded by ADK, non-actionable background events spend zero model calls, the proof reserves at most six model calls, Cloud Run scales to zero and Scheduler is paused outside the proof.

**3:50–4:00 — Close**

“HealthIA does not just answer a patient. It carries authorized health work forward until there is evidence of the next safe step.”

## What must be visible in the final capture

- actual Gemini adaptive questions;
- actual Google ADK runtime badge from cloud evidence;
- a mission that reaches `completed`;
- at least one persisted artifact;
- Cloud Run revision and URL;
- Pub/Sub + Firestore;
- matching correlation ID in Cloud Logging;
- cost guard status;
- architecture diagram.

## Submission checklist

- [ ] Hosted project URL if kept available, or clear cloud deployment proof if scaled down.
- [ ] Public/private repository link with judge access if private.
- [ ] README spin-up instructions.
- [x] Architecture diagram in `docs/ARCHITECTURE.md`.
- [ ] ~4-minute unedited demo URL.
- [x] Problem overview.
- [x] Value proposition.
- [x] Feature list.
- [x] Technology list.
- [x] Findings/learnings draft.
- [ ] Real `dist/cloud-proof/healthia-cloud-proof.json` retained outside git or added as sanitized submission evidence.
- [ ] Final Devpost text copied and proofread.

## Findings and learnings draft

The strongest architectural lesson was that “multi-agent” should not mean “call every model.” HealthIA uses one bounded ADK decision for an actionable event and deterministic specialist tools for the rest. A deterministic safety oracle is evaluated before the model and validates the model-selected action afterward. This makes autonomy observable without letting probabilistic reasoning become the final clinical safety gate.

The second lesson was that evidence is part of the product. A mission is not complete because a model produced prose; it is complete when a tool result is persisted, correlated to source evidence and a closure condition is satisfied.

The third lesson was cost discipline. Non-actionable events avoid Gemini entirely, ADK runs reserve their worst-case two-call budget up front, Cloud Run scales to zero, the periodic scheduler stays paused except during proof, and the deployment includes a cleanup path.

## Bonus opportunities after core submission is locked

Only after all hard gates are proven:

- publish a technical build article with the required hackathon disclosure;
- publish a social post using `#AllThingsAgenticHackathon`;
- consider a clearly useful second Google model only if it materially improves the demo rather than adding complexity.
