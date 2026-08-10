CURRENT OBJECTIVE
Promote the Google Constellation second wave from executable guarded connectors to provider-backed LIVE PASS without modifying the Golden PR #37 implementation.

GOLDEN BASELINE
- SHA `891745e1ab93dc78b9aa4e54d65b315befa885f2`.
- Frozen branch `kira/golden-google-constellation-live-891745e1`.
- PR #37 is LIVE PASS, mergeable and Ready for review; `main` remains untouched.

WAVE 2 ORDER
1. Scheduler renewal observability and forced-run proof.
2. FCM real controlled device delivery.
3. Speech-to-Text synthetic/private audio live proof.
4. Document AI synthetic/private evidence live proof.
5. Cloud Healthcare FHIR R4 create/reread + DICOM metadata proof with synthetic resources.
6. Veo private educational generation behind explicit cost authorization.

CURRENT CLOUD TRUTH FROM GOLDEN AUDIT
- Enabled: Cloud Scheduler, FCM, Vertex AI, TTS, Gmail, Calendar, Tasks, Places, Pub/Sub, Firestore, Secret Manager, Cloud Run.
- Not listed enabled: Speech-to-Text, Document AI, Cloud Healthcare.
- Dedicated Gmail worker, Pub/Sub topic/subscription and Scheduler service account exist.
- Scheduler list visibility was not proven by the CI audit identity.
- FCM connector is executable but has no real controlled device delivery receipt yet.

IN PROGRESS
- Build a provider-truth Scheduler verifier that distinguishes missing job, IAM visibility blocker, forced-run failure and successful idempotent renewal.

SECURITY
- No patient data for STT/Document AI/FHIR/Veo smoke proofs.
- No PHI in FCM notification surfaces.
- No broad IAM grants to make CI convenient.
- No secret/token/API-key values in repository, logs or receipts.
- `CODE PASS != LIVE PASS`.
