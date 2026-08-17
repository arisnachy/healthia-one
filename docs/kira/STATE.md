# KIRA State

## Objective
Build HealthIA ONE Core v0.1 as the first functional vertical slice of the complete Patient Digital Twin OS manifesto, deploy it economically to Google Cloud, and prove the exact candidate through one judge-visible Living System journey.

## Current checkpoint
- Final native candidate checkpoint: `origin/main` `fa560a9ece334d62c38e8d17c784f1566aaea287` contains the Living System inside the authenticated primary HealthIA shell. The native view projects the patient-scoped Twin, persisted evidence, active missions, autonomous receipts and human-review decisions from `/api/bootstrap`; it does not use evaluator credentials or synthetic evaluator state.
- PRs `#75` and `#76` passed remote CI. Local full regression passed, `scripts/full_system_check.py` passed `14/14`, visual browser verification showed the native Spanish surface without console errors, and the adaptive interview contract was hardened so answer options remain factual rather than imperative while deterministic medication and diagnosis guards remain fail-closed.
- Exact provider binding passed for Cloud Run revision `healthia-one-demo-00038-tm4`, release `fa560a9ece334d62c38e8d17c784f1566aaea287`, Cloud Build `12f557a9-c6d9-4a38-98e7-a0dfb07aaa11` and Artifact Registry digest `sha256:1175d839ecb42cec60f705078f92031b236bc7c12ae36ed33f9e42a83a33363b`.
- The strict main-service proof now passes live Gemini 3.5, ADK execution, two adaptive memory-preserving blocks, multimodal PDF, authenticated A/B isolation, Firestore/GCS provider rereads, device identity, original-evidence roundtrip and Living System `14/14`, Twin `v3`, exact main revision, persisted human receipt and zero Living model calls.
- Final video workflow run `32030016758` passed CUTLOCK against that exact source revision: real English product capture, no static screenshots, native Living surface visible, Google Cloud Charon male without fallback, `235s`, `1600x900`, and MP4 SHA-256 `4c4a09121cdf650e93f705357c347d943aa5bca36bec9cdaa61ebc913b3c0f57`. YouTube and Devpost remain intentionally unchanged until owner preview approval.
- Original checkout at `bd1ce0614be330142ed2f49a87979423e91ba192` remains untouched with user-owned modifications.
- Clean worktree `healthia-one-living-system` and branch `codex/living-system-core` start at fetched `origin/main` `ec233508497a982a3f026b4bad9895e748e15ea6`.
- `docs/HEALTHIA_ONE_LIVING_SYSTEM_CLOUD_VICTORY_PLAN.md` defines the 12 evidence gates.
- `docs/MANIFEST_TRACEABILITY.md` maps the complete Master Document to live, implemented-not-promoted, contract-only, research-only, and prohibited commitments.
- Gate 1 repository reconciliation and candidate documentation are committed at `c10b623`.
- Gate 2 contract slice is committed: additive versioned Twin fields, organ/system and anatomy state, medication monitoring expectations, baselines, trajectories, deviations, obligations, non-causal Clinical Event Graph edges, a closed sanitized event catalog, idempotent version advancement, and enriched Twin projection.
- Gates 3–5 local candidate are implemented: an access-key protected, physically separate `patient_eval_living` state; durable per-release session/run budget; real persistence of a four-signal Health Connect-shaped fixture; exact 14-event runtime; Twin versioning; governed mission; explicit human boundary; persisted synthetic receipt; and a dedicated `/living` UI.
- Runtime and API tests prove expiry, global budget persistence, release binding, patient rejection, demo/evaluator data isolation, idempotence, exact event order, JSON restart replay, fail-closed configuration, capability rejection, zero model calls, and completion only from persisted evidence.
- Playwright completed the full browser flow at `http://127.0.0.1:8765/living`: 10/14 at the human boundary, 14/14 after evidence, Twin v1→v2→v3, and zero console errors. The access key is not browser-persisted; re-entry rereads the durable server replay. Screenshot: `output/playwright/living-system-isolated-complete.png`.
- Exact-SHA cloud deployment and provider reread passed twice during hardening. The latest pre-integration proof bound clean SHA `3644fed65ff64007e9ae7eaba0ef394fc417b891` to Cloud Build `51637721-3675-443e-95cf-bcd24e58cbb2`, revision `healthia-one-demo-00031-ttc`, Artifact Registry digest `sha256:a4e7e23097d360632f5f92d3b479a7c88e8023c56a758e9b740c7dd3d4f44781`, and 379 provider files compared byte-for-byte.
- The strict live proof passed authenticated A/B isolation, anonymous rejection, Gemini 3.5 + ADK, multimodal PDF, Firestore/GCS rereads, device identity, and Living System 14/14, Twin v3, persisted receipt and zero model calls.
- Vigia security review passed after proof credentials were moved to temporary environment variables with guaranteed `finally` cleanup.
- The earlier independent JUDGE classified the pre-integration core as `CONDITIONAL_PASS`; a new independent final JUDGE is required after native integration and exact-head cloud/video evidence.
- Generated cloud JSON remains outside Git to avoid post-deployment-attestation SHA recursion. Sanitized copies must be published with the final release and tied to the exact candidate SHA.

## Victory gate
- Exact candidate SHA passes focused, regression, clinical, security, accessibility, and cost tests.
- A clean external browser sees the authorized event update the versioned Twin, open and advance the durable mission, stop at human authority, record a receipt, verify closure, and preserve state across relogin/restart.
- Cloud Run revision, image digest, Firestore/GCS evidence, public UI, video, repository and Devpost claims agree on the same SHA.
- Dormant operation sends zero model requests; durable quotas protect the evaluation budget.
- Independent clinical/security reviewers and JUDGE pass before the Living System is called complete.
