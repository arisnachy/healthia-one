# Architecture

```text
Patient chat / measurements / result upload
                 ↓
           FastAPI gateway
                 ↓
     deterministic safety boundary
                 ↓
      KIRA dynamic team router
       ↙      ↓       ↓       ↘
HISTORIA  SENTINEL  LUMEN  VITA/NAVIGATOR
                 ↓
       longitudinal patient state
          JSON local / Firestore
                 ↓
    proactive evaluator + event broker
                 ↓
       SSE message to patient chat
```

## Design rules

1. The patient owns the context and explicitly selects monitored signal classes.
2. Deterministic safety rules execute before model reasoning.
3. The minimum useful specialist team is activated; the UI does not force the patient to manage agents.
4. Every intervention exposes detected signal, reason, evidence IDs, uncertainty, and next action.
5. Private chain-of-thought is never rendered. Only public work, tool results, and decisions appear.
6. Long-running missions have states and closure conditions instead of disappearing after chat.
7. The local JSON adapter is replaceable by Firestore without changing the domain contracts.
8. The public demo uses synthetic data only.

## Next production layers

- Patient authentication and scoped authorization.
- Firestore transaction/idempotency tests.
- Cloud Tasks or Pub/Sub for durable scheduled follow-up.
- Vertex AI/Gemini multimodal result extraction.
- FHIR import/export with provenance and patient consent.
- Professional review channel for actions that require clinical accountability.
- Golden clinical-safety evaluation suite and attack tests.
