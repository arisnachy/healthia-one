# HealthIA ONE — canonical V5 judge demo (~3:17)

> **Your health never starts over.**

This file describes the **current judge-facing V5 demo**. Historical 3:55 and 2:47 masters remain preserved as proof lineage, but they are not the current submission entry point.

## Canonical judge entry

- **Official live product demo (~3:17):** https://youtu.be/44LfVn9pPdU
- **Public Judge Mode:** https://healthia-one-judge-1038180719788.us-central1.run.app
- **Judge guide:** [`JUDGES_START_HERE.md`](../JUDGES_START_HERE.md)
- **Canonical Devpost package:** [`docs/DEVPOST_SUBMISSION.md`](DEVPOST_SUBMISSION.md)
- **ONE SAFETY proof lineage:** [`hackathon/evidence/one_safety_final_proof.json`](../hackathon/evidence/one_safety_final_proof.json)
- **Submission video proof manifest:** [`hackathon/evidence/public_judge_video_proof.json`](../hackathon/evidence/public_judge_video_proof.json)

V5 is the current judge-facing film. The exact-byte 3:55 ONE SAFETY master remains useful evidence, but it must be described as historical proof lineage rather than the current Devpost demo.

## V5 story

All patient data shown in the demo is synthetic.

### Result Guardian — longitudinal evidence creates work

A clinician-confirmed losartan treatment already exists in the Patient Twin. A renal-function result containing creatinine arrives through the real Results workspace. HealthIA sees that relevant potassium evidence is still missing and opens a durable treatment-aware mission **without a new chat prompt**.

When potassium evidence later arrives, HealthIA links it to the same mission and closes the mission from durable evidence. HealthIA does not diagnose kidney disease and does not change medication.

**Judge takeaway:** the patient story itself can create and close durable work.

### Appointment Guardian — the Twin prepares the visit

A family-medicine appointment requires recent results, an active medication list and insurance. HealthIA verifies what the longitudinal record already contains, identifies the missing insurance evidence and creates an appointment-preparation mission.

When the insurance document is uploaded through the real Documents workspace, the same mission closes from persisted evidence.

**Judge takeaway:** continuity is driven by canonical state, not prompt memory.

### Post-Visit Guardian — continuity survives the encounter

When an appointment becomes completed but no attributable consultation or discharge document exists, HealthIA opens a post-visit continuity mission instead of inventing what happened.

When the consultation note arrives, the same mission closes from durable evidence.

**Judge takeaway:** missing evidence remains missing until the system can prove otherwise.

### Live Gemini 3.5 Flash + Google ADK

Inside the real HealthIA Chat, Gemini 3.5 Flash generates a bounded adaptive interview. The recording gate requires a live `gemini_dynamic` response with exactly five case-specific questions before the scene is accepted.

Google ADK coordinates the clinical capability surface while the Patient Twin remains the durable continuity layer underneath the conversation.

**Judge takeaway:** AI reasoning is used where interpretation adds value; it is not the source of truth.

### Real autonomous external follow-up

The strongest Taskmaster path continues outside chat:

```text
no new chat prompt
→ overdue blood-pressure mission
→ Eventarc wakes a private worker
→ real Gmail message
→ controlled patient reply in the same thread
→ Gmail users.watch
→ authenticated Pub/Sub
→ VitalRecord 128/80 with source_type=patient_email_reply
→ the same durable mission becomes COMPLETED
```

Completion comes from durable external evidence. A model-generated success message cannot make an outside-world mutation true.

**Judge takeaway:** HealthIA carries unfinished work forward even when the chat window is no longer driving the interaction.

## ONE SAFETY truth boundary

HealthIA separates three decision modes:

1. **AI reasoning** for interpretation, multimodal extraction and adaptive questioning.
2. **Deterministic policy** for exact state transitions, idempotency and safety invariants.
3. **Human authority** for consent and clinically sensitive decisions.

Protected external actions follow:

```text
intent
→ deterministic authorization boundary
→ ONE SAFETY
→ one-use HealthActionTicket
→ real connector
→ durable receipt
→ mission outcome
```

Authorization is not execution evidence. A connector attempt without durable outcome does not become `COMPLETED`.

## Required truth boundary

Do not claim:

- autonomous diagnosis;
- autonomous prescribing or medication changes;
- validated clinical sensor performance;
- clinical efficacy;
- regulatory approval or clearance;
- universal security certification;
- a public-host visibility state or byte identity that has not actually been independently verified.

The demo proves tested software behavior with synthetic data. It does not prove clinical effectiveness or replace professional or emergency care.

## Historical proof lineage

The 3:55 `HealthIA-ONE-Autonomous-Taskmaster-Charon-ONE-SAFETY.mp4` master remains the strongest exact-byte ONE SAFETY artifact lineage and preserves Trace → HealthActionTicket → receipt evidence.

The older approximately 290-second `HealthIA-ONE-final-judge-demo.webm` is also archived historical evidence. Neither artifact is the current V5 Devpost demo.

Any future replacement of V5 must be strictly stronger and must not lower the existing truth, consent, safety, reproducibility or publication gates.
