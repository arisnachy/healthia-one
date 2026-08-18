# How We Built HealthIA ONE: Durable Health Agents, ONE SAFETY, and Real Google AI

> **This piece of content was created for the purposes of entering the All Things Agentic Hackathon 2026.**

HealthIA ONE started from a simple problem: health information and unfinished health work are fragmented across chats, laboratory reports, imaging, medications, appointments, devices, support resources and external services. A useful patient agent should not merely answer one prompt well and then forget what still needs to happen.

We built HealthIA ONE as a **patient-owned, event-driven health continuity system**. Its core idea is durable work: preserve original evidence, create patient-scoped missions, use AI only where reasoning adds value, stop at human authority boundaries, resume the same mission after consent, and require real connector evidence before claiming that the outside world changed.

## 1. Architecture

The final judging path combines:

- **Gemini 3.5 Flash on Vertex AI / Google GenAI** for bounded reasoning and multimodal extraction;
- **Google Agent Development Kit (ADK)** for demand-driven agent execution;
- **Cloud Run** for runtime;
- **Firestore** for durable patient, mission and Patient Twin state;
- **private Google Cloud Storage** for original clinical evidence;
- **Secret Manager + service identity / ADC** for secrets and credentials;
- **Google Model Armor** plus local fail-closed policy at prompt ingress;
- **Google Places / Maps Platform** for authorized resource discovery;
- **Gmail + Pub/Sub + Calendar + Google Tasks** for real external workflow paths;
- **OpenTelemetry + Google Cloud Trace** for execution correlation.

The model is not the system of record. Durable patient state is.

## 2. Evidence first, interpretation second

For supported synthetic clinical PDFs/images, HealthIA preserves the original bytes before model interpretation. Gemini performs bounded multimodal extraction, structured findings are persisted, and the Patient Twin links derived state back to original evidence.

If evidence is unreadable or ambiguous, the workflow fails closed rather than inventing a finding.

## 3. ONE SAFETY: authorization is not execution evidence

HealthIA separates planning from permission and permission from proof of execution.

```text
Sense / Request
→ Reason
→ Authorize
→ ONE SAFETY
→ HealthActionTicket
→ Connector
→ Receipt
→ Cloud Trace
```

A one-use `HealthActionTicket` authorizes one bounded external action. It is **not** evidence that the action happened. Completion requires the connector to return a durable receipt.

The final Cloud proof correlates one real Google Places action across:

- Trace ID `eec691300b7bb1c1c0564e95fb090e4f`
- HealthActionTicket `hat_021b1b6b1b4542e2`
- action `maps.search_nearby`
- receipt `receipt_95ba26286e6f4e15`
- outcome `completed`

The promotion gate then queried **Google Cloud Trace by that exact Trace ID** and required the exported trace to contain `google.action.guarded_execute`.

## 4. Prompt injection must fail before mutation

HealthIA uses two prompt-ingress boundaries: real Google Model Armor and local fail-closed application policy.

The controlled adversarial proof requires:

- Model Armor detects the jailbreak probe;
- HealthIA returns HTTP `400` at `prompt_ingress`;
- `model_called = false`;
- zero new HealthActionTickets;
- zero patient-state mutation.

A blocked prompt therefore cannot reach the model or obtain an execution capability.

## 5. Human authority is part of the agent design

HealthIA can create a durable mission before location consent, but it does not perform a Google Places search merely because the mission exists.

After the patient authorizes the next bounded step, the **same mission resumes**.

Exact bounded choices also avoid unnecessary model calls. If the patient says **“The second one,”** HealthIA deterministically selects the second displayed candidate instead of asking a language model to reinterpret a precise ordinal choice.

## 6. Real unattended continuity

For an opted-in synthetic patient, HealthIA can detect that a blood-pressure follow-up is overdue without a new chat prompt, create durable work, wake an event-driven worker, perform authorized connector steps, and resume the same mission when a real reply arrives.

Autonomy does not remove consent, receipts, idempotency or safety boundaries.

## 7. Google Veo integration: HealthIA Explain

HealthIA also contains a patient-education media path called **HealthIA Explain**. The feature is designed so patient-specific facts can remain outside the generated video prompt while **Veo receives only a prevalidated generic educational prompt with no patient data**.

The implemented path uses **Vertex AI Veo 3.1 Fast (`veo-3.1-fast-generate-001`)**. A controlled LIVE proof generated one **8-second, 720p** synthetic medical-education clip, stored it in a private GCS evidence path, validated the MP4, and recorded a manifest containing the model, duration, resolution, SHA-256, `synthetic_only: true` and `patient_data_sent: false`.

This bonus integration is preserved separately from the frozen final ONE SAFETY runtime so bonus evidence does not rewrite or destabilize the exact judging candidate.

Veo implementation and LIVE proof lineage: https://github.com/arisnachy/healthia-one/pull/43

## 8. What we learned

The strongest agentic systems are not the ones that call the most models. They are the ones that know:

- when reasoning is useful;
- when deterministic logic is safer;
- when a human owns the decision;
- when a real external action has actually happened;
- how to carry unfinished work forward without losing provenance.

That is the idea behind HealthIA ONE:

**Your health never starts over.**

## Public project evidence

- Official Devpost demo (3:55): https://youtu.be/v7SJUkzzRxw
- Judges: https://github.com/arisnachy/healthia-one/blob/main/JUDGES_START_HERE.md
- Repository: https://github.com/arisnachy/healthia-one
- Architecture: https://github.com/arisnachy/healthia-one/blob/main/docs/ARCHITECTURE.md
- Final proof: https://github.com/arisnachy/healthia-one/blob/main/hackathon/evidence/one_safety_final_proof.json
- Veo / HealthIA Explain integration: https://github.com/arisnachy/healthia-one/pull/43

All hackathon clinical demonstrations use synthetic patient data.
