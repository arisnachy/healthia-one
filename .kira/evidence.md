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
- Full local suite: 400/400 PASS. Focused Gmail/mega-loop/deployment/OAuth contracts also pass.
- Security cleanup: an untracked 143-byte OAuth JSON artifact created by a legacy stdin bug was detected by shape only, never printed, and permanently deleted; current importer uses direct SDK stdin. No credential/API-key/auth-code patterns remain in the repository scan.
- Scheduler PREP LIVE: real Gmail watch force-renewal succeeded before the natural run; logging-enabled worker revision `healthia-gmail-worker-00014-pvs` served 100% traffic.
- Scheduler natural provider execution: Cloud Scheduler emitted 2 lifecycle events and the private worker returned HTTP 200 at `2026-08-10T05:00:00.993008Z` on revision `healthia-gmail-worker-00014-pvs`.
- Scheduler durable receipt proof: completed `gmail.watch` receipt(s) exist in the PREP window, while the natural 05:00 Scheduler window contains exactly 0 `gmail.watch` receipts. Therefore the scheduled execution was a real no-op and did not call Gmail watch renewal again.
- Final Scheduler proof artifact: GitHub Actions run `31384610740`, artifact `HealthIA-Wave2-Scheduler-LIVE`, artifact digest `sha256:c16a4c6ec7f329685aaf48a23e773451cccab73ac2cb54952b66ff369eb9ea30`; `status=LIVE_PASS`, `scheduler_noop_proven=true`, `iam_mutation=false`, `secret_material_exposed=false`.
- Scheduler proof caveat preserved explicitly: the pre-fix worker did not emit the aggregate response payload into Cloud Logging because its logger had no Cloud Run handler. Provider execution, HTTP 200, and the no-op are independently proven by Cloud Scheduler/Cloud Run logs plus durable action receipts. The current worker logger is bound to `uvicorn.error` and has a regression test.
