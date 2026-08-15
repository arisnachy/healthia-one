# HealthIA ONE — Autonomous Care Loop

Autonomy in HealthIA does **not** mean unrestricted action. It means the system can keep a patient-authorized health mission moving without waiting for a new chat prompt, while preserving explicit clinical and external-action boundaries.

## Closed-loop definition

A truly autonomous HealthIA loop is:

`observe -> correlate -> investigate -> choose the next bounded action -> act -> communicate -> wait/observe -> verify outcome -> close or reopen`

Creating an alert is not enough. A mission is autonomous only when HealthIA can remember why it exists, continue after the user leaves, avoid duplicate work, recover from delivery failure, and determine whether the intended next step actually happened.

## Autonomy levels

### A0 — Requested assistant
The patient asks a question and HealthIA answers. This remains available but is not autonomy.

### A1 — Authorized observation
HealthIA receives authorized events such as Health Connect readings, new results, medication check-ins, appointment state, family-history changes, or mission outcomes.

### A2 — Context investigation
Before interrupting the patient, HealthIA checks the longitudinal record and already-authorized context: baseline, trend, recent activity, sleep/HRV when available, medication check-ins, prior results, related missions and evidence provenance.

Correlation is never promoted to causation. Context never suppresses deterministic safety thresholds.

### A3 — Internal autonomous work
HealthIA may create/update a durable mission, prepare a patient question, build a visit brief, identify missing evidence, compare a new result with baseline, or prepare a bounded action plan. These are internal/reversible actions and must remain auditable.

### A4 — Autonomous patient communication
With standing channel consent, HealthIA may contact the **patient** through in-app, FCM push, or Guardian email. Communication must be minimal, privacy-preserving and idempotent. Patient email is limited to the profile email and cannot silently become third-party contact permission.

### A5 — Bounded external logistics
HealthIA may perform explicitly authorized logistics such as an exact Calendar action, exact Gmail provider contact, exact Task, or mission-scoped Maps lookup. Standing consent may be used only where the product defines a narrow, reversible purpose. Clinical treatment decisions are excluded.

### A6 — Outcome verification
HealthIA should verify receipts/evidence and continue or close the mission. Examples: appointment confirmed, requested document received, lab result arrived, patient supplied missing context, or an external provider returned a verifiable administrative response.

## Producers that should become autonomous

1. `result.persisted` — compare a new result with longitudinal evidence, identify meaningful change/missing context, create a mission, notify when warranted, and prepare questions for review.
2. `medication.changed` / adherence events — detect missed/late check-ins, possible continuity gaps or new evidence relevant to the current regimen; never change dose/treatment automatically.
3. `appointment.due` / `appointment.completed` — prepare the visit, collect missing documents/questions, then track the post-visit plan and evidence.
4. `mission.stale` — if the patient has not completed a non-urgent mission, issue a bounded reminder with cooldown; do not nag indefinitely.
5. `family_history.changed` — update risk/watch topics and scientific radar without diagnosing the patient from a relative's condition.
6. `preventive.due` — surface evidence-backed screening/vaccine/preventive tasks using validated rule sets and the patient's record.
7. `recovery.followup_due` — after an acute illness/procedure or a patient-confirmed treatment start, ask the agreed recovery questions and compare trajectory with prior state.
8. `discovery.changed` — when materially relevant science, trial or support-resource evidence changes, compare it with the Clinical Twin/current treatment and notify only when it creates a useful next step.

## Communication contract

- In-app is the durable home of the mission.
- Push is PHI-neutral on the lock screen.
- Guardian email requires `guardian_email` + `guardian_email_auto_send`, the patient's profile email, an active connected Gmail scope, exact action authorization, provider receipt and idempotency.
- Quiet hours, snooze and proactive pause apply to non-urgent Guardian email.
- Email is not the sole urgent-safety channel.
- Contacting clinicians, relatives, providers, government programs or any third party remains a separate scoped authorization.

## Hard clinical/privacy boundaries

HealthIA autonomy must never, by itself:

- diagnose a causal explanation from a correlation;
- start/stop/change a medication or treatment;
- claim trial/program eligibility or application completion without evidence/receipt;
- expose raw GPS coordinates in Guardian reasoning or patient email;
- contact a third party under the patient's self-notification consent;
- silently override a patient pause/revocation;
- repeat the same external action because of Eventarc/worker redelivery;
- treat a model response as stronger evidence than the underlying clinical source.

The target is **persistent helpfulness with bounded agency**: HealthIA should keep working, but it must know exactly where it is required to stop and ask a human.
