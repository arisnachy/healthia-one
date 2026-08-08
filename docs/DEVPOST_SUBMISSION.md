# HealthIA ONE — Devpost submission draft

> **Status:** judge-facing draft. Replace the two explicit placeholders only after the real Cloud strict proof and final unedited video exist. Do not convert unproven claims into marketing copy.

## Category

**The Taskmaster**

## Project URL

`[CLOUD_RUN_URL_AFTER_STRICT_PROOF]`

The hosted URL is added only after the exact deployed candidate passes `deployment/verify_cloud_demo.py`.

## Repository

https://github.com/arisnachy/healthia-one

## Demo video

`[FINAL_UNEDITED_4_MIN_VIDEO_URL]`

## One-line description

**HealthIA ONE is a patient-owned continuity agent that turns scattered health evidence into durable, verifiable missions instead of one-off chatbot answers.**

## The problem

Patients carry pieces of their health across laboratory PDFs, imaging reports, devices, prescriptions, appointments, family history and memory. A conventional chatbot can explain one item in one conversation, but it does not reliably preserve the original evidence, update longitudinal state, prove what action was completed, or recover the same evidence later under the same patient identity.

HealthIA ONE is designed around a different contract: **your health never starts over**. The patient owns a persistent state, and the agent team activates only when a goal requires work.

## What HealthIA ONE does

### Adaptive clinical conversation

A patient can describe a concern in natural language. Gemini 3.5 Flash and Google ADK generate five case-specific questions from the complaint, existing patient context and previous answers. Later blocks receive accumulated question/answer memory and avoid blindly repeating the first block. Gemini decides when another material question block is useful and when the system should stop asking and provide a patient-facing orientation.

The Google ADK runtime always includes interview and safety tools and selects at most two additional specialists for the current goal. Agent execution is demand-driven instead of a permanent background swarm.

### Closed-loop Taskmaster result mission

The central Taskmaster workflow is more than summarization:

1. the patient uploads a synthetic PDF/image;
2. HealthIA persists the original bytes before interpretation;
3. Gemini 3.5 Flash on Vertex AI performs multimodal extraction under a controlled JSON schema;
4. the structured result is committed to patient state;
5. the clinical twin is updated with provenance to the result and original document;
6. when the patient later asks about that study, HealthIA retrieves the exact persisted evidence;
7. the system returns the saved patient explanation and original link;
8. the mission becomes `COMPLETED` only when the persisted result really exists;
9. the completed mission carries `result_id`, `document_id` and explicit closure evidence;
10. the outcome survives logout/login and remains isolated from another authenticated synthetic patient.

A live GitHub Actions proof ran this flow with a **one-model-request ceiling**. After Gemini had extracted the PDF, HealthIA still completed the mission from durable state without spending a second model request just to paraphrase the same evidence.

### Patient-owned longitudinal state

HealthIA organizes synthetic patient information into a timeline and clinical twin spanning results, vitals, weight/activity, medication check-ins, appointments, family history, documents, missions and auditable events.

Original uploaded evidence remains independently retrievable rather than being replaced by model output.

### Identity and safety boundaries

- salted scrypt password hashes;
- signed HttpOnly sessions;
- patient-scoped Firestore/JSON/Memory state;
- patient-scoped documents, SSE and device ingestion;
- signed device credentials bound to patient + device + connection;
- deterministic safety boundary before agent reasoning;
- no autonomous prescribing or treatment changes;
- no fabricated multimodal interpretation when evidence cannot be read reliably.

## Technologies used

### Google AI and agents

- **Gemini 3.5 Flash**
- **Vertex AI** through Google Cloud ADC/service identity
- **Google Agent Development Kit (ADK)**
- **Google Gen AI SDK**
- structured multimodal output using JSON schema

### Google Cloud

- **Cloud Run** — FastAPI application runtime; scale-to-zero demo configuration
- **Firestore Native** — canonical patient/account/mission state in Cloud mode
- **Cloud Storage** — private original clinical evidence
- **Secret Manager** — application session/device signing secrets
- **Cloud Build** — source build using a dedicated build identity
- **IAM** — separate provisioning, build and runtime identities

The Cloud Run runtime does **not** receive a Gemini API key. It uses its Google Cloud service identity for Vertex AI.

### Application stack

- Python 3.12
- FastAPI
- Pydantic
- Playwright / Chromium E2E
- vanilla browser JavaScript/CSS
- Android Health Connect bridge contract

## Other data sources

The judge/demo environment uses **synthetic data only**. No real patient records or identifiers are required for the hackathon proof.

The product can accept patient-entered structured data and synthetic PDF/image evidence. The Android bridge defines the patient-bound contract for Health Connect-compatible activity/vitals data.

## Architecture

The full diagram and trust boundaries are documented in `docs/ARCHITECTURE.md`.

Core flow:

`Patient → Cloud Run/FastAPI → safety + demand-driven orchestrator → Google ADK / Gemini 3.5 Vertex → Firestore + private GCS → clinical twin/timeline → patient`

Build and runtime identities are separated. The build service account receives build-specific capability, while the Cloud Run runtime receives only the application permissions needed for Vertex AI, Firestore, evidence storage and application secrets.

## Evidence

### Live Vertex Taskmaster proof

- GitHub Actions run: `31228561751`
- candidate SHA: `d01c06fc40d074c15da4f43513aff32dd93060c9`
- project: `healthia-6088a`
- model: `gemini-3.5-flash`
- transport: Vertex AI / Google Cloud ADC
- model request ceiling: 1
- proof artifact id: `9012957895`

### Current deterministic release candidate

- candidate SHA: `fef8b2af898af3c0117c5a62fa57e476bdc9f560`
- GitHub Actions run: `31229957923`
- pytest: passed
- fourteen full-system workflows: passed
- Chromium E2E: passed
- compile/smoke/Judge/frontend/PowerShell checks: passed
- release ZIP verification: passed
- pytest from extracted release ZIP: passed
- release artifact id: `9013468149`

### Cloud deployment evidence

`[ADD_CLOUD_RUN_REVISION_AND_STRICT_PROOF_ARTIFACT_AFTER_GATE_PASSES]`

## Findings and learnings

### 1. Agentic value is easier to prove when completion is a state transition

A useful agent should not be judged only by how convincing its text looks. HealthIA missions therefore have explicit durable states and correlated evidence. The Taskmaster proof checks `COMPLETED`, result/document IDs and closure markers rather than accepting a good-looking answer.

### 2. Model calls and workflow completion should be decoupled

The one-request proof exposed an important design principle: Gemini should do the work that requires a model, while persisted state should handle later deterministic retrieval and completion. Re-calling an LLM to repeat saved evidence increases cost and makes an agent less reliable, not more agentic.

### 3. Original evidence must survive model interpretation

HealthIA stores uploaded bytes first and treats the model output as a derived interpretation. This keeps provenance available for later review and prevents the clinical twin from becoming an untraceable source of truth.

### 4. Demand-driven specialists are more useful than a permanent swarm

A fixed multi-agent swarm adds latency and cost even when a goal only needs two capabilities. HealthIA requires interview+safety for clinical questioning and selects only the additional specialists needed for the current case.

### 5. Cloud proof should be independent from deployment success

A successful `gcloud run deploy` command is not enough. HealthIA has a separate strict verifier that must demonstrate patient isolation, Vertex/ADK behavior, Firestore persistence, private GCS evidence and clinical-twin provenance on the deployed service.

## How to run

The README contains reproducible local and Cloud instructions.

Local mode defaults to zero model spend. The final hackathon Cloud architecture uses Gemini 3.5 Flash on Vertex AI with Google Cloud ADC.

## Safety / scope

HealthIA ONE is a synthetic hackathon release candidate. It is not a medical device, emergency service or autonomous prescription system. It does not claim clinical effectiveness, regulatory clearance or production security certification.

## Final recording plan

`docs/DEMO_SCRIPT.md` contains the approximately four-minute unedited sequence. The final take will show:

1. Cloud Run URL/revision and Vertex evidence;
2. live adaptive Gemini + ADK questioning;
3. real synthetic PDF upload;
4. original evidence + clinical twin update;
5. Taskmaster mission `COMPLETED`;
6. logout/login continuity and patient isolation;
7. matching Firestore and private GCS evidence;
8. architecture and green GitHub proof.
