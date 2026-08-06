# HealthIA ONE — Hackathon Victory Plan

## Strategic position

HealthIA ONE should enter **The Taskmaster** as its primary track.

The winning story is not “a medical chatbot.” It is:

> A patient-owned health mission autopilot that continuously converts authorized device data, documents, appointments and treatment check-ins into safe, auditable next actions until the patient reaches a verified next step.

Secondary award targets:

1. Best Architectural Design.
2. Best Multimodal UX.
3. Individual/Hobbyist.

The Fortified Enterprise Fleet is a future expansion. Entering that track now would require production-grade identity, tenant isolation, durable agent runtime, registry, gateway, security controls and observability that are not yet demonstrated end to end.

## Current audit

### Strong foundations already present

- Chat-first patient experience with an integrated composer.
- Deterministic safety gates that remain active if Gemini fails.
- Typed longitudinal `PatientState`.
- Consent, quiet hours, snooze, rule muting, audit and export.
- Proactive clinical and continuity evaluators.
- Health missions, appointments, medication check-ins and consultation briefs.
- Google ADK specialist graph.
- Gemini 3.6 Flash integration.
- Cloud Run container and Firestore storage adapter.
- Android Health Connect bridge with device pairing and provenance.
- Synthetic hardware-free demonstration path.
- Clean semantic frontend and regression suite.

### Critical gaps preventing a winning claim

1. **The ADK graph is not the main production runtime.**
   The FastAPI application uses deterministic routing plus Gemini response enhancement, while `healthia_agent/agent.py` remains a separate graph. Judges need to see ADK selecting tools and completing the workflow used by the visible product.

2. **Autonomy is process-local.**
   The background loop runs inside the web process. Cloud Run may scale down or restart, so the current loop is not durable asynchronous execution.

3. **Most autonomous outcomes are messages, not completed external actions.**
   The agent detects and explains gaps but does not yet prove a closed loop such as: event received → plan created → tool executed → artifact produced → patient feedback captured → mission closed.

4. **Cloud proof is incomplete.**
   The repository contains Cloud Run and Firestore boundaries, but the submission still needs visible deployment evidence, logs, a hosted URL if possible and reproducible cloud setup.

5. **Multimodal proof is incomplete.**
   PDF and image uploads remain pending when verified extraction is unavailable. A winning demo should show Gemini reading a synthetic result image or PDF, extracting structured facts and preserving uncertainty/provenance.

6. **Identity and patient isolation are demonstration boundaries.**
   The current state store uses one synthetic patient document. A cloud demo needs at least two synthetic identities or a clearly isolated judge/demo account path.

7. **Observability is not judge-visible.**
   The audit log exists, but the demo needs a simple mission execution view showing trigger, selected agent/tool, public evidence, action result, retry/failure and closure without exposing private chain-of-thought.

8. **Submission evidence is not assembled.**
   The project still needs the final four-minute unedited video, cloud console proof, architecture diagram, hosted link, concise write-up and optional public content/social post.

## Estimated readiness by judging criterion

This is an internal planning estimate, not a judge score.

- Innovation and operational utility: **strong concept, medium proof**. The system removes real continuity friction, but must demonstrate a completed autonomous workflow.
- Architectural discipline and tech stack: **strong local architecture, incomplete cloud runtime**. Safety, state and boundaries are solid; durable event execution and ADK integration are the main gaps.
- Demo and production readiness: **good repository, weak final evidence**. Reproducibility exists, but cloud proof and the judge-facing story need completion.

## Winning demonstration: one closed-loop mission

Use one synthetic scenario from start to finish:

1. A Health Connect or synthetic device event reports persistently elevated blood pressure and reduced activity.
2. A Pub/Sub or Cloud Scheduler trigger invokes the Cloud Run mission worker.
3. The ADK coordinator receives the authorized patient state and deterministic safety result.
4. The coordinator selects the minimum tools:
   - longitudinal context;
   - safety gate;
   - mission planner;
   - consultation brief generator;
   - patient notification.
5. HealthIA creates a mission with evidence IDs, a next action and a closure condition.
6. HealthIA asks the patient for a repeat measurement using the correct technique.
7. The patient submits the measurement or the Android bridge synchronizes it.
8. HealthIA updates the trend, prepares a consultation brief and marks the mission ready for professional review.
9. The execution view shows every public step, tool result, retry and final state.
10. The demo closes with the patient controlling consent, muting the rule or exporting their data.

This proves autonomy, patient control, safety, memory, action and closure in one coherent story.

## Execution plan

### P0 — Must complete before submission

- [x] Replace the fragile Windows `python -c` Gemini probe with a UTF-8 Python verifier.
- [x] Explain Google, Samsung, Apple and OAuth connection models honestly in the device architecture.
- [ ] Make Google ADK execute the same mission workflow used by `/api/chat` and proactive checks.
- [ ] Add a durable cloud trigger using Pub/Sub, Cloud Scheduler or Cloud Tasks.
- [ ] Deploy Cloud Run with Firestore and Secret Manager configuration.
- [ ] Add a cloud verification script that records service URL, revision, project, Firestore write/read and Gemini model call.
- [ ] Implement one verified multimodal synthetic lab-result or discharge-document flow.
- [ ] Add a judge-visible mission execution timeline.
- [ ] Record a single unedited four-minute demo with Cloud Run dashboard/log evidence.
- [ ] Publish the final architecture diagram and exact spin-up instructions.

### P1 — High-value differentiators

- [ ] Native iOS HealthKit bridge prototype with synthetic/test data.
- [ ] Samsung-specific direct adapter only for data unavailable through Health Connect.
- [ ] Two synthetic patient identities with isolation tests.
- [ ] Structured ADK tool-result schema and retry policy.
- [ ] OpenTelemetry-compatible mission events and Cloud Logging correlation IDs.
- [ ] Patient feedback score that changes future plan preferences without changing clinical safety rules.
- [ ] Gemini multimodal comparison panel showing source image, extracted facts, uncertainty and provenance.

### P2 — Submission bonus work

- [ ] Public technical article describing the agent architecture and safety boundary.
- [ ] Public social post with `#AllThingsAgenticHackathon`.
- [ ] Optional Gemma component for local redaction/classification if it clearly improves the demo.

## Engineering gates

### Gate A — Local correctness

- Complete Python tests.
- JavaScript syntax checks.
- PowerShell parse and Windows launch test.
- Android debug APK build.
- Deterministic smoke test.

### Gate B — Real agent execution

- ADK trace proves tool selection and execution.
- Safety gate cannot be downgraded by the model.
- Mission has trigger, evidence, action, result and closure state.
- Failure path produces a retry or safe fallback.

### Gate C — Google Cloud proof

- Cloud Run revision visible.
- Firestore state survives restart.
- Secret is not committed or printed.
- Durable trigger invokes the mission worker.
- Cloud Logging shows one correlated end-to-end mission.

### Gate D — Judge proof

- Hosted URL or clearly reproducible private deployment.
- Architecture diagram.
- Four-minute unedited demo.
- README spin-up steps.
- Explicit truth boundary.
- No unsupported clinical or hardware claims.

## What not to do

- Do not present planned Apple, Samsung SDK, Fitbit or Garmin routes as implemented.
- Do not ask for Google, Samsung, Apple or wearable-provider passwords.
- Do not call a timed loop inside one web process “durable asynchronous execution.”
- Do not show internal chain-of-thought.
- Do not overfill the demo with every module; prove one mission deeply.
- Do not claim clinical diagnosis, regulatory clearance or validated medical-device performance.

## Definition of victory

HealthIA is submission-ready when a judge can watch one uninterrupted flow and answer “yes” to all of these questions:

1. Did Gemini and Google ADK make a real decision?
2. Did the agent execute tools instead of only producing text?
3. Did Google Cloud run and persist the workflow?
4. Did the action remove a real patient continuity burden?
5. Was the action safe, consent-bound and auditable?
6. Could another developer reproduce the project from the repository?
