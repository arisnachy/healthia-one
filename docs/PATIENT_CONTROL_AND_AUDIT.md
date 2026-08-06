# Patient control, consent and audit

HealthIA ONE is designed around patient-controlled continuity. Proactive behavior is not an unrestricted background permission.

## Consent model

The patient controls:

- whether proactive interventions are enabled;
- which signal classes may activate them;
- quiet hours;
- temporary snooze;
- muted rule families;
- whether deterministic urgent safety alerts may bypass quiet hours and snooze.

Signal classes currently include vitals, weight, activity, results, missions, family history, documents, medications and appointments.

Disabling a signal prevents it from producing proactive follow-up. It does not delete the underlying patient record. Data deletion and retention require a separate production policy and authenticated workflow.

## Quiet hours and snooze

Non-urgent findings are held during quiet hours and while snoozed. Quiet hours support ranges that cross midnight. Urgent deterministic findings may bypass the restriction only when `allow_urgent_safety_bypass` is enabled.

## Muted rules

A patient may mute a rule family from an intervention card. The UI stores a stable prefix such as `weight:` rather than a one-time event ID, so future findings of that class remain silent until the patient removes the mute.

## Audit log

The audit log records public operational facts:

- actor;
- action;
- resource type and ID;
- timestamp;
- outcome;
- selected non-secret details.

It does not store private chain-of-thought, API keys, document bytes, or hidden model reasoning.

The local implementation keeps the latest 1,000 audit events in patient state. Production requires append-only cloud storage, access controls, retention policy and tamper-evident verification.

## Patient export

`GET /api/export` produces a structured JSON export of the patient state. Internal document storage paths are removed. Binary files are not embedded; only document metadata is included.

## Chronology integrity

Backdated vitals, weight, activity, results, documents, medication check-ins and appointments are sorted by their clinical or operational timestamp after insertion. This prevents UI and proactive rules from treating upload order as clinical order.

## BASTION

BASTION is the Google ADK specialist responsible for permissions, privacy boundaries, reversible controls and public auditability. KIRA routes privacy requests to BASTION without mixing them into clinical interpretation.

## Production boundary

The current implementation remains a synthetic hackathon system. Real-patient deployment still requires authentication, patient isolation, encrypted Cloud Storage, Firestore security rules, access logging, deletion and retention workflows, legal review, clinical governance, incident response and independent security testing.
