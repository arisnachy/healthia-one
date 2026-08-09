# HealthIA ONE · Google Health Constellation

Status: **draft candidate with verified guarded runtime and private Cloud ingress proof** on `kira/google-health-constellation`.
Base: `kira/opportunity-autopilot` exact green head `3977b81dc4a6f47599ce9ec7f7f8cdad504a7574`.

`main` is intentionally untouched. Do not merge this branch while any exact-head gate is red/pending or while the remaining live-credential/resource blockers below are unresolved.

## Product thesis

HealthIA ONE is not a chat with a list of Google integrations. The longitudinal clinical/family twin is memory, deterministic safety/policy owns the hard boundaries, Gemini/ADK plans and synthesizes, the durable Mission Engine owns state/idempotency/receipts, and Google products are tools selected only when a patient mission needs them.

`understand → plan → act → wait for events → verify → remember → follow through`

The chat remains the primary control surface. Service-specific views expose evidence, mission state and receipts rather than becoming separate workflows.

## Non-negotiable execution boundary

Every Google action flows through:

`patient intent/event → deterministic safety → patient scope/grants → semantic plan → read-only discovery → exact proposed mutation → durable authorization when required → connector execution → idempotent receipt → mission state → human synthesis`

No Gemini/ADK tool may create its own authorization, invent OAuth access, call raw Gmail/Calendar mutations, or bypass the patient-scoped mission/receipt layer.

## Verified milestones

### 1. Opportunity parent is green and synchronized

PR #36 was hardened and its exact head `3977b81dc4a6f47599ce9ec7f7f8cdad504a7574` passed:

- pytest;
- Full System;
- KIRA DialogBench;
- Chromium browser E2E;
- LAB Ω Core;
- LAB Ω Secondary;
- compileall;
- smoke;
- JUDGE Ω;
- frontend semantic gates;
- PowerShell deployment parsing;
- release ZIP build/verification;
- pytest from the extracted release candidate.

The green parent was merged into this child through internal sync PR #38. `main` was not modified.

### 2. Safety-first Conversation Brain routing

Strong Google mission intent is now routed in this order:

`deterministic Safety → Google Mission candidate → Opportunity → social/clinical/UI fallback`

The async Gemini boundary re-checks Safety before invoking the Google Mission planner. A valid Google mission response returns directly instead of going through a second generic Gemini generation.

Examples:

- `Búscame un centro de autismo en Santiago` can become a navigation mission.
- `Tengo dolor fuerte en el pecho y falta de aire; búscame una clínica` stays in urgent deterministic safety and never becomes a Google mission first.

Location truth rules:

- patient-authorized coordinates may be used;
- patient-explicit location text may be used for Places Text Search;
- locale, timezone or language never become residence/location evidence;
- Gemini may not expand `Santiago` into a country or invented coordinates;
- search context is stored with `is_residence=false`.

### 3. Shared Google Constellation runtime

FastAPI, chat/ADK and event surfaces use the same process-local Constellation singleton in memory mode. Firestore remains authoritative across Cloud Run processes.

The shared runtime owns:

- patient-scoped grants;
- exact action authorizations;
- completed/blocked receipts;
- mission state;
- OAuth connection metadata;
- provider/tool connectors.

OAuth refresh/client secrets are not stored in the clinical twin. Firestore retains only connection metadata and an opaque Secret Manager version reference; short-lived access tokens are obtained lazily when an authorized user-API action needs them.

### 4. Exact-payload authorization

A durable authorization is bound to:

`patient + mission + action + material payload fingerprint + expiry`

Examples:

- authorizing one Gmail recipient/subject/body cannot authorize a changed message;
- authorizing a Calendar slot cannot authorize a different time/location;
- authorization is one-time by default and consumed transactionally;
- duplicate completed requests return the existing receipt rather than repeating the side effect.

### 5. Executable Workspace/Maps mission tools

Implemented behind the shared action policy/receipt boundary:

- Google Maps Platform Places Nearby;
- Places Text Search (New) with explicit `textQuery`, bounded `pageSize` and FieldMask;
- Routes;
- Calendar Free/Busy;
- Calendar create/update/cancel with deterministic event ID recovery;
- Gmail read/watch/draft/send/reply;
- deterministic sent-message recovery before re-send;
- People contact candidate resolution;
- Drive export-container metadata slice;
- Tasks create/update/complete.

Contacts never become genogram relationships from labels alone. Places candidates never become clinical referrals from proximity alone.

### 6. Durable Gmail event worker and watch renewal

Implemented:

- mailbox watch state in Memory/Firestore;
- reverse lookup by connected mailbox;
- watch renewal based on expiration metadata, not mailbox polling;
- account change invalidates the old cursor;
- Gmail Pub/Sub notification decode (`emailAddress` + `historyId`);
- `users.history.list` bridge;
- exact mission `threadId` matching;
- unrelated mail ignored;
- history cursor advances only after successful processing;
- ambiguous/low-confidence administrative reply does not advance mission state;
- private FastAPI worker with lazy Cloud client initialization;
- fail-closed deployment contract with authenticated Pub/Sub push and Scheduler OIDC.

`GOOGLE_CLOUD_PROJECT` is now an explicit required worker environment variable in both production deployment and live-proof workflow. A Cloud proof exposed this missing variable and the production script was corrected before promotion.

### 7. Production-shaped guarded mega-loop

The deterministic integration laboratory proves:

`Maps → selection → Calendar Free/Busy → exact Gmail authorization → Gmail receipt → Pub/Sub reply → offered slot → exact Calendar authorization → Calendar receipt → exact Tasks authorization → Tasks receipt → mission COMPLETED`

The test uses the real Constellation service/store/guard architecture with synthetic connector transport. It proves:

- mission reload across request/process boundaries;
- one-time authorization persistence/consumption;
- duplicate Pub/Sub history is a no-op;
- no duplicate Gmail/Calendar/Tasks side effects;
- completed receipts for every executed tool;
- final public `mission.completed` trace.

### 8. Private Google Cloud live proof

A reversible exact-head proof succeeded for source head:

`28c5b24797a8bdf72f60a21c171a35cd7aff07de`

Evidence:

- Cloud Build ID: `cd6225d5-da32-43fd-a52f-b14d47de555a`;
- Artifact Registry image digest: `sha256:bebeed8ce95d23c2972f930bbee0306a74953d60f7875a520f81eb9d089f03cc`;
- private Cloud Run revision: `healthia-gmail-proof-31333013858-00001-7ww`;
- unauthenticated `/healthz` did not receive a 2xx response;
- authenticated Pub/Sub OIDC subscription was created using an already-authorized project identity;
- a synthetic Gmail-shaped Pub/Sub message was published;
- private `/events/gmail-push` returned HTTP `204`;
- the Firestore-backed worker initialized and failed closed for an unknown mailbox;
- the proof performed no IAM policy mutation;
- temporary service/topic/subscription/image were removed by the workflow cleanup path.

This proves the implemented infrastructure path:

`exact branch head → Cloud Build → Artifact Registry → private Cloud Run → authenticated Pub/Sub OIDC → Gmail worker → Firestore-aware fail-closed handling`

It does **not** prove a real patient Gmail mailbox because no patient OAuth refresh secret is provisioned in Secret Manager.

## Clinical Google Cloud capability layer

The following server-side connectors use **Application Default Credentials (workload identity)**, not patient OAuth refresh tokens. Patient grants/action policy remain an independent HealthIA consent boundary above them.

### Document AI — executable guarded slice

Implemented:

- configured processor resource only;
- private `gs://` evidence URI only;
- synchronous `:process` request;
- text/entities/pages/form fields/tables returned to the internal connector result;
- evidence ID linkage;
- patient text is not copied into public receipt summaries.

Truth boundary: connector/policy/tests exist; no live HealthIA Document AI processor invocation is claimed yet.

### Cloud Healthcare FHIR/DICOM — executable guarded slice

Implemented:

- configured FHIR/DICOM stores only;
- FHIR read;
- FHIR bounded search;
- FHIR create/update with exact patient authorization;
- DICOM study metadata retrieval;
- resource type/ID/query/UID validation against path injection.

Truth boundary: no live HealthIA FHIR/DICOM store is claimed. HealthIA's internal longitudinal twin remains canonical; this is an interoperability gateway.

### Firebase Cloud Messaging — executable guarded slice

Implemented:

- HTTP v1 mission notification connector;
- exact patient authorization before send;
- caller-supplied title/body are ignored;
- lock-screen copy is fixed and PHI-neutral;
- notification data contains only bounded mission routing metadata.

Truth boundary: no real device registration token send is claimed yet.

### Speech-to-Text — executable guarded slice

Implemented:

- synchronous recognition for patient-authorized private audio in Cloud Storage;
- language configuration;
- transcript returned internally, not exposed in receipt summary.

Truth boundary: streaming voice/Gemini Live input is not implied by this slice and remains contract-only.

### Text-to-Speech — executable guarded slice

Implemented:

- bounded patient-facing text synthesis;
- private audio payload returned internally;
- source text stays out of public receipt summary.

Truth boundary: bidirectional Gemini Live voice is separate and not claimed.

### Veo private education — executable guarded slice

Implemented:

- allowlisted Veo models only;
- exactly authorized generation action;
- long-running operation submission;
- output constrained under a private GCS prefix;
- one sample, bounded duration/resolution;
- `personGeneration=dont_allow`;
- no public YouTube output.

Truth boundary: no live Veo generation is claimed until the project has the required private output prefix/API/IAM and the exact action is explicitly authorized. YouTube public search/upload remains a separate contract.

## Capability truth registry

`existing` means already part of the verified HealthIA foundation.

`executable` means a guarded connector/runtime slice exists behind grants/policy/receipts and has deterministic tests. **It does not mean the required external Google resource/account is configured or live-proven.**

`contract` means architecture/policy is reserved but an executable connector slice is not yet promoted.

`deferred` means intentionally outside the current winning path.

### Existing

- Vertex AI / Gemini;
- Google ADK;
- Firestore;
- Cloud Storage;
- Android Health Connect.

### Executable guarded slices

- Maps/Places/Routes;
- Calendar;
- Gmail + Pub/Sub mission bridge;
- People contact candidates;
- Drive export-container metadata;
- Tasks;
- Document AI private-GCS processing;
- Cloud Healthcare FHIR/DICOM gateway;
- FCM PHI-neutral mission notifications;
- Speech-to-Text private-GCS recognition;
- Text-to-Speech;
- private Veo LRO generation.

### Contract only

- Cloud Vision OCR;
- Cloud Translation;
- Firebase Authentication / Identity Platform migration;
- YouTube public education/search/upload;
- Gemini Live bidirectional voice.

### Deferred

- BigQuery population intelligence;
- Google Forms follow-up;
- Google Wallet passes/credentials.

## Remaining live blockers

1. **Real Gmail mailbox:** provision a patient-authorized Google OAuth connection/refresh secret and granted Gmail scopes; only then can `users.watch`, `users.history.list` and a real provider thread be live-proven.
2. **Scheduler renewal:** code/deployment contract exists, but the current GitHub audit principal cannot list Cloud Scheduler jobs; do not claim live watch renewal until the job is independently verified.
3. **Document AI:** configure a processor resource and private evidence path before live invocation.
4. **Cloud Healthcare:** configure HealthIA FHIR/DICOM stores and least-privilege IAM before live interoperability proof.
5. **FCM:** register a real HealthIA device token before a live neutral notification proof.
6. **Speech/TTS:** APIs/runtime access must be verified with synthetic/private evidence before claiming live calls.
7. **Veo:** configure private GCS output prefix and verify API/IAM/cost guard before a live generation proof.
8. **Real external patient side effects:** no real provider Gmail message, Calendar event or Tasks item was created in the infrastructure proof; the guarded mega-loop is production-shaped/synthetic until a patient OAuth account is connected.
9. **Assistance document delivery:** a real external application submission still requires a verifiable external delivery receipt.

## Demo target

The strongest judge-visible mission remains:

> `My son has autism. Find help near us and help me get an appointment.`

Desired trace:

1. HealthIA preserves the son's condition as family context, not the patient's diagnosis.
2. Opportunity source/requisites are verified.
3. Places finds relevant candidates from explicit location evidence.
4. Patient selects a center.
5. Calendar read finds feasible windows.
6. HealthIA prepares the exact inquiry.
7. Patient authorizes that exact Gmail payload.
8. Gmail receipt is stored.
9. Gmail Pub/Sub wakes the private worker when a mission-linked reply arrives.
10. Only the exact thread is read/interpreted.
11. Offered slots are presented.
12. Patient selects one.
13. Exact Calendar/Tasks actions are authorized.
14. Calendar/Tasks receipts close the mission.
15. Optional private education can use Document AI/STT/TTS/Veo without publishing patient-specific content.
16. The Mission Flight Recorder shows Event → Evidence → Decision → Tool → Authorization → Receipt → Outcome, never private chain-of-thought.

The winning story is not “we integrated many Google APIs.” It is:

**HealthIA completed one real patient mission across multiple systems without losing clinical safety, patient/family context, consent, idempotency or proof.**

## Merge rule

Keep PR #37 **draft** and keep `main` untouched until:

- its exact final head passes pytest + Full System + DialogBench + Chromium + LAB Ω Core/Secondary + JUDGE + release verification;
- all documentation reflects the exact candidate;
- any Google product described as live has independent live evidence;
- real patient OAuth/resource configuration is not confused with executable connector code;
- no red/pending required gate remains.
