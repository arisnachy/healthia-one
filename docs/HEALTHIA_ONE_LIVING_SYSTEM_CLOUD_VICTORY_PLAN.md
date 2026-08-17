# HealthIA ONE - Living System Cloud Victory Plan

## Mission

Turn the HealthIA ONE Master Document into one truthful, judge-visible product journey that runs on Google Cloud and makes the system feel alive:

```text
authorized event
  -> policy and provenance
  -> versioned Patient Twin update
  -> personal-baseline deviation
  -> durable mission
  -> bounded autonomous action
  -> human boundary when required
  -> durable verification receipt
  -> Twin learns from the outcome
```

This is a build contract, not a claim that the work below is already complete. It deliberately separates `IMPLEMENTED`, `TESTED`, `VERIFIED`, and `COMPLETE`.

## Victory condition

A judge opens one stable link and, without repository knowledge, can see a synthetic patient system wake up, ingest an event, change the longitudinal Twin, detect a patient-specific deviation, open and advance the same mission, stop at a real authorization boundary, resume safely, verify the outcome, and preserve the resulting state across logout/relogin.

The same experience must expose:

- the exact deployed source SHA and Cloud Run revision;
- the agents and typed tools that actually executed, without chain-of-thought;
- provenance from derived state back to the synthetic source;
- durable mission transitions and external/synthetic receipts;
- patient consent, clinical limits, cost limits, and an automatic return to dormant mode;
- an evidence replay that another reviewer can reproduce.

The final judge reaction we optimize for is:

> "This is not a chatbot. The patient changed, the system noticed, the agents moved the work forward, and nothing was called complete until there was evidence."

## Confirmed baseline - 2026-08-16

### Repository truth

- Real checkout: `healthia-one/`.
- Local checkout: `main` at `bd1ce0614be330142ed2f49a87979423e91ba192`.
- Fetched `origin/main`: `ec233508497a982a3f026b4bad9895e748e15ea6`.
- Local checkout is 670 commits behind fetched `origin/main` and contains user-owned modifications in `README.md`, `deployment/run-local-secure.ps1`, and `tests/test_forja_runtime_contracts.py`, plus untracked `.kira/` and `dist/` content.
- Therefore no product implementation may begin by resetting, checking out over, or blindly merging this working tree. Reconciliation is Gate 1.

### Existing product and cloud truth

- Remote main already contains durable autonomy, Eventarc/Pub/Sub workers, Gmail reply recovery, Google mission actions, Firestore state, GCS evidence, ADK/Gemini boundaries, Android/FCM work, consent gates, receipts, idempotency tests, and a read-only synthetic Judge Mode.
- The existing public Judge Mode is intentionally GET-only and cannot mutate state or call a model. It proves evidence but is not yet the interactive Living System experience defined here.
- Current Cloud Run includes separate web/demo, judge, autopilot, Gmail, and FCM surfaces. Operational workers remain private and services scale to zero by default.
- Current IAM inspection did not confirm anonymous `allUsers` access for the web/demo/judge services. Existing service URLs are infrastructure, not yet proof of one judge-accessible public product link.
- A daily Gmail watch-renewal scheduler is enabled. Scale-to-zero therefore reduces idle compute but does not by itself prove zero background activity or zero storage/event cost.
- The deployed Judge Mode is stamped to source `8f4b468336499eb9175ae9be1caaac745f24782e`, while fetched `origin/main` is newer. A new claim requires exact-head redeployment and proof.
- Existing exact-head videos and provider receipts remain preserved fallbacks. They are not silently replaced.

### Planning-tool boundary

The official Devpost guided-build state, PRD, and spec files are not initialized in this checkout. This plan therefore uses the same acceptance/verification discipline without inventing Devpost state. Submission state must later be read from Devpost itself.

## Build preferences

- **Build mode:** Autonomous execution after explicit approval to start implementation.
- **Chronogram:** None. Work advances only by evidence gates, not calendar estimates.
- **Git discipline:** One focused branch from current remote main; one reversible commit per passed gate; no unrelated user changes included.
- **Verification:** Continuous focused tests, full regression before cloud promotion, exact-SHA live proof, independent clinical/security review, and independent final JUDGE.
- **Demo data:** Synthetic only.
- **Cloud posture:** Private workers, public bounded evaluation surface, scale-to-zero default, maximum one evaluation instance, durable request/token caps.

## Non-negotiable product rules

1. The Patient Twin is structured, versioned state; chat is an interface, not memory.
2. Every derived fact retains provenance and confidence.
3. `EVENT -> POLICY -> TWIN UPDATE -> DETECTOR -> MISSION?` happens before generative narration.
4. Model prose never proves tool execution.
5. A mission does not close without a durable receipt or explicit justified cancellation.
6. Judge Mode increases presentation and bounded compute capacity; it never bypasses clinical policy, consent, identity, or professional authorization.
7. No autonomous diagnosis, prescription, medication change, emergency replacement, or regulatory claim.
8. Operational Google workers and secrets never become public merely to simplify the demo.
9. No real patient data, OAuth material, service-account credentials, device tokens, or raw connector secrets appear in logs, screenshots, video, Git, or judge APIs.
10. The demo must fail closed: missing evidence remains pending; missing consent remains blocked; exhausted budget remains unavailable.

## Complete manifesto contract

The hackathon candidate is not a disposable blood-pressure demo. It is the first working vertical slice of the long-term Patient Digital Twin OS described in the Master Document. Every future capability must grow from the same canonical Twin, event, policy, mission, provenance, consent, and verification contracts implemented now.

### Permanent mission

HealthIA ONE exists to maximize healthy lifespan while reducing preventable disease, avoidable disability, and unnecessary therapeutic burden. The operating objectives are explicit product contracts:

1. **ONE PREVENT:** identify safe, evidence-bounded opportunities to prevent avoidable disease.
2. **ONE PRESERVE:** preserve organ-system state and functional capacity.
3. **ONE DETECT:** recognize meaningful patient-specific deviation early.
4. **ONE OPTIMIZE:** prioritize modifiable factors without presenting uncertain projections as facts.
5. **ONE MINIMIZE BURDEN:** pursue the Minimum Effective Health Burden, never by autonomously changing treatment.
6. **ONE LEARN:** update the individual Twin from verified outcomes; population learning requires separate consent and research governance.

### One architecture, four commitment levels

| Manifest capability | Hackathon commitment | Truth boundary |
|---|---|---|
| Versioned ONE PATIENT TWIN | Build and show live | Canonical structured state, not chat memory |
| Personal baseline, trajectory, deviation and confidence | Build and show for the promoted synthetic signals | Patient-specific comparison is not a diagnosis |
| Organ/system objects and persistent anatomy | Build the schema; show one surgery/anatomy state and selected cardiovascular/metabolic/functional projections | No unsupported physiological simulation |
| Clinical Event Graph and follow-up obligations | Build a bounded graph for laboratory, medication, surgery/hospital event, and device observations | Edges represent provenance/obligation, not automatic causality |
| ONE GUARDIAN permanent attention economy | Build as durable event-driven work, not permanent polling | It ignores noise, batches weak signals, and escalates only under policy |
| ONE MEDS expected-versus-observed monitoring | Build a safe medication-exposure/monitoring contract and one synthetic example | No dose change, prescription, or adherence accusation |
| Clinical Review Pack | Build and show | Professional context; never an autonomous signed clinical decision |
| Healthspan domains, Age & Biology, Modifiability | Preserve explicit contracts and show only supported descriptive trajectories | No biological-age or efficacy claim without validated models |
| Patient Future Simulator | Preserve scenario/provenance/uncertainty interfaces; optional illustrative non-clinical prototype only | Never predict a guaranteed personal outcome |
| ONE DE-MED | Produce future clinician-review opportunities from verified contributors | Never stop or reduce medication autonomously |
| ONE N=1 LAB | Preserve intervention/baseline/outcome/confounder contracts | Future supervised microexperiments only |
| ONE COLLECTIVE, ONE MATCH, ONE CAUSAL LAB, ONE DISCOVERY | Architect domain separation, consent, governance and evidence pipeline; do not activate population research for the hackathon | No cross-patient learning, causal or discovery claim without a governed research system |

### Meaning of learning

For the hackathon, `LEARN` means that verified new evidence updates one synthetic patient's baseline, expectations, obligations, and future detector state. It does **not** mean uncontrolled model retraining or transfer of one patient's identifiable data to another. Future collective learning must use a separately authorized research domain with identity separation, cohort governance, audit, statistical validity, external validation, and explicit uncertainty.

### HealthIA ONE Core v0.1

The winning candidate implements one coherent core, not a collection of disconnected mock screens:

```text
TWIN + GUARDIAN + LABS + MEDS + DEVICE + MISSIONS + VERIFY
```

`MEDS` in Core v0.1 means structured medication exposure, expected-versus-observed monitoring, an obligation, and a professional-review boundary. It does not mean an autonomous medication agent or any prescription/dose action.

The named runtime actors promoted in the demo are limited to **ONE SENSE**, **ONE TWIN**, **ONE GUARDIAN**, **ONE SAFETY**, and **ONE VERIFY**. Each promoted actor must have a durable sanitized event or typed-tool receipt. ONE PREVENT, ONE LONGEVITY, autonomous ONE MEDS, ONE DE-MED, ONE COORDINATOR, ONE MATCH, ONE CAUSAL LAB, ONE DISCOVERY and ONE COLLECTIVE are product domains or future agents until their own executions are independently proven; the video must not depict them as live autonomous workers.

### Autonomy ladder

Autonomy is assigned per action class, never by a global "judge mode" switch:

- **A0 Observe:** ingest, normalize, version, display and explain evidence.
- **A1 Suggest:** prepare a reversible recommendation or question; a person decides.
- **A2 Act with confirmation:** execute only after the required patient/professional authorization.
- **A3 Bounded autonomy:** execute reversible, low-risk administrative/continuity actions inside consent and quotas.
- **A4 Clinically consequential autonomy:** unavailable in the hackathon candidate; requires formal validation, governance and professional authority.
- **A5 Research/population autonomy:** unavailable; requires a separate governed research platform and consent.

Judge Evaluation may increase scenario capacity only. It may not promote an A0-A3 action into A4/A5.

### Explicit scientific and medication prohibitions

- Observational associations, cross-patient comparisons, correlated signals and N=1 outcomes are never presented as causal effects or therapeutic recommendations.
- HealthIA may open a professional review opportunity, but it never starts, stops, reduces, increases or substitutes medication autonomously.
- Reducing therapeutic burden remains subordinate to net clinical benefit, demonstrated stability, patient preference and qualified professional authorization.
- A literature/guideline source may inform a review only with version, jurisdiction, provenance and applicability; it never silently becomes patient truth.

### Minimum canonical contracts for the candidate

The versioned Twin must expose at least `version`, `patient_namespace`, `source_event_ids`, `identity_context`, `organ_system_state`, `anatomy_state`, `observations`, `medication_exposures`, `baseline`, `trajectory`, `deviations`, `confidence`, `consent_scope`, `clinical_event_edges`, `active_missions`, `obligations`, `evidence_refs`, and `updated_at`.

The public sanitized event sequence is fixed and testable:

```text
event_received
  -> policy_checked
  -> observation_normalized
  -> twin_versioned
  -> baseline_compared
  -> signals_correlated
  -> deviation_detected
  -> guardian_investigation_opened
  -> mission_opened
  -> human_boundary
  -> bounded_action_executed
  -> receipt_recorded
  -> mission_verified
  -> twin_updated_from_verified_outcome
```

Each event carries a schema version, synthetic patient namespace, correlation/mission ID, timestamp, actor, policy decision, source/evidence IDs and status. It never includes chain-of-thought, PHI, credentials or unrestricted tool input.

### Interoperability and scale seams

- Map conceptual Master Document APIs to existing routes; do not create duplicate public sources of truth merely to match names.
- Preserve FHIR-resource mappings and future EHR/HealthKit connectors without claiming them LIVE.
- Treat the Clinical Event Graph as canonical typed relations over events, findings and obligations. A future Knowledge Graph may index those relations but may not replace them.
- Firestore can hold the bounded candidate time series; a dedicated time-series store is a scale seam, not a hackathon dependency.
- GCS preserves private originals and evidence; transformed data always links back to the immutable source and generation.

## Promoted story

The demo will show breadth through one causal patient story, not a feature catalog.

### Preloaded synthetic Twin

The judge starts with a longitudinal patient whose Twin already contains:

- demographics, preferences, and consent scopes;
- a prior surgery reflected in current anatomy state;
- medications with indication, expected response, and monitoring obligation;
- laboratory trends and original-document provenance;
- device-derived blood pressure, activity, sleep, and weight baselines;
- open/watch/completed missions and a concise Clinical Review Pack.

### Live autonomous event

A new authorized synthetic Health Connect event bundle enters the real application with a correlated, four-day change in blood pressure, weight, resting/night heart rate, and activity. Each signal is weak enough to avoid an unsupported diagnosis; together they open a visible `Guardian Investigation`. The single promoted clinical-continuity action remains the already-bounded blood-pressure measurement follow-up, so the broader intelligence is visible without expanding clinical authority:

1. ONE SENSE validates identity, source, time, units, and consent.
2. ONE TWIN writes a new version and updates organ/system trajectories and the Clinical Event Graph.
3. ONE GUARDIAN compares population reference, personal baseline, and trajectory, correlates the authorized signals, and suppresses isolated noise.
4. ONE SAFETY classifies risk and permitted autonomy.
5. A durable follow-up mission opens with evidence IDs, missing data, allowed tools, and a closure condition.
6. The system advances every reversible/authorized step without another prompt.
7. At a human boundary, it visibly stops and requests the exact authorization or measurement needed.
8. The same mission resumes after the synthetic patient acts.
9. ONE VERIFY closes only after a canonical measurement/receipt is persisted.
10. The Twin, expectations, obligations, and future detector baseline update, and Mission Replay reconstructs why.

The same screen also exposes preloaded longitudinal breadth: prior surgery with persistent anatomy, a medication with an expected monitoring obligation, a laboratory trend with source provenance, organ-system summaries, active missions, and the Clinical Review Pack. These are canonical Twin projections, not decorative cards.

This circuit demonstrates the manifesto while preserving the architectural decision not to promote autonomous diagnosis or treatment.

## Evaluation activation design

HealthIA must not guess that a visitor is a judge from IP address, user agent, geography, or behavior. Evaluation is an explicit capability.

### State machine

```text
DORMANT
  -> signed/authorized evaluation entry
ARMING
  -> isolated synthetic namespace + durable budget lease
ACTIVE
  -> run one bounded scenario and allow replay/reset
EXHAUSTED | EXPIRED | MANUAL_CLOSE
  -> revoke lease, disable model/tool mutations, retain sanitized proof
DORMANT
```

### Public/private split

- **Public landing/evidence:** cheap GET-only explanation, exact SHA, health, video, architecture, and "Start evaluation" entry.
- **Bounded evaluation application:** synthetic account/session only, isolated Firestore namespace, limited resets and model calls, no unrestricted Google-account mutation.
- **Private execution plane:** Eventarc/Pub/Sub workers, Gmail/Calendar/Tasks connectors, secrets, provider credentials, and administrative proof endpoints behind Cloud Run IAM.
- **Evidence replay:** sanitized receipts from both the interactive synthetic session and preserved real-provider proofs, clearly labeled.

The judge gets one coherent product link. Internal service separation remains invisible unless the judge opens the architecture/evidence drawer.

## Verifiable build checklist

- [ ] **1. Reconcile the real checkout without losing user work**
  Source ref: `AGENTS.md`; current repository and remote refs.
  What to build: Inventory the dirty local files, preserve their diffs, create a clean worktree/branch from fetched `origin/main`, and carry forward only intentional compatible changes. Do not reset the current working tree. Establish the new candidate base SHA in the plan notes.
  Acceptance: The implementation branch is based on current `origin/main`; the original dirty checkout is unchanged; every carried change is attributable; `git diff --check` passes.
  Verify: `git status --short`; `git rev-list --left-right --count <candidate>...origin/main`; inspect preserved patches and worktree paths.

- [ ] **2. Turn the Master Document into executable product contracts**
  Source ref: `HealthIA_One_Documento_Maestro_v1.0.docx` sections 3, 5, 6, 16, 17, 21, 25, and 27.
  What to build: Add versioned contracts for Twin layers; organ/system state; observations; personal/population/trajectory references; anatomy; Clinical Event Graph nodes/edges; medication exposure, expected response and monitoring; obligations; missions; consent; action logs; provenance; confidence; modifiability; healthspan domains; intervention/outcome envelopes for future N=1; and patient-state transitions. Add dormant interface contracts for Future Simulator and separately governed ONE COLLECTIVE research without implementing unsupported models. Map existing models instead of creating a second source of truth.
  Acceptance: Existing persisted patients migrate or read compatibly; each new field has validation and a truth boundary; chat/session memory cannot become canonical clinical state.
  Verify: Focused schema/migration tests; serialization round trip; old-state fixture load; cross-restart readback; `pytest` contract suite.

- [ ] **3. Implement the Living Twin projection**
  Source ref: Master Document sections 3, 4, 9, 17, and 24.
  What to build: Derive a patient-facing Twin projection with current state, organ/system objects, baseline, trajectory, deviation, confidence, provenance, active missions, Clinical Event Graph, anatomy changes, medication expectations, modifiability and healthspan domains. Keep it a projection of canonical state.
  Acceptance: One incoming event produces a new Twin version and a visible diff; a surgery persists in anatomy; a medication has expected/observed response and monitoring obligation; weak correlated signals remain explicitly uncertain; every displayed derived fact links to evidence.
  Verify: Unit tests for each projection; API readback; browser test comparing before/after versions; provenance deep-link test.

- [ ] **4. Unify the event-to-mission autonomous circuit**
  Source ref: Master Document sections 5, 6, 8, 18, and 25.4; `docs/AUTONOMOUS_CONTINUITY.md`.
  What to build: Route the promoted authorized event bundle through policy, canonical Twin update, signal correlation/alert-fatigue suppression, personal-baseline detector, Guardian Investigation, mission creation, bounded tool execution, human boundary, resume, receipt, and verification. Reuse remote-main autonomy/outbox/idempotency components.
  Acceptance: Duplicate events are idempotent; crash/retry resumes the same mission; no model call decides that a deterministic follow-up is due; unsupported actions remain blocked; completion requires evidence.
  Verify: Event redelivery test; crash-recovery test; safety/consent negative tests; `scripts/mainline_bp_continuity_proof.py`; Firestore before/after reread.

- [ ] **5. Build the judge-visible Live Agent Activity and Mission Replay**
  Source ref: Master Document sections 5.2, 9.3, 16.4, 22, and Appendix B.
  What to build: Add a patient-safe execution feed showing public events such as `event_received`, `policy_checked`, `twin_versioned`, `deviation_detected`, `mission_opened`, `tool_executed`, `human_boundary`, `receipt_recorded`, and `mission_verified`. Show agent/tool names, timestamps, inputs/outputs hashes, evidence IDs, and status without exposing chain-of-thought.
  Acceptance: The judge can reconstruct the mission from sanitized durable events; UI state survives reload; failures/retries are legible; no secret or hidden reasoning appears.
  Verify: API contract tests; privacy snapshot tests; browser reload/replay test; sanitized log scan; manual screen review at desktop/mobile widths.

- [ ] **6. Create the bounded Evaluation Session controller**
  Source ref: this plan > Evaluation activation design; Master Document sections 6 and 14.
  What to build: Implement explicit evaluation entry, isolated synthetic namespace, durable lease, scenario reset, expiry/exhaustion, per-session/global quotas, and automatic dormant return. Never infer judge identity from browser metadata.
  Acceptance: Unauthorized or expired entry cannot activate the session; reset cannot touch non-synthetic patients; global caps survive process restart; clinical gates remain identical inside/outside evaluation.
  Verify: Session forgery/expiry tests; namespace-isolation tests; quota restart test; destructive-route negative tests; audit event for every state transition.

- [ ] **7. Build the one-click Living System scenario**
  Source ref: Master Document section 21.1; this plan > Promoted story.
  What to build: Seed a reproducible synthetic Twin with organ/system summaries, persistent post-surgical anatomy, laboratory provenance, medication monitoring, obligations and prior missions. Provide a controlled judge action that injects the four-signal event bundle, opens one uncertain Guardian Investigation, and advances one clinically bounded continuity mission. Include visible breadth but only one promoted causal story.
  Acceptance: A fresh session shows the Twin before the event, the correlated change, the new Twin version, the investigation and mission in the expected order; the judge can pause, inspect evidence, resume at the human boundary, logout/login, and replay the same mission; reset is deterministic; no card is disconnected from canonical state.
  Verify: New `scripts/living_system_proof.py`; Playwright end-to-end; exact expected event sequence; two-patient isolation; zero browser console/page errors.

- [ ] **8. Make the cloud execution plane durable and exact-SHA bound**
  Source ref: `docs/AUTONOMOUS_CONTINUITY.md`; `docs/GOOGLE_HEALTH_CONSTELLATION.md`; current Cloud Run inventory.
  What to build: Deploy a candidate-bound web/evaluation service, private Eventarc/Pub/Sub workers, Firestore canonical state, private GCS evidence, Secret Manager references, and correlated Cloud Logging. Stamp source SHA, image digest, revision, and proof run in readiness/evidence APIs.
  Acceptance: Scale-to-zero restart does not lose the mission; duplicate delivery is safe; deployed SHA equals tested SHA; operational workers reject anonymous invocation; evidence survives a new revision.
  Verify: `gcloud run services describe`; IAM policy checks; `deployment/verify_cloud_revision_continuity.py`; correlated log query; exact GCS generation/SHA reread; anonymous-negative worker probes.

- [ ] **9. Add durable sleep/wake and spending protection**
  Source ref: `docs/COST_CONTROL.md`; evaluation state machine in this plan.
  What to build: Keep minimum instances at zero and evaluation max instances at one; replace process-only request protection with a durable Firestore budget ledger; cap model calls, output tokens, scenario resets, and evaluation leases; configure eligible Cloud spend caps/alerts and Artifact Registry retention without deleting deployed images.
  Acceptance: Dormant application sends zero model requests; scheduled Gmail/watch maintenance is separately accounted for and cannot activate the judge scenario; one evaluation cannot exceed its durable allowance even after restart; exhaustion fails closed; storage cleanup preserves all deployed digests and proof artifacts.
  Verify: Restart/concurrency quota tests; Cloud Run min/max inspection; Scheduler/Eventarc/Pub/Sub inventory; Vertex request-count proof; billing alert/cap screenshot or sanitized configuration receipt; dry-run retention report before any deletion.

- [ ] **10. Run clinical, security, privacy, accessibility, and regression gates**
  Source ref: Master Document sections 6, 14, 15, and 22; `docs/SECURITY_AND_SAFETY_MATRIX.md`.
  What to build: Add adversarial coverage for prompt/document injection, forged provenance, cross-patient access, consent revocation, unit errors, duplicate events, false closure, emergency language, inaccessible live updates, and cost abuse.
  Acceptance: Safety rules cannot be downgraded by Judge Mode or Gemini; real PHI is absent; live activity is screen-reader accessible; all focused and full suites pass from the candidate branch and release artifact.
  Verify: Focused security/clinical suites; full `pytest`; `python scripts/full_system_check.py`; `python scripts/dialogbench.py`; browser smoke; Android contract/build gates; release ZIP re-test; secret scan.

- [ ] **11. Promote one stable cloud link with independent live proof**
  Source ref: Master Document condition of victory; `JUDGES_START_HERE.md`; this plan > Victory condition.
  What to build: Deploy the exact green candidate, activate the bounded evaluation route, run the complete scenario from a clean external browser, capture provider/cloud receipts, and independently validate the public link. Preserve the prior candidate/video until this gate passes.
  Acceptance: The stable landing is anonymously reachable, while scenario activation requires the bounded evaluation capability; the full scenario works without developer intervention and completes within its quota; Cloud Logging/Firestore/GCS agree with the UI; exact SHA and revision match; sleeping resumes after expiry; no worker or secret is exposed.
  Verify: Independent clean-browser run with no developer Google session; `scripts/living_system_proof.py --cloud`; anonymous landing/health probe; authenticated evaluation proof; IAM negative probes against private workers; exact-SHA comparison; post-expiry dormant/cost probe; independent JUDGE review.

- [ ] **12. Align video, repository, Devpost, and future architecture**
  Source ref: Master Document sections 19-28; `docs/WINNING_ONE_TAKE.md`; hackathon submission requirements when read live from Devpost.
  What to build: Record a truthful continuous product video with Google Cloud Charon voice, update the architecture/evidence index and judge instructions, publish the exact verified artifact, and prepare the Devpost handoff. Publish a traceability ledger from every Master Document capability to `live`, `implemented-not-promoted`, `contract-only`, or `research-only`. Document expansion paths for Age & Biology, Modifiability, Minimum Effective Health Burden, Patient Future Simulator, ONE MEDS, ONE DE-MED, imaging/anatomy, N=1, ONE MATCH, ONE CAUSAL LAB, ONE DISCOVERY and ONE COLLECTIVE without presenting them as implemented.
  Acceptance: Video, public link, repository, source SHA, claims, and Devpost text tell the same story; anonymous download matches the published hash; every future capability is labeled roadmap; final JUDGE finds no unsupported claim.
  Verify: Full video visual/audio review; duration/rules check against live Devpost requirements; public URL and SHA-256 re-download; `python scripts/judge_omega.py --strict`; independent clinical/security/JUDGE verdicts.

## Required evidence package

No checklist item is promoted without an evidence record containing:

- candidate source SHA and dirty/clean state;
- test command and exit result;
- Cloud Run service/revision/image digest where applicable;
- sanitized trace/mission ID and patient namespace;
- Firestore reread and GCS provenance where applicable;
- model/tool request count and cost-guard state;
- human-boundary/consent receipt;
- independent reviewer verdict;
- explicit limitations.

## Required victory metrics

The release evidence must report, for the exact candidate SHA:

- event-to-investigation and event-to-mission latency;
- duplicate-event suppression and idempotent redelivery rate;
- missions closed without a valid receipt, whose required value is zero;
- unauthorized/cross-patient action success, whose required value is zero;
- consent-revocation enforcement and time to stop;
- restart recovery with the same Twin version, mission and budget lease;
- model calls, tokens, resets and estimated/spend-guard state per evaluation;
- false escalation/no-action outcomes for the deterministic synthetic fixture set;
- browser console/page/network errors;
- accessibility announcements for live state transitions;
- exact-SHA, revision, image digest and proof-artifact agreement.

## Manifest traceability deliverable

Before implementation can be called complete, `docs/MANIFEST_TRACEABILITY.md` must map every Master Document section and named capability to:

```text
concept
  -> commitment level (live | implemented-not-promoted | contract-only | research-only | prohibited)
  -> canonical entity/contract
  -> route or internal event
  -> deterministic test
  -> cloud/browser evidence
  -> clinical/scientific limitation
```

No item may be promoted in the product, repository, video or Devpost copy above the strongest evidence recorded in this ledger.

## Status vocabulary

- **IMPLEMENTED:** Code/configuration exists in the candidate branch.
- **TESTED:** Deterministic local/CI tests passed for the candidate.
- **VERIFIED:** The behavior was observed against the intended Cloud/browser/provider boundary and reread from durable state.
- **COMPLETE:** All applicable tests, live proof, documentation, submission alignment, and independent review passed for the same exact SHA.

## Scope held for the future

The architecture must preserve expansion seams, but the hackathon candidate will not claim these as complete unless separately proven:

- validated multi-domain biological-age models;
- autonomous diagnosis or treatment optimization;
- full DICOM/DICOMweb diagnostic interpretation;
- native Apple HealthKit production integration;
- population-level ONE COLLECTIVE research;
- causal treatment-effect claims;
- regulatory clearance or production clinical efficacy.

These are not vague placeholders. Gate 2 must define their interoperable data, consent, provenance, uncertainty and governance seams now, while runtime activation remains unavailable until separately validated. This prevents the hackathon candidate from becoming a dead-end prototype while keeping its claims truthful.

The post-hackathon future begins from the same foundations: versioned Twin, provenance, obligations, policy, typed tools, durable missions, verification, consent, and auditable learning.

## Final release gate

HealthIA ONE may be called the Living System candidate only when every checklist item is `COMPLETE` for one exact SHA and an independent JUDGE confirms:

1. the judge can see the system act rather than merely narrate;
2. the patient changes and the Twin changes with evidence;
3. autonomy advances without repeated prompting but stops at human authority;
4. mission closure is backed by durable verification;
5. the cloud link is stable, economical, private where required, and reproducible;
6. the demo is truthful, synthetic, safe, and aligned with the repository and submission.

