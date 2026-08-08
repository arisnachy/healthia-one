# HealthIA ONE — judge evidence index

This file is the judge-facing source of truth for what has actually been proven. It deliberately separates repository capabilities, live evidence and final-publication state. Failed or quota-blocked runs are never promoted as passes.

## Current status

- **Primary track:** The Taskmaster
- **JUDGE Ω evidence-backed score:** **99/100**
- **Current verdict:** `HIGH_SCORE_BUT_BLOCKED`
- **Technical/demo gates:** proven
- **Only remaining hard gate:** publish the already-proven judge video at the final stable judge-facing URL, place that URL in the Devpost package, then run final CI/JUDGE and merge/lock.

The score is computed from `hackathon/judge_omega_scorecard.json` by `scripts/judge_omega.py`. One Demo & Production Readiness point remains withheld until the video publication/submission URL itself exists.

## 1. Exact-candidate Cloud + unmocked browser proof — PASS

**GitHub Actions run:** `31262429792`  
**Exact candidate SHA:** `a28955c3641c37a9e5a06f5f0ccf943ccb197bbd`  
**Artifact:** `healthia-exact-candidate-cloud-proof` (`9023242539`)  
**Artifact digest:** `sha256:4760e89b6985fa81b532e4ed2fb094abcb8859f57c92259886c152d4632a55b6`

### Runtime identity

- Google Cloud project: `healthia-6088a`
- Region: `us-central1`
- Cloud Run service: `healthia-one-demo`
- URL: `https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app`
- Proven ready revision: `healthia-one-demo-00012-jvl`
- Container image: `us-central1-docker.pkg.dev/healthia-6088a/cloud-run-source-deploy/healthia-one-demo@sha256:1d88907ce97b96da2d9e6189a0ae766f5fc547f7a4c36fcb57acb1140f060518`
- Model: `gemini-3.5-flash`
- Transport: Vertex AI / ADC
- Canonical store: Firestore
- Original evidence store: private Google Cloud Storage
- Mocked: **false**

### Strict API proof

The deployed candidate proved:

- Cloud Run health/readiness;
- authenticated patient runtime and anonymous API rejection;
- two-patient state isolation;
- cross-patient document denial;
- logout/relogin state restoration;
- patient-scoped Firestore state;
- patient-scoped private GCS original evidence;
- a live Gemini Interactions call;
- a real Google ADK Runner tool trajectory;
- two memory-preserving dynamic five-question blocks;
- Gemini follow-up/orientation decision;
- restart-safe browser and device identities;
- Gemini multimodal PDF extraction;
- clinical-twin provenance;
- byte-for-byte original evidence round trip.

Observed clinical evidence included exactly five questions in block 1 and block 2, ADK execution of `interview` + `safety`, and final status `clinical_ai_orientation_completed`.

The strict proof persisted a multimodal result and original document into Firestore/GCS. Exact sanitized details are preserved in `hackathon/evidence/cloud_exact_candidate_proof.json`.

### Browser proof

The same run executed a real Chromium journey against the same Cloud service with **no mocks**.

Browser checks passed:

- secure registration/session;
- live Vertex runtime label;
- account settings UI;
- first live Gemini+ADK five-question block;
- second live memory-aware five-question block;
- live clinical orientation;
- multimodal PDF result with original provenance;
- completed Taskmaster result mission;
- logout and relogin continuity;
- Cloud readiness showing Vertex + ADK + Firestore + GCS;
- **zero browser console errors and zero page errors**.

The evidence artifact contains nine PNG screenshots plus a WebM recording. The browser recording SHA-256 is `4df3a3dced23875890d81a8cfb5b99ee083b308608def42be78cb02ef2515cb1`.

## 2. Cross-revision continuity proof — PASS

**GitHub Actions run:** `31262903731`  
**Frozen candidate SHA:** `e01aa35b912def31bb4e68b95cb236582090b476`  
**Artifact:** `healthia-cloud-revision-continuity-proof` (`9023298988`)  
**Artifact digest:** `sha256:4a30950483141ce55fa6f1256fa83998f0337a5e873576fa6f8598b111592263`

The proof prepared durable synthetic patient A/B state, then forced a genuinely new Cloud Run revision using only a harmless revision marker. The container image digest stayed unchanged.

- Before revision: `healthia-one-demo-00013-2bz`
- After revision: `healthia-one-demo-00014-ns8`
- Revision changed: **true**
- Same image across revision: **true**

After the new revision, the verifier independently proved:

- patient A could reauthenticate;
- patient A longitudinal marker persisted;
- multimodal result persisted;
- completed `result_explanation` Taskmaster mission persisted;
- clinical-twin result/document provenance persisted;
- the original GCS object path persisted;
- GCS generation was unchanged before/after;
- original SHA-256 bytes were unchanged;
- patient B identity persisted;
- patient B still could not see patient A result/document/mission;
- direct cross-patient original-document probing remained denied.

The sanitized evidence is preserved in `hackathon/evidence/cloud_revision_continuity_proof.json`. Temporary proof passwords/cookies/tokens were never uploaded.

## 3. Continuous final judge demo proof — PASS

**GitHub Actions run:** `31265639488`  
**Candidate SHA:** `3f99e511f6518e8dc9b45ebfd0cbdc37aaa9768e`  
**Artifact:** `HealthIA-ONE-final-judge-demo` (`9024139098`)  
**Artifact digest:** `sha256:71ee6e2ce665a9b98e44ca11aae7c7334849b73ac7e756b157afa47b3a249f33`  
**Video SHA-256:** `cfd91b0d08cf6659e1fb924c2e85071cd3b79bd414578b7112908c46f91adb19`  
**Recorded duration:** `290.16 s`  
**Synthetic data only:** true

The recorder reused the existing private Cloud Run deployment; it did **not** deploy a new revision. Its live runtime was:

- URL: `https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app`
- project/region: `healthia-6088a` / `us-central1`
- revision: `healthia-one-demo-00016-mct`
- model: Gemini 3.5 Flash
- Google ADK ready: true
- Firestore: true
- GCS evidence: true
- auth required: true

The continuous Playwright recording visibly covers the required judge story and passed these machine checks:

- problem overview visible;
- value proposition visible;
- live private Cloud runtime ready;
- live Gemini + ADK clinical block 1;
- live memory-aware clinical block 2;
- safe clinical orientation completed;
- multimodal PDF persisted with original evidence;
- Taskmaster result mission completed;
- logout/relogin continuity;
- `.run.app` URL + live readiness visible;
- zero browser console/page errors;
- duration gate 200–300 seconds.

The full sanitized proof record is `hackathon/evidence/final_judge_demo_proof.json`.

**Publication boundary:** the video file itself is now proven and preserved as a GitHub Actions artifact. It is not yet counted as the final submission URL until the exact file is published at the stable judge-facing link used by Devpost.

## 4. Deterministic verification — PASS

The candidate repeatedly passes the repository verification gate after the ADK latency/structured-output, multimodal and dependency-boundary fixes. The gate includes:

- pytest;
- 14 full-system workflows;
- Chromium E2E;
- Python compileall;
- smoke tests;
- JUDGE Ω validation;
- frontend semantic/syntax checks;
- PowerShell parsing;
- release ZIP build and verification;
- pytest again from the extracted release archive.

The runtime dependency boundary now uses `google-adk` core while declaring Firestore and GCS clients explicitly, avoiding the unused broad ADK GCP extras bundle. Tests lock that boundary.

Cloud proofs and the submission recording are explicit opt-in operations so ordinary CI does not silently spend model quota or create revisions.

## 5. Earlier live Taskmaster proof — PASS

**GitHub Actions run:** `31228561751`

This earlier one-request Vertex proof independently demonstrated a useful design property: after one Gemini 3.5 Flash multimodal request persisted the original/result/twin, HealthIA could retrieve the saved result and complete the result-explanation mission without spending a second model request merely to paraphrase the same evidence. It also demonstrated patient isolation and logout/login continuity.

## 6. Explicitly excluded evidence

**Run `31203021748` is not a passing proof.** Its live Google AI path ended in HTTP 429 because available credits/quota were depleted. It must not be cited as a successful Gemini/ADK run.

Failed Cloud proof iterations are also not counted as passes. They were used to diagnose and repair, in sequence, ADK latency, non-structured output, output truncation and multimodal PDF latency. Only green evidence is promoted here.

## 7. Cost/deployment safety hardening

Billable Cloud proofs and the live recording are explicit opt-in operations. Ordinary commits must not deploy Cloud or spend Gemini quota.

During the proof campaign, JUDGE identified a legacy `workflow_run` deployment path that could create a Cloud revision after an otherwise successful permission workflow. That automatic path was removed. The authoritative Cloud gates freeze an exact candidate SHA, and `.github/submission-demo-trigger.txt` was returned to `enabled=false` immediately after the passing recording.

## 8. What is still missing

The functional, architecture, Cloud, browser, cross-revision and video-content gates are green. The only remaining submission boundary is publication/locking:

1. publish the proven judge video at the final stable judge-facing URL;
2. place that exact URL in `docs/DEVPOST_SUBMISSION.md`;
3. run final CI + JUDGE on the exact submission head;
4. merge PR #29 and lock the submission only if everything remains green.

Until the stable video URL is in the final package, HealthIA should **not** claim `100/100` or `SUBMISSION_LOCKED`.
