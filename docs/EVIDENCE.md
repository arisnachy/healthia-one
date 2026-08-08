# HealthIA ONE — judge evidence index

This file is the judge-facing source of truth for what has actually been proven. It deliberately separates repository capabilities from live evidence and does not count failed or quota-blocked runs as passes.

## Current status

- **Primary track:** The Taskmaster
- **JUDGE Ω evidence-backed score:** **98/100**
- **Current verdict:** `HIGH_SCORE_BUT_BLOCKED`
- **Only remaining hard gate:** final approximately four-minute unedited submission video + final Devpost package

The score is computed from `hackathon/judge_omega_scorecard.json` by `scripts/judge_omega.py`. The final two Demo & Production Readiness points remain withheld until the real submission video/package exists.

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

The strict proof persisted a multimodal result and original document into Firestore/GCS. The exact sanitized details are preserved in `hackathon/evidence/cloud_exact_candidate_proof.json`.

### Browser proof

The same run then executed a real Chromium journey against the same Cloud service with **no mocks**.

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

## 3. Deterministic verification — PASS

The candidate has repeatedly passed the repository verification gate after the ADK latency/structured-output and multimodal fixes. The gate includes:

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

The Cloud proof is intentionally separated from ordinary CI so normal regression work does not silently spend model quota or create revisions.

## 4. Earlier live Taskmaster proof — PASS

**GitHub Actions run:** `31228561751`

This earlier one-request Vertex proof independently demonstrated a useful design property: after one Gemini 3.5 Flash multimodal request persisted the original/result/twin, HealthIA could retrieve the saved result and complete the result-explanation mission without spending a second model request merely to paraphrase the same evidence. It also demonstrated patient isolation and logout/login continuity.

## 5. Explicitly excluded evidence

**Run `31203021748` is not a passing proof.** Its live Google AI path ended in HTTP 429 because the available credits/quota were depleted. It must not be cited as a successful Gemini/ADK run.

Failed Cloud proof iterations are also not counted as passes. They were used to diagnose and repair, in sequence, ADK latency, non-structured output, output truncation and multimodal PDF latency. Only the green exact-candidate runs above are promoted as judge evidence.

## 6. Cost/deployment safety hardening

Billable Cloud proofs are explicit opt-in operations. Ordinary commits must not deploy Cloud or spend Gemini quota.

During the proof campaign, JUDGE identified a legacy `workflow_run` deployment path that could create a Cloud revision after an otherwise successful permission workflow. That automatic path was removed from `main`; the legacy workflow is now manual-only. The authoritative proof gates require explicit trigger files and freeze an exact candidate SHA before Cloud work.

## 7. What is still missing

The technical hard gates are green. The remaining submission work is presentation evidence:

1. record the approximately four-minute **unedited** judge demo using the proven Cloud flow;
2. publish/upload that final video;
3. replace the video placeholder in `docs/DEVPOST_SUBMISSION.md`;
4. run final CI + JUDGE on the exact submission head;
5. merge/lock the candidate only after those steps.

Until that video/package exists, HealthIA should **not** claim `100/100` or `SUBMISSION_LOCKED`.
