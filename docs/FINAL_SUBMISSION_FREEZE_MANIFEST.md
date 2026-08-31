# HealthIA ONE — Final Submission Freeze Manifest

Status: **JUDGE-FACING FREEZE**
Date: **2026-08-31**

This manifest exists to prevent accidental drift between the verified submission candidate and experimental/proof-only branches during the final judging window.

## Canonical judge entry points

- Official live product demo (~3:17): https://youtu.be/44LfVn9pPdU
- Public Judge Mode: https://healthia-one-judge-1038180719788.us-central1.run.app
- Judge start page: `JUDGES_START_HERE.md`
- Canonical Devpost package: `docs/DEVPOST_SUBMISSION.md`
- Architecture: `docs/ARCHITECTURE.md`
- ONE SAFETY proof: `hackathon/evidence/one_safety_final_proof.json`
- Bonus evidence index: `docs/HACKATHON_BONUS_POINTS.md`

## Freeze rule

Until judging/submission lock is safely past, `main` is the submission lineage. Do **not** merge experimental, proof-only, recorder-only, or unpromoted feature PRs merely because they are open or contain newer work.

In particular, open work explicitly marked experimental/proof-only/non-submission remains outside the canonical submission unless it independently satisfies the existing promotion rules and is deliberately promoted after review.

## Truth rules

- A newer branch is not automatically the submission candidate.
- CODE PASS is not LIVE PASS.
- Authorization is not execution evidence.
- Model prose is not connector execution evidence.
- Historical demos/proofs remain lineage, not the current judge entry point.
- External action claims require durable connector evidence/receipts.
- Clinical claims remain bounded to the synthetic prototype and do not establish efficacy, diagnosis, prescription authority, or regulated-device status.

## Allowed late edits

Only low-risk judge-facing maintenance should occur during the freeze:

1. reproducibility corrections;
2. evidence-integrity corrections;
3. synchronization of public judge-facing URLs/text;
4. typo/clarity fixes that do not change product behavior or inflate claims.

Runtime behavior, safety boundaries, infrastructure, credentials, patient-like data, and experimental capabilities should remain untouched unless an independently verified critical defect requires a deliberate recovery decision.

## Final pre-submit check

Before any final submission/update, confirm these exact items still agree:

- YouTube demo = `44LfVn9pPdU`;
- Judge Mode = `healthia-one-judge-1038180719788.us-central1.run.app`;
- Devpost text matches `docs/DEVPOST_SUBMISSION.md`;
- architecture upload corresponds to `docs/ARCHITECTURE.md`;
- public bonus article/social links match `docs/HACKATHON_BONUS_POINTS.md`;
- no experimental/proof-only PR has been merged into the submission lineage unintentionally.

If any item differs, treat it as submission drift and fix the judge-facing material before changing the verified runtime.