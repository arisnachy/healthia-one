# Decisions

- DECISION: Use `/api/readiness` for deployed readiness. WHY: Cloud Run reserves `/healthz` and returns 404. IMPACT: local `/healthz` remains backward compatible; deployed gate is truthful.
- DECISION: Enforce exact web service and exact OAuth secret names in provisioning scripts. WHY: prevent accidental exposure/injection into the private backend. IMPACT: fail closed on wrong targets.
- DECISION: Use direct SDK Python stdin for OAuth client import on Windows. WHY: Windows PowerShell/native pipelines produced invalid BOM/empty versions. IMPACT: valid UTF-8 JSON without payload logging.
