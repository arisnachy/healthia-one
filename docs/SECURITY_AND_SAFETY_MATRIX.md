# Security and clinical safety matrix

| Risk | Current control | Verification | Production gap |
|---|---|---|---|
| Urgent symptoms handled as routine chat | Deterministic urgent-language gate before routing | Safety regression tests | Clinical validation and monitored incident review |
| Extreme vital value downgraded by a model | Deterministic vital thresholds and BASTION stop condition | Unit and proactive tests | Validated protocols, localization and clinician governance |
| Autonomous diagnosis | Prompts, public copy and data contracts separate confirmed facts from hypotheses | Chat-route and safety contracts | Clinical evaluation and regulatory analysis |
| Medication dose change | MEDSAFE forbids stopping, duplicating, substituting or changing dose | Skipped-dose and treatment tests | Pharmacist review, medication knowledge source and jurisdictional policy |
| Family history treated as destiny | HEREDITAS creates preventive questions only; non-biological relatives excluded from biological clusters | Family clustering tests | Genetics specialist review and richer pedigree standards |
| Hallucinated PDF/image content | Unread files stay `pending_review` | Document tests and UI copy | Verified Gemini multimodal extraction, confidence and human confirmation |
| Path traversal in uploaded filename | Filename normalization and patient-scoped resolved-path check | Document upload/download tests | Private Cloud Storage, signed access and malware scanning |
| Oversized or unsupported upload | Extension allowlist and configured 5 MB limit | API tests | MIME sniffing, antivirus, DLP and content-disarm pipeline |
| Unwanted proactive surveillance | Signal-level consent, global pause, quiet hours, snooze and rule muting | Patient-control tests | Authenticated consent ledger and policy versioning |
| Alert during quiet hours | BASTION consent gate | Cross-midnight quiet-hour tests | Durable scheduler and queued delivery policy |
| Urgent alert blocked by pause | Optional deterministic urgent-safety bypass | Urgent-bypass tests | Clinical/legal policy and patient onboarding |
| Duplicate background intervention | Stable emitted-rule keys | Idempotency tests and smoke test | Cross-instance Firestore transaction/lease |
| Backdated record interpreted as newest | Collections sorted by clinical/operational timestamp | Chronological insertion test | Conflict resolution and timezone normalization |
| Private chain-of-thought exposed | UI displays public agent actions and evidence only | Static UI contracts | Model-provider and observability review |
| Secret committed to repository | `.env` ignored; secure PowerShell process prompt | Repository review | Secret Manager and automated secret scanning |
| Internal file path exported | Export removes `storage_path` and binary files | Export regression test | Authenticated export job, retention and deletion policy |
| Cross-patient data access | Synthetic single-patient scope only | Explicit truth boundary | Authentication, tenant isolation, authorization tests and Firestore rules |
| Audit record tampering | Typed in-state audit list | API and route tests | Append-only tamper-evident cloud ledger |
| Model quota exhaustion | Deterministic local mode works without Gemini | Local smoke test | Quota-aware ADK scheduling, fallback and cost controls |
| Background process restart loses schedule | Current loop is in-process | Not claimed as durable | Cloud Tasks or Pub/Sub and restart/resume tests |
| Public demo contains real PHI | Synthetic fixture policy and visible labels | Documentation and seed data | Access controls and formal data handling policy |

## Release rule

A green CI run means the documented software contracts passed in a clean environment. It does not prove clinical effectiveness, legal compliance, production security, regulatory clearance or absence of defects.
