# HealthIA ONE — Opportunity Autopilot

## Mission

Opportunity Autopilot extends HealthIA's evidence-first Taskmaster thesis from **patient events** to **changes in the outside world**.

It watches only patient-authorized clinical/family topics, retrieves new evidence from serious sources, deduplicates it before any model spend, preserves patient-vs-family scope, and turns relevant findings into durable discoveries or assistance missions. The chat remains the control surface.

The design is intentionally quiet: a source update is not automatically a patient notification.

```text
Patient / family context
  → derived watch topics
  → cheap source retrieval + dedupe
  → deterministic relevance / evidence gate
  → optional bounded Gemini grounded search
  → patient-scoped Opportunity Vault
  → chat decides when/how to surface
  → application/document workflow when requested
  → explicit patient review before external submission
  → durable receipt before mission closure
```

## Scientific radar

The zero-LLM retrieval layer uses official APIs:

- PubMed through NCBI E-utilities (`ESearch` + `EFetch`).
- Europe PMC REST search.
- ClinicalTrials.gov API v2.

The source adapter stores identifiers, URL, publisher, publication date, evidence tier, peer-review/preprint status where available, and source text/abstract used by later appraisal.

A new publication does **not** change patient treatment. `therapeutic_comparison()` places cited source claims next to the recorded medication list and explicitly requires professional review. It never authorizes starting, stopping, substituting, or changing a dose.

## Family/genogram semantics

Watch topics retain a subject and relation.

Example:

```text
patient: hypertension → relation=self
son: autism → relation=hijo
```

A family condition can therefore drive caregiver/community research without being converted into a diagnosis or risk claim about the patient.

## Resource and assistance radar

`GroundedResourceRadar` is a separate, explicitly enabled paid layer. It uses Gemini with Google Search grounding only after cheap filtering and is capped by `max_calls` per radar instance.

Results must include a direct source URL and pass an official-domain allowlist before they enter the Opportunity Vault. The initial list favors government/public-health sources and can be expanded deliberately.

The model is not allowed to infer eligibility facts such as income, disability certification, citizenship or diagnosis.

## Eligibility and application workflow

An assistance program stores explicit requirements and required documents. Deterministic evaluation returns four independent concepts:

- matched requirements;
- unmet requirements;
- unknown requirements;
- missing documents.

Unknown is never silently converted to eligible.

Application state:

```text
DISCOVERED
  → ELIGIBILITY_CHECKED
  → DOCUMENTS_REQUIRED / FORM_PREFILLED
  → PATIENT_REVIEWED
  → READY_TO_SUBMIT
  → SUBMITTED
  → AWAITING_DECISION
  → COMPLETED
```

`authorize_external_submission()` fails closed unless the patient reviewed the packet and no required field/document is missing. `record_submission_receipt()` refuses to mark a submission unless an external action was explicitly authorized and a durable receipt/reference exists.

## Cost hierarchy

1. Watch-topic derivation: deterministic, zero LLM.
2. PubMed/Europe PMC/ClinicalTrials retrieval: network only, zero LLM.
3. Fingerprint/deduplication: deterministic, zero LLM.
4. Evidence/relevance gate: deterministic, zero LLM.
5. Grounded web resource search: optional and explicitly bounded.
6. Patient-facing synthesis/application help: only when a relevant item exists or the patient asks.

The same scientific source can be processed once and matched to multiple authorized patient topics rather than paying to rediscover the same paper for every patient.

## Event/idempotency contract

`OpportunityAutopilot` claims an event with a stable patient-scoped idempotency key. Re-delivery returns a duplicate report and does not repeat discovery, program or application side effects.

The vault has Memory, JSON and Firestore implementations and lives separately from the canonical clinical `PatientState`, preserving the existing clinical-twin truth boundary.

## Chat-first controls

`OpportunityChatController` handles patient intents such as:

- “¿Qué hay nuevo?”
- “¿Encontraste alguna ayuda económica?”
- “Completa el formulario de esa ayuda.”
- “¿Qué documento falta?”
- “Busca recursos.”
- “No busques más sobre autismo.”

The controller returns a structured action and optional `ui_action`; it does not require a separate autonomous-agent UI.

## Current branch boundary

This branch establishes the durable domain, scientific source adapters, resource-search gate, event runtime, application workflow and chat controller with deterministic tests. It intentionally does **not** merge directly to `main` or silently enable recurring/paid scans. Integration into the existing FastAPI/chat service and any scheduled Pub/Sub/Eventarc trigger must pass the normal HealthIA CI/LAB/JUDGE gates before promotion.
