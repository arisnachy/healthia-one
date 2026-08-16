# HealthIA ONE · Google Health Constellation

Status: **verified draft candidate with guarded runtime, private Cloud ingress proof, patient OAuth browser flow, and bounded live-promotion evidence** on `kira/google-health-constellation`.

Base: `kira/opportunity-autopilot` exact green parent `3977b81dc4a6f47599ce9ec7f7f8cdad504a7574`.

`main` is intentionally untouched. PR #37 stays draft until the remaining external Google resources/credentials needed for a real patient-account mission are provisioned and independently proven.

## Product thesis

HealthIA ONE is a patient intelligence/action OS, not a page of integration buttons.

- the longitudinal clinical/family twin is memory;
- deterministic safety/policy owns hard boundaries;
- Gemini/ADK plans and synthesizes;
- the durable Mission Engine owns state, retries, idempotency and receipts;
- Google products are tools selected only when a patient mission needs them;
- chat remains the primary control surface.

`understand → plan → act → wait for events → verify → remember → follow through`

## Non-negotiable execution boundary

Every Google action follows:

`patient intent/event → deterministic Safety → patient scope/grants → semantic plan → read-only discovery → exact proposed mutation → durable authorization when required → connector → idempotent receipt → mission state → human synthesis`

Gemini/ADK cannot mint OAuth grants, create HealthIA authorizations, call raw sensitive mutations, or bypass the patient-scoped mission/receipt layer.

## Verified core

### Parent and exact-head quality gates

The Opportunity Autopilot parent was hardened and synchronized into this branch through internal PR #38.

The Google Constellation candidate has repeatedly passed the exact-head gate set after each material runtime change:

- pytest diagnostics;
- Full System;
- KIRA DialogBench;
- Chromium browser E2E;
- LAB Ω Core;
- LAB Ω Secondary;
- compileall;
- smoke;
- JUDGE Ω;
- frontend semantic/runtime checks;
- secure PowerShell parsing;
- release ZIP build/verification;
- pytest from the extracted release candidate.

The one-take judge recording remains an explicit opt-in job; a skipped recording job is not a product failure.

### Safety-first Conversation Brain

Strong Google mission intent is evaluated in this order:

`deterministic Safety → Google Mission candidate → Opportunity → social/clinical/UI fallback`

The async Gemini boundary re-checks Safety before executing the mission planner. A valid Google mission response returns directly instead of being sent through a second generic generation.

Location truth rules:

- patient-authorized coordinates may be used;
- patient-explicit location text may be used for Places Text Search;
- locale, timezone and language never become residence/location evidence;
- Gemini may not silently expand `Santiago` into a country or invented coordinates;
- search context is stored as search context, not residence.

### Shared Constellation runtime

FastAPI, chat/ADK and event surfaces share one process-local Constellation in memory mode. Firestore is authoritative across Cloud Run processes.

The runtime owns:

- patient grants;
- exact action authorizations;
- receipts;
- mission state;
- OAuth connection metadata;
- provider/tool connectors.

OAuth token material never enters the clinical twin, prompts or public receipts.

## Patient Google OAuth connection flow

The browser flow now exists end-to-end in code:

`authenticated HealthIA patient → /oauth/connect → Google consent → signed state + PKCE S256 → callback under the same patient session → authorization-code exchange → stable Google sub/email check → refresh-token Secret Manager version → Firestore connection metadata`

Implemented protections:

- `state` is HMAC signed and expires quickly;
- PKCE verifier is stored only in a short-lived HttpOnly cookie;
- callback must match the same HealthIA patient session;
- `access_type=offline` is requested for refresh-token capability;
- incremental scopes are supported;
- scopes are requested by bounded HealthIA grant bundle rather than all-at-login;
- Google `sub` is persisted as stable provider identity;
- switching silently to a different Google account is rejected until explicit disconnect;
- access tokens are never persisted;
- refresh/client secrets live only in Secret Manager;
- Firestore stores only account/scopes/stable subject + opaque secret version reference;
- missing OAuth configuration reports `readiness=false` and `/connect` fails closed instead of breaking HealthIA startup;
- Secret Manager clients are lazy and are not initialized just to render readiness/UI.

Default connect bundles cover the appointment mega-loop only:

- Gmail relevant-read;
- Gmail send;
- Calendar free/busy;
- Calendar event write;
- Tasks write.

Contacts, Drive and YouTube upload remain incremental permissions.

### OAuth deployment contract

`deployment/configure-google-oauth.ps1` configures an existing Cloud Run service only after `-Confirmed`.

It does **not**:

- create a Google OAuth Client ID;
- register redirect URIs in Google Auth Platform;
- enable APIs;
- print secret payloads;
- grant project-wide Secret Manager access.

It requires two existing Secret Manager versions:

1. OAuth application client JSON in the exact shape:

```json
{"client_id":"...apps.googleusercontent.com","client_secret":"..."}
```

2. a random OAuth state-signing secret of at least 32 bytes.

It grants the Cloud Run runtime identity `roles/secretmanager.secretAccessor` only on those specific secrets, injects the state secret as `HEALTHIA_GOOGLE_OAUTH_STATE_SECRET`, and stores only the client-secret **resource name** in `HEALTHIA_GOOGLE_OAUTH_CLIENT_SECRET_RESOURCE`.

For a known HealthIA patient ID the script can also precreate the deterministic empty token-secret shell `healthia-google-oauth-<sha256(patient_id)[:24]>` and grant the runtime identity only:

- Secret Version Adder;
- Secret Accessor;
- Secret Manager Viewer metadata on that one secret.

The token secret contains no refresh token until that patient actually approves Google consent.

The configured OAuth redirect path is always:

`/api/google-constellation/oauth/callback`

Cloud uses HTTPS; localhost HTTP is accepted only by local development code.

## Gmail event runtime and disconnect semantics

Implemented:

- durable mailbox watch state in Memory/Firestore;
- reverse lookup by connected mailbox;
- watch renewal by expiration metadata, never mailbox polling;
- Gmail Pub/Sub decode (`emailAddress` + `historyId`);
- `users.history.list` bridge;
- exact mission `threadId` matching;
- unrelated mail ignored;
- cursor advances only after successful processing;
- ambiguous/low-confidence administrative replies do not advance mission state;
- private Cloud Run worker with authenticated Pub/Sub OIDC;
- private Scheduler/bootstrap endpoints;
- deployment contract for renewal scheduling.

Disconnect is immediate from HealthIA's point of view:

- OAuth connection becomes disabled;
- renewal scans retire watches for disabled/mismatched accounts without calling Gmail or Secret Manager;
- an already-in-flight Pub/Sub push for a disconnected or replaced mailbox is ACKed with 204, the stale watch is disabled, and Gmail history is not read.

Provider-side Google grant revocation remains a separate explicit provider action; HealthIA does not falsely claim it from a local disconnect.

## Guarded appointment mega-loop

The production-shaped deterministic laboratory proves:

`Maps → candidate selection → Calendar Free/Busy → exact Gmail authorization → Gmail receipt → Pub/Sub reply → offered slot → exact Calendar authorization → Calendar receipt → exact Tasks authorization → Tasks receipt → mission COMPLETED`

It exercises the real mission/guard/store architecture with synthetic connector transport and proves:

- mission reload across requests;
- one-time authorization persistence/consumption;
- changed payload requires a new authorization;
- duplicate Pub/Sub delivery is a no-op;
- no duplicate Gmail/Calendar/Tasks side effects;
- durable public receipts for executed tools.

## Private Cloud ingress proof

The Gmail worker path has been repeatedly proven from exact branch heads using reversible Cloud resources:

`exact source → Cloud Build → immutable Artifact Registry image → private Cloud Run → authenticated Pub/Sub OIDC → /events/gmail-push → Firestore-backed worker → fail-closed 204`

A post-OAuth-hardening proof on source `181c9fb63380b7400aa61645df73eaa1848309d5` produced:

- Cloud Build `ecc3d226-5a14-49c6-805e-24a7952c2f61`;
- image digest `sha256:c8256e765b4f13c113580e9c5899124a9769702cf6181b22f3bafd15fa0c3ceb`;
- private revision `healthia-gmail-proof-31338708081-00001-wq4`;
- unauthenticated `/healthz`: non-2xx (`404`);
- authenticated Pub/Sub message `20954778993306324`;
- `/events/gmail-push`: `204`;
- no IAM mutation by the proof workflow;
- temporary proof resources cleaned up.

This does **not** equal a real patient Gmail proof because no patient Google OAuth consent/refresh secret has been provisioned yet.

## Clinical Google Cloud connector layer

Server-side clinical cloud connectors use Application Default Credentials/workload identity. Patient grants/action policy remain an independent HealthIA consent boundary above cloud IAM.

### Document AI — executable, live-blocked

Guarded code supports configured processor + private `gs://` evidence, returning structured internal extraction without copying patient text into receipt summaries.

Current live blocker: `documentai.googleapis.com` is not enabled in the audited project and no HealthIA processor resource is configured. Finalization workflows intentionally do not enable it silently.

### Cloud Healthcare FHIR/DICOM — executable, live-blocked

Guarded code supports configured stores, bounded FHIR read/search/create/update and DICOM study metadata with path/identifier validation.

HealthIA's internal twin remains canonical; FHIR/DICOM is an interoperability gateway.

Current live blocker: `healthcare.googleapis.com` is not enabled and no HealthIA FHIR/DICOM stores are configured.

### Firebase Cloud Messaging — executable, IAM/device-blocked

The HTTP v1 connector uses PHI-neutral lock-screen text; caller-supplied sensitive notification title/body are ignored.

Live promotion probe result:

- FCM API is enabled;
- CI proof identity receives `PERMISSION_DENIED` on send;
- the probe uses an intentionally invalid registration token, so no device can receive it.

Remaining live requirements: runtime FCM send permission + a real HealthIA device registration token.

### Speech-to-Text — executable, API-blocked

Guarded synchronous recognition accepts only patient-authorized private GCS audio and keeps transcript content out of public receipt summaries.

Current blocker: `speech.googleapis.com` is not enabled. Streaming/Gemini Live remains a separate contract.

### Text-to-Speech — executable and live-proven synthetic

A bounded authenticated live probe succeeded against the project Text-to-Speech API using only synthetic text:

- HTTP synthesis returned MP3 data;
- audio bytes: `22848`;
- audio SHA-256: `d412fd495192a3b35f732c45faddaa1ed1f24ed01757631d3be81fe4daa9467a`;
- generated bytes were deleted immediately and were not uploaded as an artifact;
- no patient content was used.

Bidirectional Gemini Live voice remains separate and is not implied by this proof.

### Veo private education — executable, cost-gated

The connector constrains model allowlist, duration/resolution, one output, `personGeneration=dont_allow`, exact authorization, and private GCS output.

Vertex AI API is enabled, but CI never auto-triggers a billable Veo generation. Live Veo stays behind explicit cost/authorization + private output-resource gates. Public YouTube remains separate.

## Live Promotion Matrix

`.github/workflows/google-live-finalization.yml` runs only bounded synthetic/read-only probes and explicitly forbids:

- API enablement;
- IAM mutation;
- patient data;
- real FCM device delivery;
- automatic Veo generation.

Current matrix truth:

- Text-to-Speech: **LIVE PASS**;
- FCM: **BLOCKED_IAM**;
- Speech-to-Text: **BLOCKED_DISABLED_API**;
- Document AI: **BLOCKED_DISABLED_API**;
- Cloud Healthcare: **BLOCKED_DISABLED_API**;
- Veo: **COST_GATED**;
- Cloud Scheduler inventory: **BLOCKED_IAM** for the current GitHub audit identity (`cloudscheduler.jobs.list`).

## Capability truth registry

`existing` = verified HealthIA foundation.

`executable` = guarded connector/runtime slice exists behind grants/policy/receipts and deterministic tests. It does not automatically mean external Google resources are configured.

`contract` = architecture/policy reserved but not promoted to executable connector.

`deferred` = intentionally outside the current winning path.

### Existing

- Vertex AI / Gemini;
- Google ADK;
- Firestore;
- private Cloud Storage;
- Android Health Connect.

### Executable guarded slices

- Maps/Places/Routes;
- Calendar;
- Gmail + Pub/Sub mission bridge;
- patient Google OAuth browser connection flow;
- People contact candidate resolution;
- Drive export-container metadata;
- Tasks;
- Document AI private-GCS processing;
- Cloud Healthcare FHIR/DICOM gateway;
- FCM neutral mission notification;
- Speech-to-Text private-GCS recognition;
- Text-to-Speech (**live-proven synthetic**);
- private Veo long-running generation.

### Contract only

- Cloud Vision OCR;
- Cloud Translation;
- Firebase Authentication / Identity Platform migration;
- YouTube public education/search/upload;
- Gemini Live bidirectional voice.

### Deferred

- BigQuery population intelligence;
- Google Forms follow-up;
- Google Wallet.

## Remaining real promotion blockers

1. **Google OAuth external configuration:** create/configure a Google OAuth Web Client outside the repo, register the exact HTTPS callback, store the client JSON + state secret in Secret Manager, and run the confirmed least-privilege provisioning contract.
2. **Real patient OAuth consent:** connect a test patient Google account and obtain a real refresh-token version; only then can real Gmail/Calendar/Tasks actions be promoted.
3. **Real Gmail watch:** execute `users.watch`, receive a real mailbox Pub/Sub event, call `users.history.list`, and prove exact mission-thread resumption.
4. **Scheduler renewal:** current GitHub audit principal cannot independently list Scheduler jobs; no live renewal claim yet.
5. **Document AI:** API + processor resource still need provisioning.
6. **Cloud Healthcare:** API + FHIR/DICOM stores + least-privilege IAM still need provisioning.
7. **FCM:** runtime send IAM + real device registration token are missing.
8. **Speech-to-Text:** API is disabled; no live audio recognition claim.
9. **Veo:** explicit cost gate/private output setup is still required before a live generation.
10. **External assistance delivery:** an assistance application cannot become `SUBMITTED` without a verifiable external delivery receipt.

## Judge-visible target

The strongest end-to-end mission remains:

> `My son has autism. Find help near us and help me get an appointment.`

Desired trace:

1. preserve the son's condition as family context, not the patient's diagnosis;
2. verify the Opportunity source and requirements;
3. Maps finds candidates from explicit location evidence;
4. patient selects a center;
5. Calendar read finds feasible windows;
6. HealthIA prepares the exact inquiry;
7. patient authorizes the exact Gmail payload;
8. Gmail receipt is stored;
9. Gmail Pub/Sub wakes the private worker on a mission-linked reply;
10. only the exact thread is read/interpreted;
11. offered slots are presented;
12. patient chooses;
13. exact Calendar/Tasks actions are authorized;
14. receipts close the mission;
15. optional private education uses guarded cloud tools without publishing patient-specific content;
16. Mission Flight Recorder shows Event → Evidence → Decision → Tool → Authorization → Receipt → Outcome, never private chain-of-thought.

The winning story is:

**HealthIA completes one real patient mission across multiple systems without losing clinical safety, patient/family context, consent, idempotency or proof.**

## Merge rule

Keep PR #37 **draft** and keep `main` untouched until:

- the exact final head passes pytest + Full System + DialogBench + Chromium + LAB Ω Core/Secondary + JUDGE + release verification;
- Cloud ingress proof and Live Promotion Matrix are green on that exact head;
- documentation matches the candidate;
- anything described as live has independent live evidence;
- the real patient OAuth/resource gate is not confused with executable connector code.
