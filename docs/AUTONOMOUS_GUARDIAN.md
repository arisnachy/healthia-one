# HealthIA ONE — Autonomous Guardian

Status: Wave 5 working branch. This document is intentionally truth-boundary first: it separates implemented context interpretation from the still-pending autonomous cloud execution and notification layers.

## Goal

HealthIA should stay aware of the patient between chats, using only signals and context the patient explicitly authorizes. The system should interpret a physiological change against activity, semantic place context, time, longitudinal baseline and related signals before deciding whether to observe, investigate, notify, or stop for a human.

The core principle is:

> HealthIA is autonomous until autonomy would become authority.

It may observe, organize, compare, investigate, prepare, remind and notify within permission. It must not silently change treatment, diagnose causation from correlation, bypass a deterministic safety gate, infer precise location without permission, or treat a consumer sensor as clinically certified.

## Implemented in this branch

### Context-aware device assessment

`healthia_one.guardian_context` adds a deterministic/contextual layer for Health Connect heart-rate and blood-pressure observations.

The assessment keeps separate fields for:

- **observed** — what the device record actually contained;
- **context** — activity/exercise/semantic place/time and optional contextual metadata;
- **inference** — what the available context supports;
- **hypothesis** — possible explanations that are explicitly not treated as established causes.

Current classifications include:

- `likely_exertion_related`
- `unexpected_for_rest_context`
- `recurring_context_pattern`
- `blood_pressure_context_review`
- `context_insufficient`

### Personal longitudinal baseline

For heart rate, Guardian can derive a recent resting baseline from prior authorized Health Connect records. A new signal can then be interpreted against the patient's own recent pattern instead of a single global number.

### Repeated context pattern detection

Guardian can detect a repeated association when elevated heart-rate observations recur in the same semantic location and similar time window while the recorded activity context is resting/still.

Example:

- similar time window around 10:00;
- semantic context `work`;
- activity `still`;
- repeated heart-rate deviation above the patient's recent resting baseline.

The output states that the pattern is associated with that context. It does **not** state that work or stress caused the change.

### Semantic location privacy boundary

Guardian accepts only coarse semantic place context in its assessment output:

- `home`
- `work`
- `gym`
- `outdoor`
- `commuting`
- `unknown`

If raw latitude/longitude values appear in incoming metadata, Guardian ignores them and does not copy them into its assessment. Precise location capture, storage and geofencing require a separate explicit patient permission and mobile-side implementation.

### Safety remains authoritative

`healthia_one.devices.ingest_health_connect_batch` still runs the deterministic vital safety layer first. Guardian assessments are added afterwards and every Guardian assessment has `can_suppress_safety = false`.

A gym/exercise context therefore cannot cancel a priority blood-pressure threshold. Context may explain variability and may suggest a resting confirmation, but it never overrides the safety decision.

## Context inputs planned for the mobile bridge

The current Python Guardian contract can consume semantic metadata when supplied by an authorized bridge. The next Android phase should provide only consented context such as:

- `activity_type`: running / walking / cycling / still / sleeping / unknown;
- `exercise_session_active`: boolean;
- `location_context`: home / work / gym / outdoor / commuting / unknown;
- `hrv_rmssd_ms` when the source and permission exist;
- `sleep_minutes` or sleep-session context when available;
- optional patient-provided stress/context signals;
- medication timing and longitudinal Clinical Twin context from HealthIA itself.

The mobile implementation should prefer on-device conversion from location to semantic context instead of continuously transmitting raw GPS coordinates.

## Target autonomous flow — not yet claimed as deployed proof

The intended end-to-end flow is:

```text
Authorized wearable / Health Connect signal
        -> deterministic Safety Gate
        -> Guardian Context Engine
        -> durable patient-scoped event
        -> Firestore outbox
        -> Eventarc
        -> private Cloud Run autonomous worker
        -> investigate / compare / update durable mission
        -> Notification Planner
             -> in-app
             -> FCM push
             -> patient email (when authorized)
        -> stop at human/clinical/consent boundary
```

The repository already contains the Opportunity Autopilot outbox, leased claims, receipts, private Cloud Run/Eventarc worker contracts and Scheduler contracts. The remaining Wave 5 work is to connect selected Guardian events to that durable runtime and prove them on the exact candidate in Google Cloud.

## Patient email target

Patient email is part of the Wave 5 target but is not yet claimed as a live outbound feature from Guardian.

The desired policy is:

- auto-send only for patient-authorized reminders/updates that do not change clinical authority;
- draft or wait for review when content could be interpreted as a treatment recommendation;
- never rely on email alone for an urgent clinical safety event;
- persist a notification receipt with event, mission, consent scope, message hash, provider message ID and delivery state;
- deduplicate redelivery so one autonomous event cannot send the same email twice.

## Demo target

The winning demo moment should show a patient leaving HealthIA and not sending another prompt. A new authorized health signal or clinical event should wake the agent, produce useful work, persist the result, and—when policy allows—bring the patient back into the mission through a notification.

The judge-facing claim should be evidence-bound:

> Nobody prompted HealthIA. The patient-authorized event woke the agent. HealthIA continued the mission on its own and stopped exactly where the decision belonged to a human.

## Promotion gate

Do not merge this Wave 5 branch into the preserved hackathon candidate until all of the following are green:

1. Guardian unit/regression tests.
2. Full repository CI and browser/LAB/JUDGE gates.
3. Durable Guardian event wiring with duplicate suppression and crash recovery.
4. Private Cloud Run/Eventarc live proof.
5. Patient permission controls for context and notification channels.
6. Outbound notification receipt and duplicate-send prevention.
7. A real judge demo that shows autonomous work while the patient is away.
8. Truth-boundary review: no claim of diagnosis, causal stress inference, treatment change, precise-location surveillance or clinically certified wearable data unless separately proven.
