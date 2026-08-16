# HealthIA ONE · Google Health Constellation — CURRENT

**Status:** the core Google mission/action loop has a preserved **LIVE PASS**, and its Golden commit is an ancestor of the current Wave 4 product candidate.

- Golden Google action-loop LIVE SHA: `891745e1ab93dc78b9aa4e54d65b315befa885f2`
- Preserved evidence PR: `#37`
- Current Wave 4 tested product SHA: `a48710eeb5a2e8429a91f5004129064e5af37c1a`
- Relationship: Golden SHA is an ancestor of the Wave 4 SHA
- Wave 4 is integrated into `main`; the tested candidate was not rewritten.

This file distinguishes **LIVE external execution**, **deterministic/contract proof**, and **future/optional providers**. Nothing is promoted merely because code exists.

## Product thesis

HealthIA ONE is a patient intelligence/action OS, not a page of integration buttons.

- the longitudinal clinical/family twin is durable patient context;
- deterministic safety/policy owns hard boundaries;
- Gemini + Google ADK reason and plan when reasoning is valuable;
- the Mission Engine owns state, retries, idempotency and receipts;
- Google services are tools selected only when a patient mission needs them;
- chat remains the primary control surface;
- external execution is never inferred from model prose.

```text
understand
→ plan
→ act safely
→ stop at human boundary
→ resume after authorization
→ wait for external events when needed
→ verify connector outcome
→ remember
→ follow through
```

## Non-negotiable execution boundary

Every Google action follows this contract:

```text
patient intent/event
→ deterministic Safety
→ patient scope/grants
→ semantic plan
→ read-only discovery
→ exact proposed mutation
→ durable authorization when required
→ real connector
→ idempotent receipt
→ mission state
→ patient-visible synthesis
```

Gemini/ADK cannot mint OAuth grants, create HealthIA authorizations, bypass patient scope or turn planned actions into completed receipts.

**Authorization is not execution evidence.** A Gmail/Calendar/Task mutation is projected as complete only from a real connector outcome.

---

## LIVE PASS — real Google action loop

The frozen Golden proof demonstrated the production-shaped mission loop against real Google services:

```text
Safety
→ Mission Router
→ Places API (New)
→ Gmail send
→ Gmail users.watch
→ authenticated Pub/Sub push
→ Gmail users.history.list
→ exact thread correlation
→ Calendar FreeBusy
→ Calendar event create + reread
→ Google Task create + reread
→ durable mission receipts
→ COMPLETED
```

### What the Golden LIVE proof verified

- patient Google OAuth connection persisted for a synthetic/demo HealthIA patient;
- refresh-token use through Secret Manager without exposing secret material;
- real Google Places candidates persisted into the mission;
- real Gmail send with connector resource identity;
- real Gmail `users.watch` metadata;
- a real reply recovered through private authenticated Pub/Sub + `users.history.list`;
- exact Gmail thread correlation;
- real Calendar FreeBusy;
- real Calendar event creation and reread;
- real Google Task creation and reread;
- durable receipts for Places, Gmail, FreeBusy, Calendar and Tasks;
- duplicate Pub/Sub redelivery ACKed as an idempotent no-op;
- no duplicate Calendar/Task side effects;
- dedicated private Gmail worker;
- daily watch-renewal scheduler path;
- no OAuth/token/key material committed to the repository.

The Golden proof remains frozen as evidence. Later product work does not rewrite its claims.

---

## Wave 4 LIVE PASS — consent-aware resource navigation

Wave 4 expands the same mission architecture around a particularly judge-visible Taskmaster flow.

Patient asks for real-world support. HealthIA may create/advance the mission, but before mission-scoped location consent:

- **0 external Google Places searches** execute;
- no candidate list is fabricated;
- the durable mission stores the human authorization boundary.

After consent, the **same mission resumes**.

Wave 4 LIVE evidence verified:

- 4 bounded real Places searches;
- 9 deduplicated real candidates;
- 9/9 candidates with Google Maps URIs;
- websites returned for 6 candidates;
- phone numbers returned for 9 candidates;
- provenance spanning care, community support, government/financial support and general support queries.

The patient can then say:

> **“The second one.”**

HealthIA deterministically selects exactly the second displayed candidate. This bounded human choice does not require another model round.

Wave 4 candidate: `a48710eeb5a2e8429a91f5004129064e5af37c1a`

- full verification / JUDGE: run `31562277991` — SUCCESS
- real resource-navigation proof: run `31562277909` — SUCCESS

---

## Patient Google OAuth connection

The runtime supports the browser flow:

```text
authenticated HealthIA patient
→ /oauth/connect
→ Google consent
→ signed state + PKCE S256
→ callback under same HealthIA patient session
→ authorization-code exchange
→ stable Google sub/email check
→ refresh-token Secret Manager version
→ Firestore connection metadata
```

Security properties:

- `state` is HMAC-signed and short-lived;
- PKCE verifier is short-lived and HttpOnly;
- callback must match the initiating HealthIA patient session;
- access tokens are not persisted;
- refresh/client secrets stay in Secret Manager;
- Firestore stores stable provider identity, scopes and opaque secret references;
- incremental permission bundles are supported;
- switching silently to a different Google account fails closed;
- missing OAuth configuration reports not-ready rather than breaking startup.

Default appointment-mission permissions are bounded to the scopes actually needed for:

- Gmail relevant read/history;
- Gmail send;
- Calendar free/busy;
- Calendar event write;
- Tasks write.

Other Google services remain incremental rather than all-at-login.

---

## Gmail event runtime

The production-shaped Gmail continuation is event-driven.

```text
Gmail users.watch
→ Pub/Sub
→ authenticated private Cloud Run worker
→ users.history.list
→ exact thread correlation
→ mission transition
```

Properties:

- no permanent mailbox polling;
- durable mailbox watch state;
- renewal based on watch expiration metadata;
- unrelated mail ignored;
- exact mission `threadId` matching;
- cursor advances only after successful handling;
- ambiguous/low-confidence replies do not advance the mission;
- duplicate delivery is idempotent;
- disconnect disables HealthIA continuation immediately;
- stale delayed pushes fail closed.

Provider-side Google grant revocation is a separate provider action and is not falsely claimed from a local HealthIA disconnect.

---

## Exact external-write authorization

Read-only discovery and external mutation are deliberately different phases.

For a proposed mutation, HealthIA binds authorization to the material payload. If the payload changes, prior authorization cannot silently authorize the new action.

Examples:

- Gmail recipient/message body;
- selected appointment slot / Calendar payload;
- follow-up Task payload.

The mission receipt records what actually executed and the connector resource identifiers returned by Google.

---

## Shared durable runtime

The Google mission runtime owns:

- patient grants;
- exact action authorizations;
- receipts;
- mission state;
- OAuth connection metadata;
- selected resources;
- provider/tool results.

Firestore is authoritative across Cloud Run processes. OAuth token material never enters the clinical twin, model prompts or public receipts.

---

## Safety-first conversation routing

Strong Google mission intent is evaluated behind deterministic safety.

```text
deterministic Safety
→ Google Mission candidate
→ Opportunity layer when relevant
→ clinical / UI fallback
```

Location truth rules include:

- patient-authorized coordinates may be used;
- patient-explicit location text may be used for Places Text Search;
- locale/timezone/language do not become residence evidence;
- Gemini may not silently invent coordinates or a country;
- search context is not persisted as residence unless separately provided/authorized.

---

## Capability truth table

| Capability | Status |
|---|---|
| Google OAuth patient connection | **LIVE PASS** |
| Google Places API (New) | **LIVE PASS** |
| Mission-scoped location consent before Places | **LIVE PASS** |
| Gmail send | **LIVE PASS** |
| Gmail `users.watch` | **LIVE PASS** |
| Authenticated Pub/Sub push | **LIVE PASS** |
| Gmail `users.history.list` + exact thread correlation | **LIVE PASS** |
| Calendar FreeBusy | **LIVE PASS** |
| Calendar event create + reread | **LIVE PASS** |
| Google Tasks create + reread | **LIVE PASS** |
| Durable receipts + duplicate-delivery idempotency | **LIVE PASS** |
| Opportunity Autopilot | **PASS / separate current contract** |
| Android/Health Connect bridge | **contract + app path; do not infer physical-device LIVE from code alone** |
| FCM delivery | **separate provider gates/evidence; not part of the core prize claim unless its LIVE gate is cited** |
| Document AI | **separate provider gate; not part of core Taskmaster claim** |
| Cloud Healthcare FHIR/DICOM | **separate provider gate; not part of core Taskmaster claim** |
| Veo | **optional bonus path only; never claim integration without an explicit successful proof** |

---

## Why this architecture is not a permanent agent swarm

HealthIA is demand/event-driven. Work begins from a patient message, evidence upload, device event, explicit follow-up or authorized external event.

That choice:

- reduces unnecessary model spend;
- makes tool execution easier to audit;
- keeps patient consent visible;
- makes idempotency and receipts first-class;
- avoids pretending that “always running” automatically means “more autonomous.”

---

## Clinical truth boundary

HealthIA ONE is a patient continuity system and hackathon prototype. It is not a physician, emergency service or autonomous prescription engine.

It does not autonomously diagnose, prescribe, start/stop/change medication or replace professional/emergency evaluation.

All hackathon clinical demonstrations use synthetic data.

---

## Evidence map

Start at repository root:

- `JUDGES_START_HERE.md` — compact current claim/evidence map;
- `docs/WINNING_ONE_TAKE.md` — final judge-demo contract;
- `hackathon/evidence/` — sanitized permanent evidence;
- PR `#37` — preserved Golden Google action-loop evidence;
- PR `#41` — Wave 4 final candidate lineage.

**The rule is simple: if there is no durable connector outcome or preserved proof, HealthIA does not claim the action happened.**
