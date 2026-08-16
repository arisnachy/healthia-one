# GOOGLE CONSTELLATION WAVE 2 LIVE

Golden baseline: `891745e1ab93dc78b9aa4e54d65b315befa885f2` on `kira/golden-google-constellation-live-891745e1` is immutable and PR #37 receives no Wave 2 features.

An ephemeral branch `kira/wave2-ci-execution-base` may contain only CI execution harness needed for Google provider proofs. It is not product code and must never be merged to `main`.

Victory order is strict:
1. Scheduler renewal observability + real forced run + retry/no-op evidence.
2. FCM delivery to one controlled HealthIA device using PHI-neutral notification content.
3. Speech-to-Text live recognition using synthetic/private audio only.
4. Document AI live processor using synthetic/private GCS evidence only.
5. Cloud Healthcare FHIR R4 create+reread and DICOM metadata using synthetic resources only.
6. Veo private educational generation only after explicit cost authorization, with no PHI/person generation and private GCS output.

Truth rule: `CODE PASS != LIVE PASS`. Each stage requires real provider resource IDs/receipts, least privilege, sanitized evidence and JUDGE verification before moving to the next stage.
