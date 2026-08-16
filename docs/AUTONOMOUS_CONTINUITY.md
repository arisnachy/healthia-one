# HealthIA ONE — Autonomous Continuity Mainline

> **HealthIA noticed the follow-up was overdue. Nobody prompted it.**

This document describes the only Guardian capability promoted into the primary HealthIA ONE submission lineage: **explicitly opted-in blood-pressure measurement follow-up**. The broader Wave 5 Guardian research remains experimental and is not imported into the mainline.

## The unattended mission

A patient can explicitly opt into BP follow-up, Guardian email, standing auto-send, and mission-linked reply processing. When the configured follow-up interval expires, HealthIA does not wait for another chat message.

```text
patient state
  ↓
deterministic overdue-BP check           (0 model calls)
  ↓
patient-scoped durable mission            Firestore
  ↓
post-commit outbox                        no external work before state exists
  ↓
Firestore create → Eventarc
  ↓
private HealthIA Autopilot worker
  ↓
real Gmail follow-up                      standing patient consent required
  ↓
patient replies in the exact thread
  ↓
Gmail users.watch → authenticated Pub/Sub
  ↓
private Gmail worker
  ↓
canonical VitalRecord                     source_type=patient_email_reply
  ↓
same durable mission → COMPLETED
```

## Five durable boundaries

**One unattended health mission crossed 5 durable boundaries without another chat prompt.**

1. Deterministic overdue follow-up detection.
2. Patient-scoped Firestore mission committed before external work.
3. Post-commit outbox delivered through Eventarc to a private worker and a real Gmail receipt.
4. Mission-linked patient reply recovered through Gmail `users.watch` and authenticated Pub/Sub.
5. Canonical Firestore `VitalRecord` persisted and the same mission marked `COMPLETED`.

The trigger requires **0 model calls and 0 clinical-reasoning network calls**. Gemini is not used to decide whether the clock expired.

## Operational wake-up

The execution target is a private Google Cloud Run Job named `healthia-care-continuity-daily`. It runs the same bounded BP reconciliation code against Firestore and emits only aggregate counts to logs.

The repository workflow `.github/workflows/autonomous-continuity-daily.yml` is the clock: `0 12 * * *` UTC, equivalent to 08:00 in the Dominican Republic. It authenticates to Google Cloud and executes the private Cloud Run Job. This clock exists because the least-privilege CI identity can execute Cloud Run Jobs but cannot create Cloud Scheduler jobs (`cloudscheduler.jobs.create` is intentionally not self-granted).

The clock is not the agent. The autonomous work remains in Google Cloud:

- Cloud Run Job performs the deterministic due scan;
- Firestore owns patient and mission state;
- Eventarc delivers durable outbox events;
- private Cloud Run workers perform authorized connector work;
- Gmail + `users.watch` + authenticated Pub/Sub carry the external response back;
- Firestore stores the canonical measurement and mission outcome.

## Public Judge Mode

A separate Cloud Run service, `healthia-one-judge`, is intentionally public, read-only and synthetic. It contains no connector credentials and exposes no mutation routes. It gives judges an inspectable evidence surface while the operational workers remain private.

Stable URL:

`https://healthia-one-judge-1038180719788.us-central1.run.app`

Useful routes:

- `/` — judge-first evidence surface;
- `/judge-health` — exact deployed source/proof stamp;
- `/api/proof` — the five-boundary metric and proof metadata;
- `/api/synthetic-state` — synthetic-only continuity example.

POST requests to the evidence routes are rejected.

## Fail-closed rules

- `HEALTHIA_PROACTIVE_ENABLED=false` prevents creation of new autonomous BP work.
- Already-committed outbox intents are not silently discarded when the switch changes; they remain idempotent durable work.
- No BP mission exists without the patient's BP follow-up consent.
- Gmail auto-send requires nested Guardian email + standing auto-send consent.
- Reply processing requires its own nested consent.
- Precise location is not included in Guardian email.
- No model can self-authorize a mutation.
- A Gmail/Calendar/Task outcome is never claimed without a real connector receipt.
- Broad appointment, medication, post-visit, geofence and semantic-location Guardian logic remains outside this mainline.

## Clinical truth boundary

This circuit performs **measurement continuity**, not autonomous medicine. HealthIA does not autonomously diagnose hypertension, prescribe, start/stop/change medication, declare blood-pressure control, or replace professional/emergency evaluation.

All competition proof uses synthetic patient state and controlled synthetic responses.
