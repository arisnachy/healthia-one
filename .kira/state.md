CURRENT OBJECTIVE
Publish and validate the exact live Google Constellation implementation on PR #37 without merging main.

DONE
- OAuth persisted for synthetic patient `patient_8b8c820ea54c4ca98b84ef12d6f4fafa`; refresh token exercised by real Gmail watch/Calendar/Tasks calls without exposure.
- Places New returned 8 real candidates; selected place id is recorded in mission `gmission_cf976caf1b4d4578`.
- Gmail send returned a real message/thread id under exact authorization `gauth_89e498efef0948d8`.
- Dedicated private Gmail worker, authenticated Pub/Sub push subscription and daily Scheduler renewal are live.
- Real `users.watch`, Gmail push, `users.history.list`, exact thread correlation and structured appointment offer reached `slot_offered`.
- Real FreeBusy, Calendar event and Google Task completed under separate exact authorizations; both were reread in Google UI.
- Mission reached `completed`; exact finalize replay recovers the same resource IDs and now leaves one task id and one terminal projection.
- Duplicate Pub/Sub delivery with real message id was ACKed without changing the completed mission or receipts.
- Full local suite: 400 tests PASS. Secret-pattern scan and `git diff --check` pass (line-ending warnings only).

IN PROGRESS
- Commit/push the implementation and wait for PR #37 checks on the new SHA.

NEXT
- Independent JUDGE review against live evidence, CI and final worktree state.

CRITICAL FACTS
- Public web revision: `healthia-one-web-demo-00016-g87`; backend remains private and unchanged.
- Gmail worker revision: `healthia-gmail-worker-00004-n8p`; topic/subscription/Scheduler are live.
- Never reveal credentials, tokens, cookies or secret payloads.
