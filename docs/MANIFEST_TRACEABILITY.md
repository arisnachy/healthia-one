# HealthIA ONE Master Document Traceability Ledger

## Purpose

This ledger prevents the repository, cloud demo, video, and Devpost submission from claiming more than the exact candidate proves. It maps the complete Master Document to an executable contract and an explicit commitment level.

Commitment levels:

- `LIVE`: must execute in the winning cloud scenario for the exact candidate SHA.
- `IMPLEMENTED_NOT_PROMOTED`: may exist and be tested but is not part of the primary judge claim.
- `CONTRACT_ONLY`: data, policy, provenance, consent, and extension seams exist; the capability is not active.
- `RESEARCH_ONLY`: requires separate research consent, governance, validation, and infrastructure.
- `PROHIBITED`: unavailable by product policy in the candidate.

No row advances level without code, tests, durable reread, and claim alignment for one exact SHA.

## Master Document section ledger

| Section / capability | Commitment | Canonical contract | Route or internal event | Required test/evidence | Truth boundary |
|---|---|---|---|---|---|
| 1. Mission and six objectives | LIVE + CONTRACT_ONLY | `ProductObjective`, mission policy | readiness/evidence metadata | architecture assertion + browser copy review | DETECT and individual LEARN are live; other objectives remain bounded domains |
| 1.2 SENSE-TWIN-REASON-PLAN-ACT-VERIFY-LEARN | LIVE | correlated event/mission IDs | public sanitized event sequence | full scenario sequence + durable reread | no hidden step may be inferred from prose |
| 2. Patient Digital Twin OS | LIVE | `PatientTwinVersion` | `GET twin` mapping | logout/login and restart reconstruction | chat is interface, never canonical memory |
| 2. Agent permanent | LIVE | durable mission/outbox/lease | Eventarc/Pub/Sub + worker events | scale-to-zero recovery and redelivery | event-driven; not permanent polling |
| 2. Prevention before diagnosis | CONTRACT_ONLY | preventive opportunity/review boundary | policy evaluation | negative clinical-directive tests | no autonomous diagnosis or treatment |
| 3. Twin layers | LIVE | identity, anatomy, physiology, clinical, medication, functional, risk, obligation, evidence | twin projection | schema, migration, serialization and browser projection | selected synthetic domains only |
| 3.2 Ingestion rule | LIVE | immutable source + normalized observation | `event_received`, `observation_normalized` | original hash/generation to derived fact | source quality and uncertainty remain visible |
| 3.3 Patient state versioning | LIVE | `version`, parent/source IDs, diff | `twin_versioned` | t0/t1 diff, Firestore reread, restart | no in-place silent overwrite |
| 4. Population/personal/trajectory normality | LIVE | baseline, trajectory, deviations, confidence | `baseline_compared`, `deviation_detected` | deterministic fixture and before/after browser proof | reference comparison is not diagnosis |
| 4.2 Age & Biology Engine | CONTRACT_ONLY | domain trajectory/model/version envelope | unavailable | contract validation only | no biological-age claim |
| 4.3 Modifiability Engine | CONTRACT_ONLY | modifiability class + evidence + uncertainty | unavailable | schema/policy tests | class does not dictate treatment |
| 4.4 Longevity/healthspan | CONTRACT_ONLY | healthspan domain objectives | unavailable | architecture/claim scan | no outcome prediction or efficacy claim |
| 4.5 Minimum Effective Health Burden | CONTRACT_ONLY | burden/review objective | professional review only | safety policy tests | net benefit and professional authority dominate medication reduction |
| 5. Specialized brains | LIVE + CONTRACT_ONLY | actor/tool registry | sanitized activity events | every promoted actor has receipt | only SENSE, TWIN, GUARDIAN, SAFETY, VERIFY promoted |
| 5.1 Persistent work queue | LIVE | NOW/NEXT/WATCH/WAITING/DONE mission states | mission state events | state transition, crash/retry, idempotency | no completion without receipt |
| 5.2 Mission format | LIVE | objective, evidence, allowed tools, autonomy, dependency, closure condition | mission API mapping | contract tests and Mission Replay | missing evidence remains pending |
| 6. A0-A5 autonomy | LIVE policy | per-action autonomy class | `policy_checked`, `human_boundary` | negative tests for each applicable gate | A4 and A5 unavailable |
| 6.2 Safety gates | LIVE | data/provenance/risk/permission/reversibility/human/post-action decisions | safety events | adversarial, consent and forged-source tests | Judge Evaluation never bypasses gates |
| 6.3 Emergencies | IMPLEMENTED_NOT_PROMOTED | urgent-language safety policy | deterministic urgent route | Spanish/English safety suite | not emergency service or guarantee |
| 7. Interoperability | CONTRACT_ONLY + LIVE device | observation/provenance mappings | Health Connect candidate route | identity, consent, unit and source round trip | FHIR/EHR/HealthKit not claimed live |
| 7.3 Provenance | LIVE | evidence reference, source, time, units, quality, transformation | evidence API | hash/generation reread | no derived fact without source |
| 8. Event/deviation/alert engine | LIVE | normalized observations and deviation policy | exact public event catalog | duplicate/noise/multi-signal fixtures | correlation is not causality |
| 8.2 Attention economy | LIVE | persistence, deduplication, suppression and actionability policy | `signals_correlated` or no-action receipt | noise and false-escalation fixture set | absence of useful action produces no mission |
| 9. Health command center | LIVE | patient-safe Twin projection | evaluation UI | desktop/mobile/browser/a11y test | no empty chatbot-first experience |
| 9.2 ONE COMMAND | LIVE bounded | consent + mission permissions | explicit evaluation/session action | authorization and revocation tests | not unlimited autonomy |
| 9.3 Explainability | LIVE | what/why/uncertainty/next/evidence projection | Mission Replay | privacy snapshot and reload | no chain-of-thought |
| 10. Professional experience | LIVE selected | `ClinicalReviewPack` | clinician-safe projection | role/access and data-minimization tests | draft context; qualified review required |
| 11.1 MEDS monitoring | LIVE selected | `MedicationExposure`, expectation, observation, monitoring obligation | medication projection/event mapping | synthetic response/monitoring fixture | no autonomous medication agent |
| 11.2 ONE DE-MED | CONTRACT_ONLY | professional review opportunity | unavailable | prohibition/policy tests | never start, stop, reduce or substitute medication |
| 11.3 Prevention before pharmacotherapy | CONTRACT_ONLY | low-risk hypothesis/review envelope | unavailable | safety and guideline-provenance contract | never delay indicated treatment |
| 12. N=1 Lab | CONTRACT_ONLY | question, baseline, intervention, outcome, confounders, stop rule | unavailable | schema and consent tests | no individual causal claim |
| 13. ONE COLLECTIVE | RESEARCH_ONLY | separated research consent/domain | unavailable | isolation design and negative access tests | care use is not research consent |
| 13.3 ONE MATCH | RESEARCH_ONLY | cohort eligibility/similarity/index-time contract | unavailable | future statistical validation | no superficial or live patient matching |
| 13.4 ONE CAUSAL LAB | RESEARCH_ONLY | target-trial protocol and sensitivity metadata | unavailable | future independent scientific validation | correlation never equals causality |
| 13.5 ONE DISCOVERY | RESEARCH_ONLY | signal-replicate-causal-analysis-external-validation-prospective pipeline | unavailable | future governance/replication proof | hypothesis, never clinical truth |
| 14. Privacy/consent/governance | LIVE + CONTRACT_ONLY | identity separation, consent ledger, action log, research boundary | session/policy/audit events | cross-patient, revocation, secret/PHI scans | synthetic judge namespace only |
| 15. Risk/regulatory validation | LIVE policy | action risk class, harm, fallback, owner, authorization | evidence metadata | clinical/security/JUDGE review | no clearance or production-efficacy claim |
| 16. Technical architecture | LIVE selected | canonical store, Event Bus, orchestrator, verifier, audit | Cloud Run/Eventarc/Pub/Sub/Firestore/GCS | exact-SHA cloud proof | future stores/platforms remain seams |
| 16.2 Storage | LIVE selected | Firestore state/time series + GCS originals/evidence | private provider APIs | restart, generation/hash, IAM tests | no vector memory as clinical truth |
| 16.3 Source of truth | LIVE | structured versioned Twin | canonical read APIs | cross-session reconstruction | LLM context is derived and disposable |
| 16.4 Typed tools | LIVE | purpose, input, permission, reversibility, risk, timeout, idempotency, receipt | bounded tool events | contract and negative authorization tests | no generic omnipotent tool |
| 17. Minimum Twin schema | LIVE selected | entities named in candidate contract | mapped current APIs/events | migration and compatibility suite | no second competing model |
| 18.1 New laboratory | LIVE preloaded/selected | observation + source + trend + obligation | lab ingestion/projection mapping | synthetic lab source-to-Twin proof | supported analytes only |
| 18.2 New medication | LIVE preloaded/selected | medication exposure and monitoring obligation | medication event mapping | expected-versus-observed fixture | professional review for any change |
| 18.3 Wearable change | LIVE | source quality, personal baseline, correlated signals | evaluation event bundle | four-signal deterministic scenario | uncertainty remains explicit |
| 18.4 Hospital event | IMPLEMENTED_NOT_PROMOTED or CONTRACT_ONLY | event graph + anatomy/medication/obligations | fixture mapping | synthetic post-event obligation test | not promoted without full receipt path |
| 19. Core construction phases | LIVE core + future seams | this ledger and victory plan | N/A | gate-by-gate evidence | no time-based completion claim |
| 20. Build priorities | LIVE governance | dependency-gated checklist | N/A | clean worktree and exact-SHA evidence | preserve user work |
| 21. True Twin acceptance | LIVE | combined candidate contracts | cloud proof script + browser | every applicable acceptance assertion | one flow deep, not all medicine shallow |
| 22. Product success metrics | LIVE | latency, continuity, detection, burden, reliability, trust, quality | evidence report | exact-SHA metric artifact | internal score is not a guarantee of winning |
| 23. Development/governance | LIVE process | ownership, clinical/scientific/security review | KIRA state/decisions/evidence | independent reviews | JUDGE separate from implementation |
| 24. North Star daily behavior | LIVE selected | persistent Twin + proactive bounded mission | one-click judge scenario | clean-browser external reproduction | scenario is synthetic and labeled |
| 25. Core v0.1 | LIVE | TWIN + GUARDIAN + LABS + MEDS + DEVICE + MISSIONS + VERIFY | mapped APIs/events | exact sequence and durable rereads | MEDS is monitoring, not treatment action |
| 26. Technical sources | CONTRACT_ONLY | versioned source registry | unavailable/public evidence metadata | source version/applicability review | sources do not prove capability |
| 27. Architectural decisions | LIVE governance | non-breaking invariants | tests and release checks | strict JUDGE/claim scan | any contradiction blocks release |
| 28. North Star final | LIVE selected + future vision | one lifelong canonical architecture | judge story + roadmap | same-SHA alignment across cloud/video/repo | long-term vision is not current evidence |

## Exact winning scenario trace

```text
authorized synthetic device bundle
  -> event_received
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

The cloud, video, repository, and Devpost submission must all demonstrate or describe this same sequence and the same source SHA.

