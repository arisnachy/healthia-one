# HealthIA ONE — Wave 3 submission delta

> **Status:** candidate upgrade in progress. This document does not replace the preserved submission candidate or public judge video until the exact Wave 3 HEAD passes all gates and a new continuous take is independently verified.

## What Wave 3 changes for the judge

The previous candidate proved a durable Taskmaster result mission, Gemini 3.5 + Google ADK, private evidence, Firestore continuity, Cloud Run and a continuous public demo. Wave 3 is focused on the part a judge experiences most directly: **does the agent understand the patient, keep working autonomously, stop at the right human boundary, and prove what it actually did?**

### 1. Conversation Brain — evidence-backed references

Wave 3 makes reference handling an explicit contract instead of a routing side effect.

- Current explicit corrections override stale context.
- “Eso / it / the second one / lo de ayer” may be resolved only from bounded authorized recent context.
- The resolved reference records its source and evidence message/mission when available.
- If HealthIA cannot prove the referent, it asks one concise clarification instead of guessing.
- Raw hidden clinical interview payloads are still excluded from conversational memory.

### 2. Mission autonomy — advance to the next real boundary

An applicable Google health mission is no longer supposed to stop merely because one tool call finished. Google ADK is instructed to continue every verifiable read-only/non-mutating step that is deterministically available until one of four real boundaries is reached:

1. the patient must choose;
2. an exact external-write authorization is required;
3. evidence is genuinely missing;
4. a real external event/reply is required.

The agent has no tool for creating its own consent or OAuth grant.

### 3. Conversation-native mission continuation

A durable active mission can be resumed with natural follow-ups such as:

- “No, la segunda.”
- “Ese me sirve.”
- “Continúa con eso.”
- “The second one.”
- “Go ahead with that.”

An explicit switch back to a clinical result, measurement, treatment, document, device, privacy or timeline topic outranks the old Google mission.

### 4. Visible proof — Comprobante de misión

The patient-facing message includes a **Comprobante de misión** generated from ADK execution events and deterministic mission state, not from model claims. It can show:

- verified mission steps that actually executed;
- durable state and next action;
- a visible stop at human authorization;
- a visible wait for a real external event;
- durable completion when the mission truly closes.

Connector/resource success is never inferred from model prose.

### 5. Adversarial judge gate

Wave 3 DialogBench now requires all of the following in addition to the existing 120+ bilingual contextual scenarios:

- unanchored pronouns/ordinals fail closed;
- active mission natural continuation routes correctly;
- explicit clinical topic switches cannot be hijacked by a stale mission;
- patient words remain unchanged;
- context remains bounded.

### 6. Winning one-take replacement rule

The target story is defined in `docs/WINNING_ONE_TAKE.md`:

**natural conversation → correction/reference → evidence-first result → autonomous navigation mission → human authorization boundary → visible receipt → event-driven continuation → durable outcome/continuity**.

The old public judge video remains the fallback until the replacement take passes:

- exact-head full CI/JUDGE;
- adversarial autonomy gates;
- continuous unedited Cloud recording;
- public publication + anonymous SHA verification;
- README, EVIDENCE and Devpost synchronized to the same exact candidate.

## Infrastructure freeze

Wave 3 does not add another provider for the sake of breadth. Scheduler, Firebase/FCM, STT, Document AI and Cloud Healthcare FHIR/DICOM already have LIVE evidence. Veo remains an optional separate cost gate and is deliberately outside this product-focused phase.

## Final pitch delta

**Old emphasis:** HealthIA preserves evidence and completes durable health tasks.

**Wave 3 emphasis:** **HealthIA understands what the patient means, advances every safe step it can actually prove, stops exactly where a human must decide, and preserves a verifiable outcome so the patient never starts over.**
