CURRENT OBJECTIVE
Promote Google Constellation Wave 2 without modifying the frozen Golden LIVE SHA `891745e1ab93dc78b9aa4e54d65b315befa885f2` or PR #37, then convert the verified provider constellation into a reproducible one-take autonomous HealthIA hackathon demo.

BASELINE
- Golden reference branch: `kira/golden-google-constellation-live-891745e1`.
- PR #37, Golden and `main` remain untouched by Wave 2.
- PR #39 is the Wave 2 product branch and remains Draft until the final integration/demo gate is closed.
- Truth rules remain strict: `CODE PASS != LIVE PASS`, `Android CODE PASS != FCM-READY APK`, and provider acceptance alone is not equivalent to end-user delivery.

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
10. Veo private educational generation — **BLOCKED_EXPLICIT_COST_GATE**; no Veo generation has been authorized.

FCM LIVE EVIDENCE
- Exactly one physical Android registration was used.
- Exactly one actual PHI-neutral FCM data message was provider-accepted.
- The controlled Android produced a matching durable ACK with `notification_shown=true`.
- A later independent Firestore reread confirmed the durable proof state.
- LIVE run: `31452703408`, artifact `HealthIA-FCM-Propagated-LIVE-One-Shot`, id `9086896895`, digest `sha256:13b68a895cd8ddfcef936bfd1c15dfadff3369feabd9ce4e75dffa238823a9d2`.
- Durable readback run: `31452898769`, artifact `HealthIA-FCM-LIVE-Durable-Readback`, id `9086936050`, digest `sha256:85812dd3717f46eaedfd58d72bb6da07878fe226a1de42f1f82299c4a86d90c0`.
- Temporary FCM send role was removed after proof.

STT LIVE EVIDENCE
- The original synthetic `espeak-ng` control audio reached Speech-to-Text but did not meet the control-word truth threshold, so it was correctly refused as PASS.
- The corrected proof normalized synthetic audio to mono PCM LINEAR16 at 16 kHz, used slower repeated numeric controls and accepted word/digit representations of the same control concepts.
- Provider returned HTTP 200 and all three independent numeric control concepts were recognized.
- Raw transcript was not written into evidence; only a SHA-256 plus control-hit count was retained.
- Corrected proof run: `31454604708`; artifact `HealthIA-STT-DocumentAI-Healthcare-Corrected-LIVE`, id `9087622807`, digest `sha256:9d411dc44c99fef06e60b3204fba42a85ad2efd96782aa343555f62abee9b904`.

DOCUMENT AI LIVE EVIDENCE
- Mission-faithful proof used a temporary private GCS bucket with public access prevention and a synthetic PDF only.
- A temporary OCR processor processed the document by GCS URI and the recognized synthetic control tokens satisfied the proof threshold.
- Processor/object/bucket cleanup was requested by the harness; no clinical content or secret material was placed in the artifact.
- LIVE run: `31454733509`, artifact `HealthIA-Wave2-DocumentAI-GCS`, id `9087602986`, digest `sha256:1175038da4376a693fa8e5242aa0fd84780484b8f5b4a09738c9a8f4fcc3bb96`.

CLOUD HEALTHCARE LIVE EVIDENCE
- The first Healthcare attempt exposed a real harness defect: `projects.locations.datasets.create` returns a long-running Operation, and the old harness tried to create stores before that operation completed, producing HTTP 404. The failed run was not promoted.
- The corrected proof used provider-aware dataset lifecycle handling, then created a synthetic R4 FHIR Patient and reread it from the provider.
- It also created a valid synthetic DICOM instance, performed STOW, and reread instance metadata through DICOMweb.
- The synthetic dataset/resources were removed after proof and the temporary Healthcare IAM roles were removed and verified absent.
- LIVE run: `31454931773`, artifact `HealthIA-Healthcare-FHIR-DICOM-LRO-LIVE`, id `9087702444`, digest `sha256:f94207be92a48bcf1f80b3ec512c143406df6519e83c40657581f9256ac9e1fa`.

AUTHORIZED API / IAM TRUTH
- User explicitly authorized `I_AUTHORIZE_STT_DOCUMENTAI_HEALTHCARE_LIVE`.
- `speech.googleapis.com`, `documentai.googleapis.com`, and `healthcare.googleapis.com` are now enabled as authorized.
- Initial enabling required temporary `roles/serviceusage.serviceUsageAdmin`; provider execution used only provider-specific temporary roles.
- All temporary roles granted by KIRA for these proofs were removed after execution.
- Veo was not authorized and was not invoked.

PRODUCT FIXES DISCOVERED BY LIVE PROOF
- Android FCM pairing/registration no longer treats a valid paired bearer as revoked merely because no Health Connect observation has created a DeviceConnection yet.
- Android 13+ explicit FCM opt-in no longer relies on a fragile second button press after notification permission approval.
- STT provider testing must use normalized, recognition-friendly synthetic control audio while preserving an objective recognition threshold.
- Cloud Healthcare dataset creation must wait for the provider LRO before creating FHIR/DICOM stores.

NEXT HACKATHON GATES
1. Promote the verified STT and Healthcare fixes into the permanent provider harness and regression tests; remove all temporary one-shot workflows.
2. Re-run complete CI/preflight on the clean Wave 2 head.
3. Finish the true Conversation Brain: multi-turn memory, semantic reference resolution, correction/repair, tool orchestration and human clinical synthesis.
4. Build and prove the one-take autonomous patient journey across chat/voice/document intake → clinical reasoning → research/resource discovery → Calendar/Gmail/Tasks actions → durable FCM follow-up.
5. Audit safety, approval boundaries, receipts, duplicate/no-op behavior, private evidence and judge-facing observability.
6. Only after a separate explicit Veo cost authorization, optionally add the patient education video wow-factor.
7. Prepare the final judge package: reproducible demo, architecture, README, synthetic case, backup video, evidence summary and presentation narrative.

TRUTH RULE
Never expose credentials, OAuth material, cookies, patient identifiers, raw device tokens, Firebase client config, raw proof IDs or real clinical content in public evidence. No provider is called LIVE merely to make a dashboard green.
