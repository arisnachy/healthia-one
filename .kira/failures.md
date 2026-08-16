# Failures

- ATTEMPT: `Invoke-WebRequest -SkipHttpErrorCheck`. WHY IT FAILED: unavailable in Windows PowerShell 5.1. DO NOT REPEAT UNLESS: running pwsh 7.
- ATTEMPT: `Invoke-WebRequest` without basic mode. WHY IT FAILED: legacy IE engine unavailable. DO NOT REPEAT UNLESS: IE dependency is present; use .NET probe instead.
- ATTEMPT: direct WebException handling. WHY IT FAILED: PowerShell wrapped 401 in MethodInvocationException. DO NOT REPEAT UNLESS: inner exceptions are unwrapped.
- ATTEMPT: PowerShell pipeline/direct batch stdin for OAuth JSON. WHY IT FAILED: produced BOM-only, BOM-prefixed or empty versions. DO NOT REPEAT UNLESS: byte-exact validation proves the version; use SDK Python entrypoint.
- ATTEMPT: expected NOT_FOUND from `gcloud secrets describe`. WHY IT FAILED: PowerShell 5.1 promoted native stderr to a terminating error. DO NOT REPEAT UNLESS: error stream behavior is isolated; use list-and-compare.
- ATTEMPT: Cloud Run `--min/--max`. WHY IT FAILED: unsupported by gcloud 535. DO NOT REPEAT UNLESS: use `--min-instances/--max-instances`.
- ATTEMPT: forced Gmail watch with daily idempotency window. WHY IT FAILED: recovered stale receipt and could move the cursor backwards. DO NOT REPEAT UNLESS: explicit force uses a unique timestamp window; scheduled renewal remains daily-idempotent.
- ATTEMPT: same-account reply with natural-language slot. WHY IT FAILED: Gemini correctly stayed below the confidence threshold. DO NOT REPEAT UNLESS: reply is an explicit structured ISO administrative offer or a distinct controlled sender is available.
