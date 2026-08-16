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

The source adapter stores identifiers, URL, publisher, publication date, evidence tier, preprint metadata where available, and source text/abstract used by later appraisal. PubMed/Europe PMC indexing is **not** treated as proof that peer review occurred; peer-review status stays conservative unless explicit evidence exists.

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

A grounded search result is only a **program candidate**. Requirements extracted by the model are marked `unknown` with `source_verification_required=true`; they cannot produce a positive eligibility decision until a separate source/form verification step confirms them. The model is not allowed to infer income, disability certification, citizenship, residence or diagnosis.

Locale is never treated as residence. Until a structured patient-confirmed country field exists, resource search receives only the free-text address explicitly entered by the patient, and country/region remain unknown.

## Eligibility and application workflow

An assistance program stores explicit requirements and required documents. Deterministic evaluation returns four independent concepts:

- matched requirements;
- unmet requirements;
- unknown requirements;
- missing documents.

Unknown is never silently converted to eligible. A display name is never substituted for legal name in an application packet.

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

`authorize_external_submission()` fails closed unless the patient reviewed the packet and no required field/document is missing. `record_submission_receipt()` refuses to mark a submission unless an external action was explicitly authorized and a durable receipt/reference exists. No real external delivery adapter is claimed by this branch yet.

## Cost hierarchy

1. Watch-topic derivation: deterministic, zero LLM.
2. PubMed/Europe PMC/ClinicalTrials retrieval: network only, zero LLM.
3. Fingerprint/deduplication: deterministic, zero LLM.
4. Evidence/relevance gate: deterministic, zero LLM.
5. Grounded web resource search: optional and explicitly bounded.
6. Patient-facing synthesis/application help: only when a relevant item exists or the patient asks.

A future global evidence cache can further reduce duplicate source retrieval across patients, but this branch does **not** claim that optimization until it is implemented and proven.

## Event, crash-recovery and idempotency contract

`OpportunityAutopilot` uses a patient-scoped leased event claim. Memory, JSON and Firestore claim stores share the same state contract:

```text
RUNNING (lease)
  → COMPLETED
  ↘ FAILED → retry / new lease
```

- `COMPLETED` redelivery is a duplicate and has no side effects.
- An unexpired `RUNNING` lease blocks a concurrent worker.
- An exception marks the claim `FAILED`, so the same event can retry instead of being lost.
- In Firestore mode, claim acquisition runs transactionally.
- Compatibility `processed_event_keys` are written only after successful work; they are not the authoritative claim boundary.

Successful runs can persist a patient-scoped `AutopilotReceipt` containing only public execution evidence: event type, action/status/reason, cost class, and correlated discovery/program/application IDs. It never stores private reasoning or chain-of-thought.

The Opportunity Vault, event claims and receipts each have patient-scoped persistence. They remain separate from the canonical clinical `PatientState`, preserving the existing clinical-twin truth boundary.

## Patient-scoped API

The authenticated HealthIA boundary now exposes `/api/opportunities` plus save/review/authorize actions. These routes are deliberately **not** in the public-route allowlist. The API returns the patient's watch topics, discoveries, program candidates, application packets and recent receipts.

Authorization only moves a complete packet to `READY_TO_SUBMIT`; it explicitly reports that no external action happened. An email/portal submission may become `SUBMITTED` only after a real configured adapter returns a durable receipt.

## Chat-first controls

`OpportunityChatController` handles patient intents such as:

- “¿Qué hay nuevo sobre mi salud?”
- “¿Encontraste alguna ayuda económica?”
- “Compáralo con mi medicación.”
- “Completa el formulario de esa ayuda.”
- “¿Qué documento falta para la solicitud?”
- “Busca ayudas para autismo.”
- “No busques más sobre autismo.”

Normal language such as “beneficios de caminar” or generic “¿qué falta?” is intentionally excluded so Opportunity Autopilot does not hijack ordinary conversation. Deterministic urgent safety is evaluated before opportunity routing.

## Current branch boundary

This branch establishes the durable domain, scientific source adapters, resource-search gate, crash-retryable event runtime, patient-scoped claims/receipts, application workflow, authenticated opportunity API and chat controller with deterministic tests. It intentionally does **not** merge directly to `main` or silently enable recurring/paid scans.

Still required before claiming the full autonomous Taskmaster loop:

1. configure a private Cloud Run worker and Eventarc trigger with authenticated service identity;
2. create a durable event source/outbox for clinically relevant state changes and/or scheduled discovery refresh;
3. prove the exact deployed candidate survives redelivery/process replacement without duplicated side effects;
4. add a judge-visible Discoveries/receipt surface without exposing private reasoning;
5. implement and prove a real external delivery adapter before claiming that applications are submitted.
