CURRENT OBJECTIVE
Promote Google Constellation Wave 2 without modifying the frozen Golden LIVE SHA `891745e1ab93dc78b9aa4e54d65b315befa885f2` or PR #37.

BASELINE
- Golden reference branch: `kira/golden-google-constellation-live-891745e1`.
- Golden mission core remains LIVE PASS: OAuth, Places, Gmail send/watch, Pub/Sub/history, FreeBusy, Calendar, Tasks, receipts, duplicate no-op, COMPLETED.
- PR #37 remains untouched by Wave 2 code.
- PR #39 is the only Wave 2 product branch and remains Draft. `main` remains untouched.

WAVE 2 ORDER
1. Scheduler renewal observability + natural provider run + duplicate/no-op proof. **LIVE PASS**
2. FCM controlled-device delivery with PHI-neutral lock-screen text. **ACTIVE**
3. Speech-to-Text using synthetic/private audio only.
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

FCM ACTIVE GATE
- Use only a controlled real device registration token.
- Notification title/body remain fixed PHI-neutral lock-screen copy; caller text cannot override it.
- Never write a device token to GitHub, logs, artifacts, patient-visible receipts, or command output.
- Require exact authorization and a real FCM provider message receipt before LIVE PASS.
- If no controlled device token is provisioned, report the human/device gate instead of fabricating delivery.

TRUTH RULE
`CODE PASS != LIVE PASS`.
Never expose credentials, OAuth material, cookies, patient IDs, device tokens or clinical content in proof artifacts.
