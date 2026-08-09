# Opportunity Autopilot — current verified scope

This document is a truth-boundary snapshot for draft PR #36. It exists so later work cannot silently convert design contracts into claimed product evidence.

## Implemented in the branch

- Patient/family watch topics preserve the subject and relation from the clinical profile/genogram.
- Separate patient-scoped Opportunity Vault with Memory, JSON and Firestore persistence.
- Scientific source adapters for PubMed/NLM E-utilities, Europe PMC and ClinicalTrials.gov.
- Scientific retrieval/deduplication does not require a Gemini call.
- PubMed/Europe PMC indexing is not mislabeled as proof of peer review.
- Therapeutic comparison uses the recorded medication list plus source-reported benefits/limitations and never authorizes medication changes.
- Optional Google Search-grounded resource discovery is cost-gated and call-capped.
- A grounded program is only a candidate; model-extracted requirements remain UNKNOWN until original-source verification.
- Official HTML/plain/PDF program sources can be loaded under an allowlisted domain boundary, hashed and used for structured requirement extraction.
- HTML/plain evidence excerpts must exist literally in the downloaded source or the rule is downgraded to UNKNOWN.
- Empty/unclear requirement sets remain one explicit blocking UNKNOWN (`Verify official program requirements manually`) rather than being interpreted as “no requirements”.
- A model-extracted submission portal outside the verifier's approved official-domain boundary is discarded and recorded as a caveat; it never becomes an executable destination merely because Gemini returned it.
- Locale is never treated as residence, and display name is never substituted for legal name.
- Application prefill, missing-field/document tracking, patient review, external-submit authorization and durable receipt states are modeled separately.
- No application may be called SUBMITTED merely because the model generated a form; a real external adapter receipt is required.
- Crash-safe leased event claims support RUNNING / FAILED / COMPLETED, retry after failure, parallel-worker blocking and duplicate-completion suppression.
- Patient-scoped public Autopilot receipts contain action/status/reason/cost/evidence IDs but no private reasoning.
- Durable outbox records have stable event IDs and a Firestore collection shape suitable for direct Eventarc document-created delivery.
- Private Cloud Run/Eventarc and private Cloud Scheduler deployment scripts exist and require explicit `-Confirmed`; they do not silently enable APIs or use unauthenticated invocation.
- Autonomous Scientific Radar and Assistance Radar have separate permissions, both OFF by default and controllable from chat.
- Scientific schedule contract is weekly opt-in; assistance schedule contract is monthly opt-in; repeated producer runs deduplicate within the same patient/mode/period.
- Discoveries is a first-class Health OS view showing science, patient/family relation, source links, program/application state, original-source verification provenance and public Autopilot receipts.
- The main chat can control discoveries, therapeutic comparisons, help/resource discovery, form preparation, missing requirements/documents and radar permissions.
- Deterministic urgent clinical safety remains ahead of opportunity routing.

## Verified locally on the draft branch

The branch has been exercised with the repository test suite, Python compilation, semantic frontend syntax checks, Full System, DialogBench, smoke/JUDGE, real Chromium browser smoke, LAB OMEGA Core and LAB OMEGA Secondary after the Opportunity Autopilot integration.

Local validation is useful engineering evidence, but it does not replace the exact-head GitHub/Cloud submission gate.

## Intentionally not claimed yet

1. **No billable Cloud deployment was executed for this branch in this work session.** The Eventarc/Cloud Run/Cloud Scheduler scripts are fail-closed deployment contracts until an exact candidate is explicitly promoted and deployed.
2. **No real external assistance application/email/portal submission is claimed.** Authorization currently stops at `READY_TO_SUBMIT`; a configured delivery adapter must return a verifiable receipt before `SUBMITTED`.
3. **Direct “attach the missing assistance document in chat” is not yet submission evidence.** The application workflow can identify missing documents and existing HealthIA documents, but the result-upload composer is not claimed as a dedicated application-document attachment path until that linkage is implemented and browser-proven.
4. **No global cross-patient evidence cache is claimed.** Source retrieval is already zero-LLM, but global canonical reuse across patients remains an optimization until implemented and tested.
5. **Patient-state/family/medication change events are modeled in the event schema, but scheduled discovery is the currently implemented autonomous producer.** Do not claim automatic scientific scans from every clinical mutation until a selective event policy is explicitly wired and proven.

## Promotion rule

Keep PR #36 draft until the exact final head passes all repository/browser/LAB/JUDGE/release gates. After that, a Cloud proof must demonstrate the private Eventarc worker, consent-gated scheduler producer, Firestore outbox, leased claim, durable receipt and redelivery/process-replacement behavior on the deployed candidate. Only then should the new candidate be considered for merge into `main` or replacement of preserved hackathon evidence.
