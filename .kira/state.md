CURRENT OBJECTIVE
Promote Google Constellation Wave 2 without modifying the frozen Golden LIVE SHA `891745e1ab93dc78b9aa4e54d65b315befa885f2` or PR #37.

BASELINE
- Golden reference branch: `kira/golden-google-constellation-live-891745e1`.
- Golden mission core remains LIVE PASS: OAuth, Places, Gmail send/watch, Pub/Sub/history, FreeBusy, Calendar, Tasks, receipts, duplicate no-op, COMPLETED.
- PR #37 remains untouched by Wave 2 code.
- PR #39 is the only Wave 2 product branch and remains Draft. `main` remains untouched.
- Truth rule remains strict: `CODE PASS != LIVE PASS`; Android compile PASS also does not imply an FCM-ready APK.

WAVE 2 ORDER
1. Scheduler renewal observability + natural provider run + duplicate/no-op proof. **LIVE PASS**
2. FCM controlled-device delivery with PHI-neutral lock-screen text. **BLOCKED_FIREBASE_CONFIG + BLOCKED_DEVICE**
3. Speech-to-Text using synthetic/private audio only. **BLOCKED_API_COST_GATE; LIVE harness prepared**
4. Document AI using synthetic/private GCS evidence. **BLOCKED_API_COST_GATE; private-GCS LIVE harness prepared**
5. Cloud Healthcare FHIR R4 create+reread plus DICOM metadata using synthetic resources only. **BLOCKED_API_COST_GATE; LIVE harness prepared**
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

FCM — PRODUCT CIRCUIT CLOSED, PROVIDER GATES STILL OPEN
- Backend registration API, Firestore registration store and Android Firebase Messaging plumbing are implemented.
- A prior defect was found: the Android bridge obtained FCM support in code but did not call `FirebaseRuntime.syncRegistration()` after pairing/startup and had no custom `FirebaseMessagingService` for token rotation/message reception. This is fixed and regression-tested.
- A second prior defect was found: historical APK builds compiled with empty `HEALTHIA_FIREBASE_*` values. Therefore the former artifact `HealthIA-Bridge-debug` from run `31399922787` is revoked as FCM-ready evidence and must not be used for the LIVE proof.
- The Android bridge now refreshes registration on startup and after pairing, handles `onNewToken`, accepts only the synthetic data-message contract `kind=healthia_update`, displays fixed PHI-neutral local notification copy, and sends a signed delivery ACK containing only the synthetic `proof_id`.
- The backend `/api/devices/fcm/ack` authenticates the same paired-device bearer and stores only the proof id/timestamp with the registration. Token refresh preserves an existing proof until a later proof replaces it.
- The FCM LIVE workflow sends exactly one PHI-neutral data message and does not promote FCM merely because the provider accepts it. LIVE PASS requires the matching ACK to be reread from the exact controlled-device Firestore registration.
- Current provider preflight: run `31412142220` SUCCESS; artifact `HealthIA-Wave2-FCM-LIVE`, id `9071998630`, digest `sha256:9da4f77d13d054ce4371f9946395427b30580d9b0e1c908a40511a74dd47f9dd`.
- Current Firestore truth remains 0 FCM registration documents, 0 active registrations and 0 valid registration hashes. The live send/ACK steps were skipped. Therefore FCM remains `BLOCKED_DEVICE`, not LIVE PASS.
- The Android build workflow now separates `Android CODE PASS` from `FCM-READY APK`. On PRs it always compiles product code, but if Firebase client configuration is absent it deletes the generated APK, uploads only readiness evidence and never publishes a misleading install artifact.
- Android compile/readiness run `31412142437` SUCCESS; readiness artifact `HealthIA-Android-APK-Readiness`, id `9072059305`, digest `sha256:8321ab51187b12cbde4d465b6f30c39cbde57e8074d79318d0b1183c93418cd3`.
- Android readiness provider truth: `status=BLOCKED_FIREBASE_CONFIG`, `fcm_ready=false`, `apk_publish_allowed=false`, `compile_allowed=true`, `config_source=NONE`. No FCM-ready APK was published.
- Preferred human configuration gate is ONE single-line GitHub Actions secret named `HEALTHIA_FIREBASE_ANDROID_CONFIG_B64`, containing Base64 of the official Firebase `google-services.json`. The workflow decodes it only inside the runner, requires exactly one Android client for package `com.healthia.one.bridge`, requires project id `healthia-6088a`, masks all derived values and never uploads the decoded JSON. Raw `HEALTHIA_FIREBASE_ANDROID_CONFIG_JSON` remains a backward-compatible fallback, followed by the four individual `HEALTHIA_FIREBASE_*` Actions secrets.
- Read-only Firebase-config discovery run `31412141346` SUCCESS; artifact `HealthIA-Firebase-Config-Readiness`, id `9071998497`, digest `sha256:dc2db080d5c591ab0d6bafd9a0bc7906f8b692538c928bc622a100fe18f11821`.
- That audit found no Firebase-like Secret Manager entries or Cloud Run environment names. Firebase Management app listing, API Keys metadata and Cloud Asset discovery are all denied to the current CI principal (HTTP 403). No secret value or API key string was read, no IAM mutation occurred and provider state was not changed. A 403 is not evidence that the Firebase Android app does or does not exist.
- FCM cannot become LIVE PASS until the protected Firebase Android config is supplied, the workflow produces an FCM-ready APK, a controlled Android installs/runs/pairs it against a backend carrying the new register+ACK endpoints, Firestore shows the real registration, and the single-message live proof receives the matching device ACK.

WAVE 2 PROVIDER HARNESSES — READY BUT COST-GATED
- Read-only API enablement audit run `31400393321` established: enabled `fcm.googleapis.com`, `firebase.googleapis.com`, `texttospeech.googleapis.com`, `aiplatform.googleapis.com`; disabled `speech.googleapis.com`, `documentai.googleapis.com`, `healthcare.googleapis.com`.
- Current provider preflight run `31412142276` SUCCESS; artifact `HealthIA-Wave2-Provider-Gates`, id `9071990568`, digest `sha256:956285c2e7fcbee8dda8226edfeac66c5a80df9d5e8aa45c212ddf8657b7ef55`.
- PR execution is read-only. LIVE requires the exact authorization gate before enabling/using Speech-to-Text, Document AI and Cloud Healthcare.
- STT LIVE harness uses locally generated synthetic/private audio and verifies recognition of a control phrase without writing the transcript into evidence.
- Document AI now has a mission-faithful private-GCS harness. Current preflight run `31412141906` SUCCESS; artifact `HealthIA-Wave2-DocumentAI-GCS`, id `9071990301`, digest `sha256:815ce680062b184aeae066962ecc9abc547927b5e9083d07ea1e09a41bedfd08`.
- Cloud Storage is already enabled. The Document AI LIVE path creates a temporary private bucket with public access prevention, uploads only a synthetic PDF, processes it by GCS URI and requests cleanup of the object, bucket and processor.
- Cloud Healthcare LIVE harness creates only ephemeral synthetic resources: dataset, FHIR R4 store/resource, DICOM store/instance, rereads FHIR + DICOM metadata and requests cleanup.
- No STT, Document AI or Healthcare LIVE calls were made; those APIs remain disabled because explicit cost authorization has not been provided.
- Veo remains separately blocked by its own explicit generation-cost gate even though Vertex AI is enabled.
- Canonical `.github/workflows/google-cloud-capability-audit.yml` remains restored to Golden blob `1c505b8292b3fea3b595971e6d9e7d29ea42ea0a`.

CURRENT VERIFICATION
- Functional Wave 2 head `3bdd8d56dcb7da68e171f07187dfc5fe289dfe04` passed HealthIA ONE verification run `31412142396` completely: pytest, Full System, DialogBench, Chromium, browser clinical E2E, LAB OMEGA Core/Secondary, compileall, smoke, JUDGE OMEGA, frontend gates, PowerShell, release build/verification and tests inside the extracted release.
- Later documentation-only checkpoint `ab4a70faf8383b4ed494bf7e01e6e50ccf75d555` also passed HealthIA ONE verification run `31412740751` completely through the same gates.
- Opportunity Autopilot run `31412141450`: SUCCESS; later documentation checkpoint Opportunity run `31412740374`: SUCCESS.
- Google Constellation provider preflight, Document AI/GCS preflight, FCM provider preflight and Firebase-config readiness all completed without claiming a false LIVE or FCM-ready result.

NEXT HUMAN GATES
- Firebase Android config: obtain the official `google-services.json` for Firebase Android package `com.healthia.one.bridge` in project `healthia-6088a` (register that Android app first if it is absent). Convert that local file to one-line Base64 and save only the encoded value as GitHub Actions secret `HEALTHIA_FIREBASE_ANDROID_CONFIG_B64`. Do not paste the JSON, Base64, or derived Firebase values into chat, logs, issues, PRs or artifacts.
- FCM after config: rerun `Android bridge compile + FCM-ready APK`; install the newly published APK on one controlled Android; pair it to a backend containing the current FCM register+ACK code; confirm Firestore registration; then run the controlled-device FCM LIVE proof with exact authorization `I_AUTHORIZE_CONTROLLED_FCM_PROOF`.
- STT/Document AI/Healthcare: explicit authorization is still required before enabling the currently-disabled billable APIs.
- Veo: separate explicit cost authorization remains mandatory before any live generation.

TRUTH RULE
`CODE PASS != LIVE PASS` and `Android CODE PASS != FCM-READY APK`.
Never expose credentials, OAuth material, cookies, patient IDs, device tokens, Firebase client config or clinical content in proof artifacts.