CURRENT OBJECTIVE
Turn the already-proven Google provider constellation into a judge-visible autonomous HealthIA product without modifying the frozen Golden LIVE SHA `891745e1ab93dc78b9aa4e54d65b315befa885f2`, PR #37, or `main`.

BASELINE
- Golden reference branch: `kira/golden-google-constellation-live-891745e1`.
- PR #39 is the active Wave 2/Wave 3 product branch and remains Draft until the replacement exact-head one-take + judge package are proven.
- Infrastructure is frozen for this phase: no provider shopping, no silent API enablement, no Veo.
- Truth rules remain strict: `CODE PASS != LIVE PASS`, `Android CODE PASS != FCM-READY APK`, provider acceptance is not end-user delivery, and model prose is not tool-execution evidence.

CURRENT PROVIDER TRUTH
1. Scheduler renewal / natural provider execution — **LIVE PASS**.
2. Firebase Management read — **LIVE PASS / HTTP 200** with permanent read-only `roles/firebasecloudmessaging.viewer`.
3. Firebase Android app `com.healthia.one.bridge` and real config retrieval — **LIVE PASS**.
4. Android bridge — **FCM-READY APK PASS**.
5. Dedicated zero-AI Cloud Run FCM proof backend — **LIVE infrastructure PASS**.
6. FCM controlled physical-device delivery — **LIVE PASS**.
7. Speech-to-Text synthetic/private recognition — **LIVE PASS**.
8. Document AI synthetic document from private GCS — **LIVE PASS**.
9. Cloud Healthcare synthetic FHIR R4 create+reread plus DICOM STOW+metadata reread — **LIVE PASS**.
10. Google Places/Gmail/Calendar/Tasks natural connector path — prior **LIVE evidence exists**; Wave 3 does not reclassify those receipts.
11. Veo private educational generation — **BLOCKED_EXPLICIT_COST_GATE**; not authorized or invoked.

PROVIDER EVIDENCE ANCHORS
- FCM controlled delivery: run `31452703408`; artifact `HealthIA-FCM-Propagated-LIVE-One-Shot`, id `9086896895`, digest `sha256:13b68a895cd8ddfcef936bfd1c15dfadff3369feabd9ce4e75dffa238823a9d2`.
- FCM durable reread: run `31452898769`; artifact `HealthIA-FCM-LIVE-Durable-Readback`, id `9086936050`, digest `sha256:85812dd3717f46eaedfd58d72bb6da07878fe226a1de42f1f82299c4a86d90c0`.
- STT corrected LIVE: run `31454604708`; artifact id `9087622807`, digest `sha256:9d411dc44c99fef06e60b3204fba42a85ad2efd96782aa343555f62abee9b904`.
- Document AI private GCS LIVE: run `31454733509`; artifact id `9087602986`, digest `sha256:1175038da4376a693fa8e5242aa0fd84780484b8f5b4a09738c9a8f4fcc3bb96`.
- Healthcare FHIR/DICOM LIVE: run `31454931773`; artifact id `9087702444`, digest `sha256:f94207be92a48bcf1f80b3ec512c143406df6519e83c40657581f9256ac9e1fa`.
- Earlier natural Google evidence includes a completed Places search with 8 candidates plus durable Gmail, Calendar and Tasks receipts; this evidence remains preserved in `.kira/evidence.md`.

WAVE 3 PRODUCT TRUTH
### Conversation Brain — CODE/JUDGE PASS
- Bounded recent conversational memory excludes hidden `[ENTREVISTA_CLINICA]` payloads.
- Explicit current topic/correction outranks stale context.
- Pronouns/ellipsis/ordinals can resolve only to evidence-backed recent context.
- An unanchored reference fails closed with one concise clarification instead of a guessed referent.
- Ordinary short commands are not misclassified merely because they contain few words.
- DialogBench now includes 120+ bilingual contextual scenarios plus fail-closed unknown-reference and active-Google-mission continuation gates.

### Autonomous Google mission — CODE/JUDGE PASS
- An active durable mission can resume from natural follow-ups such as `No, la segunda`, `Ese me sirve`, `The second one`, or `Go ahead with that`.
- ADK is instructed to continue all verifiable read-only/non-mutating steps until a real patient choice, exact authorization, missing-evidence, or external-event boundary.
- Actual ADK function calls are captured from ADK events; model JSON cannot fabricate the execution trace.
- Patient-visible `### Comprobante de misión` is derived from durable state + actual ADK event execution.

### Mission-scoped Google Places location consent — CODE/JUDGE PASS
- Google capability grants may now be mission-bound and expiring.
- A mission-bound `MAPS_LOCATION` grant cannot authorize a different mission and an expired grant is inactive.
- Existing account-level grants remain backward compatible.
- Navigation discovery stops before any Places connector call when the mission lacks location consent and stores durable boundary `maps_location_for_mission` with `external_action_performed=false`.
- Authenticated endpoint `/api/google-constellation/missions/{mission_id}/authorize-location` records consent only; it performs no search or external write.
- Conversation command `Autorizo ubicación para esta misión` / `I authorize my location for this mission` can record a 30-minute grant for the currently waiting mission; ADK may then continue safe read-only work.

VALIDATED WAVE 3 CHECKPOINTS
- Head `19d3460fc46da17ddcd807af50af69c72f64d9c1`: HealthIA ONE verification run `31496196801` — **SUCCESS** through pytest, Full System, Wave 3 DialogBench, Chromium, LAB OMEGA Core/Secondary, compileall, smoke, JUDGE OMEGA, frontend gates, PowerShell, release build/verify and tests inside release.
- Head `73e302c203fc97f03cf442e4ce7883e153d94263`: HealthIA ONE verification run `31498390839` — **SUCCESS** after mission-scoped location-consent hardening through the same gates.
- No Wave 3 Cloud recording or new provider LIVE promotion is claimed by those code gates.

WINNING ONE-TAKE STATUS
- `scripts/record_submission_demo.py` has been upgraded for the Wave 3 replacement target: unknown reference fail-closed → clinical Gemini/ADK → evidence-first result → evidence-backed pronoun resolution → Google navigation mission → visible pre-Places consent boundary → mission-only temporary consent → real Places discovery → natural `The second one` continuation → relogin continuity.
- The recorder now requires `HEALTHIA_CANDIDATE_SHA` and fails unless it is bound to one exact 40-character candidate.
- `.github/workflows/wave3-exact-head-one-take.yml` is manual-only and requires exact phrase `I_AUTHORIZE_WAVE3_EXACT_CLOUD_ONE_TAKE` plus an exact candidate SHA.
- That workflow runs local exact-head tests/JUDGE before Cloud spend, checks out/deploys the same exact SHA, records only the newly deployed revision, requires the Wave 3 checks, and uploads a private artifact.
- It does **not** publish a public release and does **not** replace the preserved judge video automatically.
- **CURRENT STATUS: PREPARED / NOT AUTHORIZED / NOT EXECUTED.** Therefore there is no Wave 3 one-take PASS yet.

PRESERVED SUBMISSION FALLBACK
- Existing evidence-backed Taskmaster candidate remains the fallback until Wave 3 proves itself.
- Existing public judge video remains valid/preserved and must not be replaced merely because Wave 3 code is green.
- `docs/WINNING_ONE_TAKE.md` and `docs/WAVE3_SUBMISSION_DELTA.md` define the replacement rule.

NEXT GATES
1. Let the exact head containing the Wave 3 recorder/workflow/tests complete CI/JUDGE.
2. If and only if that exact head is green, request the separate explicit authorization `I_AUTHORIZE_WAVE3_EXACT_CLOUD_ONE_TAKE` for bounded deployment/model/Places recording cost.
3. Execute the private exact-head one-take. A failure does not replace the old candidate/video.
4. If the private take passes, inspect video/evidence and only then prepare/publication gate + anonymous SHA verification.
5. Synchronize README, `docs/EVIDENCE.md`, `docs/DEVPOST_SUBMISSION.md`, architecture and PR #39 to the same exact candidate/video before submission lock.
6. Keep Veo outside the critical path unless separately authorized later.

TRUTH RULE
Never expose credentials, OAuth material, cookies, patient identifiers, raw device tokens, Firebase client config, raw proof IDs or real clinical content in public evidence. No provider is called LIVE merely to make a dashboard green, and no new Wave 3 PASS is promoted without exact-head evidence.
