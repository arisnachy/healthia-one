CURRENT OBJECTIVE
Promote Google Constellation Wave 2 without modifying the frozen Golden LIVE SHA `891745e1ab93dc78b9aa4e54d65b315befa885f2` or PR #37.

BASELINE
- Golden reference branch: `kira/golden-google-constellation-live-891745e1`.
- Golden mission core remains LIVE PASS: OAuth, Places, Gmail send/watch, Pub/Sub/history, FreeBusy, Calendar, Tasks, receipts, duplicate no-op, COMPLETED.
- PR #37 is Ready for review and must not receive Wave 2 code.
- Ephemeral CI execution base `kira/wave2-ci-execution-base` exists only so GitHub can execute Wave 2 Cloud proof jobs from a base-branch workflow. It is not a product promotion branch and must never be merged to main.

WAVE 2 ORDER
1. Scheduler renewal observability + forced provider run + duplicate/no-op proof.
2. FCM controlled-device delivery with PHI-neutral lock-screen text.
3. Speech-to-Text using synthetic/private audio only.
4. Document AI using synthetic/private GCS evidence.
5. Cloud Healthcare FHIR R4 create+reread plus DICOM metadata using synthetic resources only.
6. Veo private educational generation only after explicit cost authorization.

CURRENT CHECKPOINT
- Scheduler runtime hardening is CODE PASS.
- Scheduler uses `X-CloudScheduler-ScheduleTime` as the stable retry window when available.
- Scheduler response exposes aggregate counts only, not patient identifiers.
- `scripts/verify_gmail_scheduler_live.py` can describe the exact job, force one controlled watch due, execute the real job twice and require a future expiration plus second-run no-op.
- Full verification for the Scheduler checkpoint passed pytest, Full System, DialogBench, Chromium, LAB Omega, JUDGE, release and extracted-release tests.
- Next gate is provider-truth Scheduler LIVE proof through the execution-base workflow. No FCM promotion until Scheduler is LIVE PASS.

TRUTH RULE
`CODE PASS != LIVE PASS`.
Never expose credentials, tokens, device tokens, cookies, patient IDs or clinical content in proof artifacts.
