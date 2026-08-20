# Security and clinical safety matrix

| Risk | Current control | Verification | Production gap |
|---|---|---|---|
| Urgent symptoms handled as routine chat | Deterministic urgent-language gate before routing | Safety regression tests | Clinical validation and monitored incident review |
| Extreme vital value downgraded by a model | Deterministic vital thresholds and BASTION stop condition | Unit and proactive tests | Validated protocols, localization and clinician governance |
| Autonomous diagnosis | Prompts, public copy and data contracts separate confirmed facts from hypotheses | Chat-route and safety contracts | Clinical evaluation and regulatory analysis |
| Medication dose change | MEDSAFE forbids stopping, duplicating, substituting or changing dose | Skipped-dose and treatment tests | Pharmacist review, medication knowledge source and jurisdictional policy |
| Family history treated as destiny | HEREDITAS creates preventive questions only; non-biological relatives excluded from biological clusters | Family clustering tests | Genetics specialist review and richer pedigree standards |
| Prompt injection or unsafe clinical direction in PDF/image/model output | Multimodal content is untrusted; deterministic bilingual output guard withholds diagnosis/treatment directives and forces professional review | `test_security_hardening.py` plus result/ADK regressions | Clinician-red-team corpus, DLP and malware/content-disarm pipeline |
| Path traversal in uploaded filename | Filename normalization and patient-scoped resolved-path check | Document upload/download tests | Private Cloud Storage, signed access and malware scanning |
| Oversized or unsupported upload | Extension allowlist and configured 5 MB limit | API tests | MIME sniffing, antivirus, DLP and content-disarm pipeline |
| Unwanted proactive surveillance | Signal-level consent, global pause, quiet hours, snooze and rule muting | Patient-control tests | Authenticated consent ledger and policy versioning |
| Alert during quiet hours | BASTION consent gate | Cross-midnight quiet-hour tests | Durable scheduler and queued delivery policy |
| Urgent alert blocked by pause | Optional deterministic urgent-safety bypass | Urgent-bypass tests | Clinical/legal policy and patient onboarding |
| Duplicate background intervention | Stable emitted-rule keys | Idempotency tests and smoke test | Cross-instance Firestore transaction/lease |
| Backdated record interpreted as newest | Collections sorted by clinical/operational timestamp | Chronological insertion test | Conflict resolution and timezone normalization |
| Private chain-of-thought exposed | UI displays public agent actions and evidence only | Static UI contracts | Model-provider and observability review |
| Secret committed or signing secret omitted | `.env` ignored; cloud startup fails closed without 32-byte session/device signing secrets | Security hardening tests and deploy parser | Automated secret scanning and rotation drill |
| Internal file path exported | Export removes `storage_path` and binary files | Export regression test | Authenticated export job, retention and deletion policy |
| Cross-patient data access | Authentication secure by default, patient identity bound server-side, disabled/logout sessions revoked | Auth and patient-isolation tests | Managed identity provider, MFA and formal Firestore rules audit |
| Audit record tampering | Typed in-state audit list | API and route tests | Append-only tamper-evident cloud ledger |
| Model quota exhaustion | Deterministic local mode works without Gemini | Local smoke test | Quota-aware ADK scheduling, fallback and cost controls |
| Background process restart loses schedule | Current loop is in-process | Not claimed as durable | Cloud Tasks or Pub/Sub and restart/resume tests |
| Public demo contains real PHI | Synthetic fixture policy and visible labels | Documentation and seed data | Access controls and formal data handling policy |
| Login/pairing brute force | Sliding-window limits by IP/account/device plus a global pairing ceiling; pairing bearers expire after 7 days | Focused abuse tests and authenticated smoke | Distributed limiter for multi-instance production |
| Device writes exceed consent | Ingestion intersects paired permissions, declared metrics and canonical server-side signal consent; profile projections cannot restore revoked consent | Device ingestion hardening tests | Signed platform attestation and revocation receipts |
| Excessive IAM blast radius | Deploy grants Secret Manager access per secret and Storage access per bucket, then removes obsolete project-wide roles | Cloud evidence contract and PowerShell parse | Live post-deploy IAM-policy reread on the exact candidate SHA |
| Oversized profile resource abuse | Bounded strings and collection sizes at Pydantic boundary | Security hardening tests | Request-body limit at ingress/WAF |

## Competition security boundary

The candidate now demonstrates a coherent boundary rather than isolated checks: identity, revocation, consent, device provenance, untrusted multimodal input, generated clinical output and cloud IAM all fail closed before data becomes patient-visible or persistent. It is a strong hackathon control plane, not a claim of regulatory certification or clinical effectiveness.

## Release rule

A green CI run means the documented software contracts passed in a clean environment. It does not prove clinical effectiveness, legal compliance, production security, regulatory clearance or absence of defects.
