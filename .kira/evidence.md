# Evidence

- OAuth connection: `arisnachy@gmail.com`, connected; required Gmail, Calendar and Tasks scopes returned by authenticated capabilities API; secret material flag false.
- Places receipt `receipt_bf32a911bd534456`: action `maps.search_nearby`, 8 candidates, completed.
- Gmail send receipt `receipt_5bdf03dcaa934b10`: real resource/thread `19fe97a94c04f91b`, exact authorization, completed.
- Gmail watch receipts `receipt_fcd0f71e2f1941d5` and `receipt_66943a3df944489d`: real numeric history IDs and expiration metadata.
- Real reply source message `19fe987dbe8fa89b` reached `gmail.appointment_offered` through private Pub/Sub worker and `users.history.list`; watch cursor advanced to `3632787` at that transition.
- Calendar FreeBusy receipt `receipt_2c488d8769a64ed7`, completed.
- Calendar receipt `receipt_ba0e47b8bfcf42d0`: event `e3ftjtt6si8lar1s72o4arjd9180hjjn3cg15ltp36erh97dfcjg`, authorization `gauth_505f9d5831164e4f`, reread in Google Calendar.
- Tasks receipt `receipt_92df4b3787924018`: task `VlFzdkcyZW9DeTZ1c3Q3dQ`, authorization `gauth_651069603e6e4282`, reread in Google Tasks.
- Duplicate Pub/Sub publish id `20956743188977617`; worker returned success/no-op and mission remained completed with one Calendar id, one Task id, one terminal event and five mission receipts.
- Full local suite before Wave 2: 400/400 PASS. Focused Gmail/mega-loop/deployment/OAuth contracts also pass.
- Security cleanup: an untracked 143-byte OAuth JSON artifact created by a legacy stdin bug was detected by shape only, never printed, and permanently deleted; current importer uses direct SDK stdin. No credential/API-key/auth-code patterns remain in the repository scan.
- Scheduler PREP LIVE: real Gmail watch force-renewal succeeded before the natural run; logging-enabled worker revision `healthia-gmail-worker-00014-pvs` served 100% traffic.
- Scheduler natural provider execution: Cloud Scheduler emitted 2 lifecycle events and the private worker returned HTTP 200 at `2026-08-10T05:00:00.993008Z` on revision `healthia-gmail-worker-00014-pvs`.
- Scheduler durable receipt proof: completed `gmail.watch` receipt(s) exist in the PREP window, while the natural 05:00 Scheduler window contains exactly 0 `gmail.watch` receipts. Therefore the scheduled execution was a real no-op and did not call Gmail watch renewal again.
- Final Scheduler proof artifact: GitHub Actions run `31384610740`, artifact `HealthIA-Wave2-Scheduler-LIVE`, artifact digest `sha256:c16a4c6ec7f329685aaf48a23e773451cccab73ac2cb54952b66ff369eb9ea30`; `status=LIVE_PASS`, `scheduler_noop_proven=true`, `iam_mutation=false`, `secret_material_exposed=false`.
- Scheduler proof caveat preserved explicitly: the pre-fix worker did not emit the aggregate response payload into Cloud Logging because its logger had no Cloud Run handler. Provider execution, HTTP 200, and the no-op are independently proven by Cloud Scheduler/Cloud Run logs plus durable action receipts. The current worker logger is bound to `uvicorn.error` and has a regression test.

## Wave 2 FCM evidence correction

- Historical FCM readiness run `31399804527` correctly established 0 registration documents, 0 active registrations and 0 registration hashes, but the historical APK artifact from run `31399922787` is no longer valid as FCM-ready evidence.
- Root cause 1 found and fixed: the Android activity did not invoke `FirebaseRuntime.syncRegistration()` after pairing/startup and there was no custom `FirebaseMessagingService` to handle token rotation and data-message receipt.
- Root cause 2 found and fixed: the historical Android workflow compiled with empty `HEALTHIA_FIREBASE_APP_ID`, `HEALTHIA_FIREBASE_API_KEY`, `HEALTHIA_FIREBASE_PROJECT_ID` and `HEALTHIA_FIREBASE_SENDER_ID`. Compile SUCCESS therefore did not prove Firebase initialization capability.
- The old `HealthIA-Bridge-debug` artifact from run `31399922787`, artifact id `9067302759`, digest `sha256:931a8e0fbbf5332e1022f7bd8e07444bcc03a86b2d0e04f6f8eafa802cf3ae51`, is explicitly **REVOKED AS FCM-READY EVIDENCE**. It must not be installed for the provider proof.
- Current Android code adds `POST_NOTIFICATIONS`, registers `HealthiaFirebaseMessagingService`, refreshes FCM registration on startup and after pairing, re-registers `onNewToken`, accepts only `kind=healthia_update`, displays fixed local PHI-neutral copy, and signs a delivery ACK back to `/api/devices/fcm/ack`.
- Backend FCM ACK persistence records only `proof_id` + timestamp with the paired registration; token refresh preserves existing delivery proof. New tests lock these contracts.
- Current FCM provider preflight run `31412142220` SUCCESS; artifact `HealthIA-Wave2-FCM-LIVE`, artifact id `9071998630`, digest `sha256:9da4f77d13d054ce4371f9946395427b30580d9b0e1c908a40511a74dd47f9dd`.
- Current FCM provider truth remains `BLOCKED_DEVICE`: 0 registration documents, 0 active registrations and 0 valid registration hashes. The workflow performed no provider write in preflight; controlled send/ACK steps were skipped.
- FCM live proof is now end-to-end: exactly one PHI-neutral data-only FCM message is sent; provider acceptance alone is insufficient; `LIVE_PASS` requires the exact synthetic `proof_id` to be ACKed by the controlled Android and reread from the same Firestore registration.

## Android Firebase build truth

- Android workflow now separates `CODE PASS` from `FCM-READY APK` and never publishes an APK when the Firebase client configuration is absent.
- Android compile/readiness run `31412142437` SUCCESS. `Compile Android debug application` passed, but FCM BuildConfig verification, APK rename and APK upload were skipped because Firebase config was absent. The temporary non-FCM-ready APK was deleted from the runner.
- Android readiness artifact `HealthIA-Android-APK-Readiness`, id `9072059305`, digest `sha256:8321ab51187b12cbde4d465b6f30c39cbde57e8074d79318d0b1183c93418cd3` records `status=BLOCKED_FIREBASE_CONFIG`, `fcm_ready=false`, `apk_publish_allowed=false`, `compile_allowed=true`, `config_source=NONE`, `secret_material_exposed=false`.
- Preferred configuration path is one single-line protected Actions secret `HEALTHIA_FIREBASE_ANDROID_CONFIG_B64` containing Base64 of the official Firebase `google-services.json`. The workflow decodes the content only in the runner, requires exactly one Android client for `com.healthia.one.bridge`, requires project id `healthia-6088a`, extracts/masks client values and never uploads the decoded source JSON.
- Raw `HEALTHIA_FIREBASE_ANDROID_CONFIG_JSON` remains a backward-compatible one-secret fallback. Four individual `HEALTHIA_FIREBASE_*` Actions secrets remain the final fallback. Base64 has first priority.
- Read-only Firebase config discovery run `31412141346` SUCCESS; artifact `HealthIA-Firebase-Config-Readiness`, id `9071998497`, digest `sha256:dc2db080d5c591ab0d6bafd9a0bc7906f8b692538c928bc622a100fe18f11821`.
- Firebase-config audit provider truth: project number readable; Secret Manager metadata list readable but 0 Firebase-like secret names and 0 exact HealthIA Firebase secret names; Cloud Run has none of the exact Firebase env names; Firebase Management Android-app list returned 403; API Keys metadata list returned 403; Cloud Asset FirebaseAppInfo search returned 403. No API key string or secret value was read, no IAM mutation occurred and no provider write occurred.
- The 403s are permission limits only and are not used to assert that the Firebase Android app exists or is absent.

## STT / Document AI / Healthcare prepared gates

- Read-only Wave 2 API enablement audit run `31400393321` SUCCESS; artifact `HealthIA-Wave2-API-Enablement`, artifact id `9067372235`, digest `sha256:7f78467d9197fdb965e5edfb53e53cd485813469fc42f04a2f4be2952d96c0a0`.
- API provider truth remains: `fcm.googleapis.com=true`, `firebase.googleapis.com=true`, `texttospeech.googleapis.com=true`, `aiplatform.googleapis.com=true`; `speech.googleapis.com=false`, `documentai.googleapis.com=false`, `healthcare.googleapis.com=false`.
- Current fail-closed Wave 2 provider preflight run `31412142276` SUCCESS; artifact `HealthIA-Wave2-Provider-Gates`, id `9071990568`, digest `sha256:956285c2e7fcbee8dda8226edfeac66c5a80df9d5e8aa45c212ddf8657b7ef55`. PR execution was read-only; no API enablement/provider write/IAM mutation occurred.
- The provider harness has executable synthetic/private STT recognition and ephemeral synthetic Healthcare FHIR R4 + DICOM create/reread/cleanup paths, but they remain gated behind explicit live cost authorization.
- Document AI mission mismatch was corrected: private inline processing is not used as the final mission proof. A dedicated private-GCS proof workflow now requires a temporary private bucket, public access prevention, synthetic PDF input by GCS URI, sanitized evidence and cleanup requests.
- Current Document AI/GCS preflight run `31412141906` SUCCESS; artifact `HealthIA-Wave2-DocumentAI-GCS`, id `9071990301`, digest `sha256:815ce680062b184aeae066962ecc9abc547927b5e9083d07ea1e09a41bedfd08`. Storage is already enabled; Document AI remains disabled and no bucket/processor was created in preflight.
- STT, Document AI and Healthcare remain `BLOCKED_API_COST_GATE`; none were enabled and no LIVE provider call was made.
- Veo remains `BLOCKED_EXPLICIT_COST_GATE`; no Veo generation was run.

## Current verification

- Functional Wave 2 head `3bdd8d56dcb7da68e171f07187dfc5fe289dfe04` passed HealthIA ONE verification run `31412142396` completely: pytest, Full System, DialogBench, Chromium, browser clinical E2E, LAB OMEGA Core/Secondary, compileall, smoke, JUDGE OMEGA, frontend gates, PowerShell, release build/verification and pytest inside the extracted release.
- Documentation-only checkpoint `ab4a70faf8383b4ed494bf7e01e6e50ccf75d555` also passed HealthIA ONE verification run `31412740751` completely through the same gates; Opportunity Autopilot run `31412740374` succeeded.
- Canonical Google Health Constellation live-proof jobs are skipped on Wave 2 PR heads rather than manufacturing a provider PASS.
- `.github/workflows/google-cloud-capability-audit.yml` remains restored to Golden blob `1c505b8292b3fea3b595971e6d9e7d29ea42ea0a`.
- Current security invariant: no credentials, OAuth material, raw FCM device tokens, Firebase client JSON/Base64, patient IDs, clinical content or key strings are permitted in proof artifacts.