# HealthIA ONE — judge evidence index

This is the judge-facing source of truth for what HealthIA ONE has actually proven. Failed, quota-blocked or superseded experiments are never promoted as passes.

## Current status

- **Primary track:** The Taskmaster
- **Preserved submission JUDGE Ω evidence-backed score:** **100/100**
- **Integrated HealthIA Explain branch:** deterministic regression gate **PASS**
- **HealthIA Explain real Veo provider:** **LIVE PASS**
- **HealthIA Explain real Gemini TTS provider:** **LIVE PASS**
- **Replacement Devpost Cloud/video proof:** pending intentional recording/publication

The internal score is computed by `scripts/judge_omega.py` against the official 40/30/30 rubric. It is an internal evidence-backed assessment, not a guarantee of external judging outcome.

## 1. Integrated HealthIA Explain + multilingual + redesigned login — PASS

**GitHub Actions run:** `31767221658`  
**Branch head:** `0de5adad497b0a15defbedc1c0341394dc1680fd`  
**Branch:** `feature/patient-education-video-20260813`

This exact software head passed:

- complete pytest suite;
- Full System Verification;
- KIRA DialogBench multi-turn context gate;
- Chromium clinical end-to-end verification;
- LAB OMEGA core full-window laboratory;
- LAB OMEGA secondary/state-changing laboratory;
- compileall;
- smoke test;
- JUDGE OMEGA evidence review;
- semantic frontend validation;
- version-layer rejection gate;
- secure PowerShell parser gate;
- verified release archive build;
- verified release archive inspection;
- pytest again from the extracted release archive.

New behavior under this branch includes:

- the approved HealthIA ONE split-screen login;
- browser/OS-driven English/Spanish UI locale with persistent override;
- patient-message-first clinical/content language routing with bounded fallback;
- multilingual HealthIA Explain missions;
- Gemini TTS behind the existing patient/mission Google grant + receipt boundary;
- optional Veo visual generation that excludes patient-specific values and identifiers;
- long TTS narration chunking and deterministic WAV merge;
- no autonomous diagnosis/prescription/treatment change in the education-video path.

**Truth boundary:** this run is deterministic/local regression proof. It does not by itself claim that the new integrated head was deployed to Cloud Run or used in the public Devpost video. Those are separate proof layers and must be refreshed before replacing the preserved submission evidence.

## 2. HealthIA Explain real Vertex AI Veo 3.1 Fast — LIVE PASS

**Run:** `31758267226`  
**Model:** `veo-3.1-fast-generate-001`  
**Project:** `healthia-6088a`  
**Region:** `us-central1`

One explicitly authorized synthetic generation produced a real MP4:

- duration: 8 seconds;
- resolution: 720p;
- aspect ratio: 16:9;
- sample count: 1;
- person generation: disabled;
- no names, faces, medications, laboratory values, measurements or other patient data in the prompt;
- output downloaded and validated as a real-looking MP4;
- artifact preserved in GitHub Actions;
- temporary private GCS generation output removed after artifact capture.

This proves the optional visual provider is real, not a mocked interface. The production HealthIA Explain architecture still treats Veo as optional enrichment; controlled HealthIA cards carry exact patient-specific facts.

## 3. HealthIA Explain real Gemini 2.5 Pro TTS — LIVE PASS

**Run:** `31764094573`  
**Model:** `gemini-2.5-pro-tts`  
**Voice:** `Charon`  
**Locale:** `es-419`

One explicitly authorized synthetic narration used Google Cloud Text-to-Speech / Gemini TTS with natural-language voice direction for a warm, calm, adult clinical explanation.

The successful artifact demonstrated:

- real Google Cloud authentication;
- Text-to-Speech API availability;
- promptable Gemini TTS synthesis;
- natural clinical narration instead of the robotic local prototype fallback;
- synthetic content only.

The production branch now routes Gemini TTS through HealthIA's existing `text_to_speech.synthesize` Google action, mission-scoped grant and receipt boundary.

## 4. Preserved exact-candidate Cloud + unmocked browser proof — PASS

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

## 5. Preserved cross-revision continuity — PASS

**Run:** `31262903731`  
**Artifact:** `healthia-cloud-revision-continuity-proof` (`9023298988`)  
**Artifact digest:** `sha256:4a30950483141ce55fa6f1256fa83998f0337a5e873576fa6f8598b111592263`

- Before: `healthia-one-demo-00013-2bz`
- After: `healthia-one-demo-00014-ns8`
- Revision changed: **true**
- Container image stayed identical: **true**

After process replacement, patient A retained its longitudinal marker, multimodal result, original document, completed mission and clinical-twin provenance. The original GCS generation and SHA-256 stayed unchanged. Patient B remained isolated and direct cross-patient original-document access stayed denied.

Sanitized machine evidence: `hackathon/evidence/cloud_revision_continuity_proof.json`.

## 6. Preserved continuous judge demo — PASS

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

## 7. Preserved stable public judge video — PASS

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

## 8. Deterministic verification boundary — PASS

The repository release gate includes:

- pytest;
- full-system workflows;
- Chromium E2E;
- LAB OMEGA;
- Python compileall;
- smoke tests;
- JUDGE Ω validation;
- frontend semantic/syntax checks;
- PowerShell parsing;
- release ZIP build and verification;
- pytest again from the extracted release archive.

Cloud, media-generation, recording and publication mutation gates are explicit opt-in. Ordinary CI does not silently deploy Cloud or consume Veo quota.

## 9. Earlier one-request Vertex proof — PASS

Run `31228561751` independently demonstrated that after one Gemini 3.5 Flash multimodal request persisted original/result/twin evidence, HealthIA could retrieve it and complete the result-explanation mission without spending a second Gemini request merely to paraphrase the stored evidence.

## 10. Explicitly excluded evidence

Run `31203021748` ended in HTTP 429 due depleted quota/credits and is **not** counted as passing evidence. Failed development/provisioning iterations are likewise excluded from the winning evidence set.

Early local HealthIA Explain videos using an operating-system `espeak` voice were prototypes only and are **not** evidence of the production narration quality. The real Gemini TTS proof is run `31764094573`.

## 11. Replacement submission lock condition

The preserved submission evidence remains valid. The integrated branch should replace it only after this exact sequence:

1. freeze one final integrated SHA after documentation changes;
2. pass fresh exact-head CI/JUDGE on that SHA;
3. perform bounded Cloud deployment/proof on that same source state;
4. record the refreshed 3–4 minute judge demo showing the new login, multilingual behavior and HealthIA Explain;
5. publish and anonymously verify the replacement video bytes;
6. align README, `docs/DEVPOST_SUBMISSION.md`, `docs/ARCHITECTURE.md`, Devpost description and video URL to that canonical state;
7. only then replace the preserved Devpost references.

A 100/100 JUDGE score is an evidence-backed internal rubric result; it is **not a guarantee of winning the hackathon**.
