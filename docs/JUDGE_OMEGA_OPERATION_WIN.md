# KIRA Ω — OPERATION WIN · Judge Matrix

## Objective

Do not win by feature count. Win by making one claim impossible to miss and easy to verify:

> **HealthIA ONE turns fragmented patient evidence into a durable health mission that can reason, act with Google tools, stop at the correct human boundary, resume deterministically, and preserve the outcome across sessions.**

This document is submission strategy only. It does not alter the preserved Wave 3 product proof.

## Official scoring target

| Criterion | Weight | HealthIA target | What the judge must visibly understand |
|---|---:|---:|---|
| Innovation & Operational Utility | 40 | 39–40 | HealthIA removes continuity work instead of only answering questions. It continues a multi-step mission with minimal hand-holding. |
| Architectural Discipline & Tech Stack | 30 | 29–30 | Real ADK + Gemini 3.5 + Cloud Run + Firestore/GCS; patient-scoped state; secret isolation; fail-closed behavior; bounded AI spend; durable state. |
| Demo & Production Readiness | 30 | 29–30 | One continuous live journey, visible Google Cloud runtime, exact-source evidence, no mocks in the proof, reproducible repo, architecture, preserved artifacts. |

**Internal target: 97–100/100 evidence-backed.** This is an internal target, not a prediction of external judging.

## The single judge story

The demo should feel like one continuous job, not a tour of features:

1. A patient describes a clinical problem in natural language.
2. Google ADK + Gemini generates adaptive questions from the authorized longitudinal context.
3. The patient supplies a clinical document/image; HealthIA persists the original first and produces a structured explanation linked to the clinical twin.
4. A later reference to prior evidence is resolved from durable state; unsupported ambiguity fails closed.
5. When the mission needs location, HealthIA stops at the human consent boundary instead of silently using location.
6. Explicit mission-scoped consent resumes the same durable mission and performs real Google Places discovery.
7. The patient says **“The second one.”** HealthIA deterministically selects the exact second verified candidate without spending another Gemini interpretation round.
8. Logout/login proves the mission and selected state survived.
9. Cloud Run readiness and the exact `.run.app` runtime are visible.

The judge takeaway should be: **“This agent does real continuity work, knows when not to act, and can prove what it did.”**

## Wave 3 evidence anchor

Winning application source:

`b5254a54fa9ae50edf29fc09964fbd8957625b12`

Private one-take:

- workflow run `31533575382` — SUCCESS
- job `93919195798` — SUCCESS
- recorder revision `healthia-one-demo-00027-z88`
- same deployed product image as source revision — verified
- request limit `20`
- LLM timeout `60 s`
- Maps key — Secret Manager reference, plaintext absent
- continuous journey — `285.34 s` recorder report (`285.52 s` ffprobe verification)
- video SHA-256 `64a40e17d2cd10d3341db20209a8dec6337c1f9591b6348a9e3cd5135fbb99c2`
- artifact `9118046695`
- artifact digest `sha256:d59095439a47e4b724681453079bcde22d170f62cc2720cd07d9922982ac9f7a`

### Fifteen checks visible in the Wave 3 recorder report

1. `english_os_locale_login`
2. `live_cloud_runtime_ready`
3. `wave3_unanchored_reference_fails_closed`
4. `live_english_gemini_adk_question_block_1`
5. `live_english_gemini_adk_question_block_2`
6. `live_english_clinical_orientation_completed`
7. `multimodal_result_persisted_with_original`
8. `english_taskmaster_result_mission_completed`
9. `wave3_evidence_backed_reference_resolution`
10. `wave3_places_stops_before_mission_location_consent`
11. `wave3_mission_scoped_location_consent_then_real_places`
12. `wave3_ordinal_resumes_and_selects_durable_mission`
13. `relogin_continuity_including_google_mission`
14. `visible_exact_candidate_run_app_and_live_readiness`
15. `zero_browser_console_or_page_errors`

## Claim → evidence matrix

| Judge-facing claim | Proof |
|---|---|
| Real Gemini 3.5 on Google Cloud | Vertex/ADC runtime in exact Cloud proof and continuous demos |
| Real Google ADK execution | live adaptive clinical blocks and audited tool trajectory |
| Not just chat | durable result mission + Google mission state advances across multiple turns |
| Real external discovery | mission-scoped consent followed by real Google Places results |
| Human boundary respected | Places explicitly stops before location consent |
| Ambiguity handled safely | unanchored reference fails closed |
| Human choice applied exactly | ordinal selection resumes durable mission and persists exact candidate |
| Durable memory/state | relogin continuity including Google mission; prior cross-revision Firestore/GCS proof |
| Original clinical evidence preserved | multimodal result persisted with original bytes before interpretation |
| Patient isolation | exact Cloud proof includes two-patient separation |
| Production-minded secrets | Maps through Secret Manager; plaintext key absent; service identities used |
| Cost bounded | RequestLimit=20 in Wave 3; min/max bounded proof deployment; explicit opt-in billable workflows |
| Reproducible | README spin-up, full CI, Chromium, release verification, evidence index |
| Live, not mocked | exact Cloud Run browser journey and continuous recorder |

## Four-minute final demo target

The preserved 285-second Wave 3 proof is valid technical evidence. The public submission video should be optimized for judging comprehension and target approximately four minutes.

### 0:00–0:20 — Problem + promise

“Healthcare starts over too often. HealthIA ONE turns scattered evidence into a durable patient-owned mission that continues until there is an evidence-backed outcome or a real human boundary.”

Show the patient UI immediately; no long title animation.

### 0:20–1:05 — Adaptive clinical intelligence

- Natural-language complaint.
- Show Gemini + ADK adaptive questions.
- Answer enough to show the next block changes with context.
- Briefly expose live readiness/Cloud marker, not a terminal lecture.

### 1:05–1:45 — Evidence-first multimodal result

- Upload synthetic PDF/image.
- Show original persisted plus structured explanation.
- Open the linked longitudinal/twin state.
- Make the “original first, interpretation second” boundary visually obvious.

### 1:45–3:15 — The winning autonomous mission

- Refer to prior evidence naturally.
- Show evidence-backed reference resolution.
- Request care/resource discovery.
- Demonstrate HealthIA stopping before location consent.
- Grant mission-scoped consent.
- Show real Places candidates.
- Say: **“The second one.”**
- Show exact durable selection with no external write.

### 3:15–3:40 — Persistence

- Logout/login.
- Show the same mission/candidate/evidence still present.

### 3:40–4:00 — Cloud + close

Show `.run.app` / live readiness / Google stack in one compact frame.

Closing line:

> **“HealthIA does not just answer a patient. It carries the continuity task, proves what it did, and stops exactly where a human must decide.”**

## What must NOT enter the final demo

- a feature parade;
- internal KIRA/FORJA names as the product value proposition;
- raw secret values, tokens, patient identifiers or real clinical data;
- claims of diagnosis, prescribing, medical-device validation or regulatory approval;
- long CI/log screens before the user value is clear;
- speculative bonus integrations that weaken the proven core;
- calling a skipped provider replay a failure;
- replacing the preserved proof unless the replacement has its own exact-source gate.

## Competitive moat

Many agent demos prove that an LLM can call a tool. HealthIA should prove a harder sequence:

**understand → persist evidence → fail closed when ambiguous → wait at consent → resume the same mission → call a real provider → apply exact human choice → persist across login → expose proof.**

That sequence is the center of OPERATION WIN.
