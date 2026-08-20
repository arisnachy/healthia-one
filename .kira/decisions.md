# Decisions

- DECISION: Treat identity, consent, device provenance, untrusted multimodal content, generated clinical output and cloud IAM as one fail-closed boundary. WHY: a healthcare agent is only as safe as its weakest crossing. IMPACT: cloud startup fails without durable signing secrets; revoked consent and unsafe output cannot be restored by client/model claims; IAM is resource-scoped.
- DECISION: Keep the abuse limiter process-local for the single-instance hackathon deployment and disclose the scale boundary. WHY: deterministic low-complexity protection fits the current max-instance contract. IMPACT: multi-instance production requires a distributed limiter before scaling.

- DECISION: Use `/api/readiness` for deployed readiness. WHY: Cloud Run reserves `/healthz` and returns 404. IMPACT: local `/healthz` remains backward compatible; deployed gate is truthful.
- DECISION: Enforce exact web service and exact OAuth secret names in provisioning scripts. WHY: prevent accidental exposure/injection into the private backend. IMPACT: fail closed on wrong targets.
- DECISION: Use direct SDK Python stdin for OAuth client import on Windows. WHY: Windows PowerShell/native pipelines produced invalid BOM/empty versions. IMPACT: valid UTF-8 JSON without payload logging.
