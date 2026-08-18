# HealthIA ONE — canonical 3:55 judge demo

> **Your health never starts over.**

This file describes the **current submission video only**. Historical demo recordings remain available in repository history for provenance, but they are **not** submission assets and must not be presented to judges as the final demo.

## Canonical submission assets

- **Official Devpost / YouTube demo (3:55):** https://youtu.be/v7SJUkzzRxw
- **Byte-verifiable ONE SAFETY master:** https://github.com/arisnachy/healthia-one/releases/download/healthia-one-autonomous-winner-demo-2026/HealthIA-ONE-Autonomous-Taskmaster-Charon-ONE-SAFETY.mp4
- **Release tag:** `healthia-one-autonomous-winner-demo-2026`
- **Duration:** `235.0 s` / `3:55`
- **Resolution:** `1600x900`
- **Frame rate:** `25 fps`
- **Enhanced master SHA-256:** `2c82929888c613960cb44ba7cb0c111b22e8a205cf38643d3199f3a1c5e542cf`
- **Narration:** Google Cloud Text-to-Speech, `en-US-Chirp3-HD-Charon`
- **Final proof:** [`hackathon/evidence/one_safety_final_proof.json`](../hackathon/evidence/one_safety_final_proof.json)
- **Judge entry point:** [`JUDGES_START_HERE.md`](../JUDGES_START_HERE.md)

The YouTube demo and Release master are intended to represent the same final judging package.

## Judge story — what the 3:55 proves

The video is a continuous real-application demonstration with synthetic data. It is not a slide-deck demo and does not rely on mocked external actions.

### 0:00 — A living health system

The demo opens on the real Living System with the product promise visible: **“A health system that remembers and acts.”** The evaluator surface fails closed, then an isolated synthetic patient is unlocked without exposing the capability.

Authorized signals advance the versioned Patient Twin and durable replay to `10 / 14`, where HealthIA stops at `WAITING FOR HUMAN`. A synthetic human-entered repeat measurement produces a persisted receipt, resumes the **same** chain, reaches `14 / 14`, advances the Twin to `v3`, and verifies with zero model calls in the deterministic safety loop.

**Judge takeaway:** autonomy is durable, observable, and bounded by human authority.

### ~0:55 — Exact Google Cloud candidate

The same continuous recording enters the real application. Runtime readiness proves:

- Cloud Run;
- Gemini **3.5 Flash**;
- Google **Agent Development Kit (ADK)**;
- Firestore durable state;
- private Google Cloud Storage evidence.

**Judge takeaway:** this is the exact running Google Cloud application, not a local mock or slide.

### ~1:10 — Health signal before the prompt

A synthetic Health Connect event enters before the patient asks anything. Only authorized metrics are accepted; source and time are preserved and the longitudinal record changes.

**Judge takeaway:** HealthIA can react because the patient story changed, not only because a chat prompt arrived.

### ~1:25 — Consent is an execution boundary

The patient asks for an autism support center near Santiago de los Caballeros. HealthIA creates a durable mission but performs **zero Google Places searches** before mission-scoped location consent.

After the patient authorizes location, the **same mission** resumes and performs a real bounded Google Places lookup with visible candidates, addresses and Google Maps links.

The patient says **“The second one.”** Deterministic policy selects candidate #2 without spending another model call.

**Judge takeaway:** HealthIA distinguishes AI reasoning, deterministic exactness, and human authority.

### ~2:15 — Evidence first, interpretation second

A synthetic clinical document enters the product. Original bytes are preserved first in private Cloud Storage; Gemini performs bounded multimodal extraction; Firestore links the structured result back to the source.

**Judge takeaway:** the model cannot erase provenance and unreliable evidence fails closed.

### ~2:40 — Continuity survives the session

The patient signs out and returns. Device signals, evidence, longitudinal timeline, selected resource and unfinished work remain present.

**Judge takeaway:** this is durable patient state, not prompt memory.

### ~2:55 — One patient workspace

The Patient Twin, persisted evidence, active missions, autonomous receipts and human decisions appear together in the real patient workspace. The demo then displays the exact candidate SHA, Cloud Run revision, Gemini model, ADK readiness, Firestore state and GCS evidence backend.

**Judge takeaway:** HealthIA ONE is one coherent system, not a collection of disconnected prototypes.

### ~3:15 — ONE SAFETY

The final master adds the validated ONE SAFETY proof layer: guarded real-world execution, one-use `HealthActionTicket`, durable connector receipt, prompt-injection boundary and Google Cloud Trace correlation.

The exact enhanced Cloud proof ties:

```text
Cloud Trace eec691300b7bb1c1c0564e95fb090e4f
  → HealthActionTicket hat_021b1b6b1b4542e2
  → maps.search_nearby
  → receipt receipt_95ba26286e6f4e15
  → completed
```

**Judge takeaway:** authorization is not confused with proof that the outside world changed.

### ~3:30 — The system acts without another prompt

The closing Judge Mode shows the event-driven continuity proof for an opted-in synthetic patient: HealthIA notices an overdue blood-pressure follow-up without a new chat prompt, creates durable work, uses bounded Google infrastructure and correlates the result back to the same mission.

**Final idea:**

> HealthIA ONE does not wait for another prompt. It carries health forward, so the patient never starts over.

## Required truth boundary

The video proves tested software behavior using synthetic data. Do **not** claim autonomous diagnosis, autonomous prescribing, clinical sensor validation, regulatory approval, universal clinical efficacy, or universal security certification.

## Recording / publication contract

Any future replacement is allowed only if it is strictly stronger than this master and passes the same competition gates:

1. real application only;
2. exact candidate on Google Cloud;
3. Gemini 3.5 Flash and Google ADK visibly identified;
4. real persisted records, missions and connector evidence;
5. consent and human-authority boundaries visible;
6. no secrets or credentials on screen;
7. synthetic data only;
8. browser console/page errors = zero;
9. final duration `<= 240 s`;
10. CUTLOCK and byte-level publication proof pass.

## Historical recordings

The older `HealthIA-ONE-final-judge-demo.webm` / approximately `290 s` artifact is **archived historical evidence only**. It is not the current submission video, it is not the Devpost demo, and it must not be labeled “Final submission URL.”
