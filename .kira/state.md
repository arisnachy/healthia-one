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
3. Speech-to-Text using synthetic/private audio only. **BLOCKED_API_COST_GATE**
4. Document AI using synthetic/private GCS evidence. **BLOCKED_API_COST_GATE**
5. Cloud Healthcare FHIR R4 create+reread plus DICOM metadata using synthetic resources only. **BLOCKED_API_COST_GATE**
6. Veo private educational generation. **BLOCKED_EXPLICIT_COST_GATE**

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
- Android bridge APK build run `31399922787` succeeded; artifact `HealthIA-Bridge-debug`, artifact id `9067302759`, digest `sha256:931a8e0fbbf5332e1022f7bd8e07444bcc03a86b2d0e04f6f8eafa802cf3ae51`.
- FCM cannot become LIVE PASS until a controlled Android device installs/runs the bridge, obtains a real Firebase registration token, and registers it through the paired-device endpoint. No token will be fabricated or written to GitHub/logs/artifacts.

WAVE 2 API COST GATES
- Read-only API enablement audit run `31400393321` succeeded; artifact `HealthIA-Wave2-API-Enablement`, artifact id `9067372235`, digest `sha256:7f78467d9197fdb965e5edfb53e53cd485813469fc42f04a2f4be2952d96c0a0`.
- Already enabled: `fcm.googleapis.com`, `firebase.googleapis.com`, `texttospeech.googleapis.com`, `aiplatform.googleapis.com`.
- Not enabled: `speech.googleapis.com`, `documentai.googleapis.com`, `healthcare.googleapis.com`.
- The audit performed no API-enable mutation, no IAM mutation and exposed no secret material.
- STT, Document AI and Healthcare remain blocked until explicit authorization to enable their APIs/billing surface. KIRA will not silently activate them.
- Veo remains separately blocked by the explicit generation-cost gate even though Vertex AI is enabled.
- Canonical `.github/workflows/google-cloud-capability-audit.yml` was restored to Golden blob `1c505b8292b3fea3b595971e6d9e7d29ea42ea0a` immediately after the probe.

CURRENT VERIFICATION
- HealthIA ONE verification run `31399922801`: GREEN through pytest, Full System, DialogBench, Chromium, LAB OMEGA Core/Secondary, compileall, smoke, JUDGE, frontend gates, PowerShell, release archive and tests inside extracted release.
- Opportunity Autopilot contract run `31399926115`: SUCCESS.

NEXT HUMAN GATES
- FCM: install/run the controlled Android APK and pair it so a real token is registered.
- STT/Document AI/Healthcare: explicit authorization is required before enabling the currently-disabled billable APIs.
- Veo: explicit cost authorization remains mandatory before any live generation.

TRUTH RULE
`CODE PASS != LIVE PASS`.
Never expose credentials, OAuth material, cookies, patient IDs, device tokens or clinical content in proof artifacts.
