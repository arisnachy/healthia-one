CURRENT OBJECTIVE
Promote Google Constellation Wave 2 without modifying the frozen Golden LIVE SHA `891745e1ab93dc78b9aa4e54d65b315befa885f2` or PR #37.

BASELINE
- Golden reference branch: `kira/golden-google-constellation-live-891745e1`.
- Golden mission core remains LIVE PASS: OAuth, Places, Gmail send/watch, Pub/Sub/history, FreeBusy, Calendar, Tasks, receipts, duplicate no-op, COMPLETED.
- PR #37 remains untouched by Wave 2 code.
- PR #39 is the only Wave 2 product branch and remains Draft. `main` remains untouched.

WAVE 2 ORDER
1. Scheduler renewal observability + natural provider run + duplicate/no-op proof. **LIVE PASS**
2. FCM controlled-device delivery with PHI-neutral lock-screen text. **BLOCKED_DEVICE**
3. Speech-to-Text using synthetic/private audio only. **ACTIVE**
4. Document AI using synthetic/private GCS evidence.
5. Cloud Healthcare FHIR R4 create+reread plus DICOM metadata using synthetic resources only.
6. Veo private educational generation only after explicit cost authorization.

SCHEDULER CLOSED
- PREP real Gmail watch renewal succeeded and left a future-expiring watch.
- Natural Cloud Scheduler execution occurred at `2026-08-10T05:00:00.993008Z` on private worker revision `healthia-gmail-worker-00014-pvs` with HTTP 200.
- Cloud Scheduler emitted 2 lifecycle events in the expected window.
- Durable action receipt audit found completed `gmail.watch` receipt(s) in the PREP window and exactly 0 `gmail.watch` receipts during the natural Scheduler window, proving the 05:00 execution was a real no-op.
- Final sanitized artifact: GitHub Actions run `31384610740`, `HealthIA-Wave2-Scheduler-LIVE`, digest `sha256:c16a4c6ec7f329685aaf48a23e773451cccab73ac2cb54952b66ff369eb9ea30`.
- No IAM policy was broadened or mutated for the proof; no secret material was exposed.
- Direct aggregate response payload was not captured on the pre-fix revision because its custom logger lacked a Cloud Run handler. The current worker uses `uvicorn.error` and the logging contract is regression-tested. This limitation is recorded rather than hidden.
- The one-shot Scheduler proof workflow was removed; `.github/workflows/google-cloud-live-proof.yml` is restored byte-for-byte to Golden blob `b6210596839a75cecb3ebf46428b7d87fe90eb1d`.

FCM DEVICE GATE
- Backend registration API, Firestore registration store and Android Firebase Messaging client plumbing are implemented.
- Notification title/body remain fixed PHI-neutral lock-screen copy; caller text cannot override it.
- Read-only Firestore provider audit run `31399804527` succeeded with artifact `HealthIA-Wave2-FCM-Device-Readiness`, artifact id `9067133415`, digest `sha256:16ae32623e19e7528e9e0b87fbd8ce4c06c4ea781f2f91efb3e0d06157abb6c6`.
- Provider truth: 0 FCM registration documents, 0 active FCM registrations, 0 registration hashes. No raw device secret, IAM mutation or secret material was emitted.
- Firebase Management listing returned 403 for the GitHub audit principal; this is an audit-IAM limitation and is not used as evidence that Firebase itself is absent.
- FCM cannot become LIVE PASS until a controlled Android device obtains a real Firebase registration token and registers it through the paired-device endpoint. No token will be fabricated or written to GitHub/logs/artifacts.

STT ACTIVE GATE
- First determine whether `speech.googleapis.com` is already enabled using read-only Cloud state.
- If disabled, stop at `BLOCKED_API_COST_GATE`; do not enable a billable API silently.
- If enabled, use synthetic/private audio only, private GCS input, no patient speech, sanitized provider receipt and cleanup of temporary evidence.

CURRENT VERIFICATION
- HealthIA ONE verification run `31399922801`: GREEN through pytest, Full System, DialogBench, Chromium, LAB OMEGA Core/Secondary, compileall, smoke, JUDGE, frontend gates, PowerShell, release archive and tests inside extracted release.
- Opportunity Autopilot contract run `31399926115`: SUCCESS.

TRUTH RULE
`CODE PASS != LIVE PASS`.
Never expose credentials, OAuth material, cookies, patient IDs, device tokens or clinical content in proof artifacts.
