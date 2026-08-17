# HealthIA ONE — judge evidence index

This is the judge-facing source of truth for what HealthIA ONE has actually proven. Failed, quota-blocked or superseded experiments are never promoted as passes.

## Current Living System candidate

The judge-facing runtime is `https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app/living`.
It is a public UI backed by an isolated synthetic evaluator namespace; mutation
requires the private evaluation capability and never grants access to patient
records.

The authoritative identity for the current submission is not a hand-edited SHA
in this document. It is the machine-readable evidence published after the build:

- `deployment/cloud-provider-binding-latest.json` proves clean HEAD to provider
  source archive, Cloud Build, Artifact Registry digest and Cloud Run revision;
- `deployment/cloud-proof-latest.json` proves the authenticated product,
  Firestore/GCS rereads and the exact 14-event Living System replay;
- release `healthia-one-autonomous-winner-demo-2026` publishes the exact-head
  Charon video and its anonymous byte-identity proof.

The generated cloud files are intentionally not committed: committing a
post-deployment attestation would itself create a different HEAD. The final
release publishes sanitized copies as immutable assets associated with the
candidate SHA. All three artifacts must name the same candidate, or a merge
commit whose tree is byte-identical and preserves that candidate in `main`.

The most recent pre-integration cloud validation proved exactly 14 events,
Twin v3, a persisted human-evidence receipt, isolated `patient_eval_living`
state and zero model calls. Evidence below is historical lineage and is not the
identity of the current Living System candidate.

## Historical submission status

- **Primary track:** The Taskmaster
- **JUDGE Ω evidence-backed score:** **100/100**
- **Verdict when the exact submission head is green:** `SUBMISSION_LOCKED`
- **All hard gates:** proven
- **Public judge video:** published and independently verified without credentials

The score is computed from `hackathon/judge_omega_scorecard.json` by `scripts/judge_omega.py` against the official 40/30/30 rubric.

## 1. Historical exact-candidate Cloud + unmocked browser proof — PASS

**Run:** `31262429792`  
**Candidate SHA:** `a28955c3641c37a9e5a06f5f0ccf943ccb197bbd`  
**Artifact:** `healthia-exact-candidate-cloud-proof` (`9023242539`)  
**Artifact digest:** `sha256:4760e89b6985fa81b532e4ed2fb094abcb8859f57c92259886c152d4632a55b6`  
**Cloud Run revision:** `healthia-one-demo-00012-jvl`  
**Cloud URL:** `https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app`

Proven on the deployed runtime:

- Gemini 3.5 Flash through Vertex AI / ADC;
- real Google ADK Runner tool execution;
- two memory-preserving five-question clinical blocks;
- authenticated patient runtime and anonymous API rejection;
- two-patient state isolation and cross-patient document denial;
- patient-scoped Firestore canonical state;
- private GCS original clinical evidence;
- Gemini multimodal PDF extraction;
- clinical-twin provenance;
- completed Taskmaster result mission;
- logout/relogin restoration;
- byte-for-byte original-evidence round trip;
- zero browser console errors and zero page errors.

Sanitized machine evidence: `hackathon/evidence/cloud_exact_candidate_proof.json`.

## 2. Cross-revision continuity — PASS

**Run:** `31262903731`  
**Artifact:** `healthia-cloud-revision-continuity-proof` (`9023298988`)  
**Artifact digest:** `sha256:4a30950483141ce55fa6f1256fa83998f0337a5e873576fa6f8598b111592263`

- Before: `healthia-one-demo-00013-2bz`
- After: `healthia-one-demo-00014-ns8`
- Revision changed: **true**
- Container image stayed identical: **true**

After process replacement, patient A retained its longitudinal marker, multimodal result, original document, completed mission and clinical-twin provenance. The original GCS generation and SHA-256 stayed unchanged. Patient B remained isolated and direct cross-patient original-document access stayed denied.

Sanitized machine evidence: `hackathon/evidence/cloud_revision_continuity_proof.json`.

## 3. Historical continuous judge demo — PASS

**Run:** `31265639488`  
**Candidate SHA:** `3f99e511f6518e8dc9b45ebfd0cbdc37aaa9768e`  
**Artifact:** `HealthIA-ONE-final-judge-demo` (`9024139098`)  
**Artifact digest:** `sha256:71ee6e2ce665a9b98e44ca11aae7c7334849b73ac7e756b157afa47b3a249f33`  
**Video SHA-256:** `cfd91b0d08cf6659e1fb924c2e85071cd3b79bd414578b7112908c46f91adb19`  
**Duration:** `290.16 s`  
**Synthetic data only:** true  
**Cloud revision shown:** `healthia-one-demo-00016-mct`

The continuous Playwright recording visibly covers problem → value proposition → live Gemini + ADK interview → multimodal result/original evidence → clinical twin → completed Taskmaster mission → logout/relogin continuity → `.run.app` and live Gemini/ADK/Firestore/GCS readiness. It passed with zero browser console/page errors.

Sanitized machine evidence: `hackathon/evidence/final_judge_demo_proof.json`.

## 4. Historical stable public judge video — PASS

**Direct public video URL:**  
`https://github.com/arisnachy/healthia-one/releases/download/healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm`

**Release page:**  
`https://github.com/arisnachy/healthia-one/releases/tag/healthia-one-hackathon-judge-demo-2026`

### Publication proof

**Run:** `31267268584`  
**Proof artifact:** `HealthIA-ONE-GitHub-release-video-proof` (`9024528554`)  
**Digest:** `sha256:281703f31d7a5a42bd28fdce18f455cfe46b91263304e1e9b8c2fbfbf62cb7d5`

The workflow recovered artifact `9024139098`, revalidated the original WebM SHA, created/updated the GitHub Release, downloaded the Release asset without credentials, and matched the exact same SHA-256.

### Independent anonymous probe

**Run:** `31267268597`  
**Probe artifact:** `HealthIA-ONE-public-video-probe` (`9024526089`)  
**Digest:** `sha256:ff151da75a8809b4ac493b909f526dd484ef7c6e9248e4c7b11bb0e0569d06d7`

A separate no-credential workflow downloaded the full public URL and independently matched the exact video SHA.

Permanent machine evidence: `hackathon/evidence/public_judge_video_proof.json`.

**Security boundary:** the public submission video is a GitHub Release asset. The patient clinical-evidence GCS bucket remains private and is not reused for public submission media.

## 5. Deterministic verification — PASS

The release gate includes:

- pytest;
- 14 full-system workflows;
- Chromium E2E;
- Python compileall;
- smoke tests;
- JUDGE Ω validation;
- frontend semantic/syntax checks;
- PowerShell parsing;
- release ZIP build and verification;
- pytest again from the extracted release archive;
- independent public judge-video probe.

The runtime installs Google ADK core while Firestore/GCS clients are declared explicitly, avoiding the broad unused ADK GCP extras bundle. Tests lock that dependency boundary.

Cloud, recording and publication mutation gates are explicit opt-in and are returned to `enabled=false` after controlled use.

## 6. Earlier one-request Vertex proof — PASS

Run `31228561751` independently demonstrated that after one Gemini 3.5 Flash multimodal request persisted original/result/twin evidence, HealthIA could retrieve it and complete the result-explanation mission without spending a second Gemini request merely to paraphrase the stored evidence.

## 7. Explicitly excluded evidence

Run `31203021748` ended in HTTP 429 due depleted quota/credits and is **not** counted as passing evidence. Failed development/provisioning iterations are likewise excluded from the winning evidence set.

## 8. Final lock condition

All rubric hard gates are now proven. The remaining step is operational rather than evidentiary:

1. let the **exact final branch HEAD** finish CI + JUDGE + public-video probe with all mutation triggers disabled;
2. PR #29 was merged as `a1525ec` after its candidate head stayed green;
3. rerun the exact-head gate for any later change before replacing the preserved submission candidate;
4. use `docs/DEVPOST_SUBMISSION.md`, the architecture diagram, repository and verified public video URL in Devpost.

A 100/100 JUDGE score is an evidence-backed internal rubric result; it is **not a guarantee of winning the hackathon**.
