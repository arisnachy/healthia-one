# KIRA Decisions

## ADR-001 — One promoted autonomous clinical-continuity circuit
Promote only opted-in blood-pressure measurement follow-up. Do not promote appointment, medication, post-visit, geofence or autonomous clinical-decision Guardian behavior.

## ADR-002 — Human and clinical authority
No autonomous diagnosis, prescription, medication change or declaration of blood-pressure control. External email and reply handling require nested patient consent and durable receipts.

## ADR-003 — Competition proof
Use one continuous real-browser Cloud Run take. Show the full live product plus an exact-head, public, read-only synthetic Judge Mode. Operational workers remain private.

## ADR-004 — Narration
Use Google Cloud Text-to-Speech voice `en-US-Chirp3-HD-Charon` (male). Fail closed if the named voice cannot be synthesized; never silently substitute another speaker.

## ADR-005 — Living System story
Sell magnitude through one causal patient story, not a catalog. A synthetic Health Connect event enters the real product, evidence and missions accumulate, consent gates real Google work, relogin proves continuity, and exact-head Judge Mode proves unattended execution. Never imply that Judge Mode itself performs mutations or that a synthetic device event is a clinical-grade sensor reading.
## ADR-006 — Core v0.1 is the manifesto's first vertical slice

The hackathon candidate implements canonical Twin, event, policy, provenance, obligation, mission and verification contracts. The promoted runtime actors are SENSE, TWIN, GUARDIAN, SAFETY and VERIFY. MEDS means structured monitoring plus a professional-review boundary, never autonomous medication action. Longevity, N=1, Future Simulator and ONE COLLECTIVE extend the same contracts but remain non-live until separately validated and governed.

## ADR-007 — Preserve the user's stale checkout through a clean worktree

Implementation proceeds in `healthia-one-living-system` on `codex/living-system-core` from `origin/main` `ec233508497a982a3f026b4bad9895e748e15ea6`. The original checkout and its user-owned changes are not reset, overwritten or automatically carried into the candidate.

## ADR-008 — Extend PatientState instead of creating a second Twin store

Core v0.1 adds backward-compatible canonical fields to `PatientState` and keeps `clinical_twin_summary()` as a derived projection. Old persisted states load through defaults. State-changing Living Twin events use stable IDs, reject unknown public fields and causal claims, enforce patient namespace, and advance the Twin version idempotently.
