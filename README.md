# HealthIA ONE

**Your health never starts over.**

HealthIA ONE is a patient-owned health continuity operating system. Chat is the primary control surface, while a dynamic team of health agents organizes authorized longitudinal context, detects care gaps, explains patient-provided information, prepares safe next steps, and keeps health missions alive over time.

This repository is a clean hackathon implementation. The public demo uses a synthetic patient only.

## What the release candidate does

### Chat-first patient experience

- One conversational entry point for measurements, results, documents, treatment, appointments, family history, privacy and follow-up.
- An always-visible ChatGPT-style composer with attachment, voice dictation and quick actions.
- Contextual action buttons inside HealthIA responses.
- Structured two-stage clinical interviews with five questions per block.
- Server-Sent Events for asynchronous interventions without a new patient message.

### Longitudinal patient record

- Confirmed conditions, allergies and registered treatment.
- Blood pressure and other vitals, weight and activity.
- Structured result uploads and plain-language explanations.
- Unified health timeline across measurements, results, documents, medication check-ins, appointments and missions.
- Condition Packs for hypertension and weight management.

### Pathological genogram

- Multi-generation maternal and paternal family lines.
- Biological relationship, sex at birth, condition, age at diagnosis, verification and provenance.
- The family-history module identifies aggregation only to prepare preventive questions.
- Family patterns never become a diagnosis or a prediction that disease will occur.

### Patient document operating system

- Laboratory, imaging, prescription, consultation, discharge, vaccine, insurance, identity and other categories.
- Safe filename handling, allowlisted formats, size limits and patient-scoped local paths.
- Downloadable originals and an indexed archive.
- PDF and image files remain `pending_review` when verified multimodal extraction is unavailable. HealthIA does not invent unread content.

### Treatment and consultation continuity

- Structured medication plans and patient-reported check-ins: taken, late, skipped or unknown.
- The treatment-safety module prevents dose changes, duplication, substitution or unsafe compensation advice.
- Appointments with specialty, location, required documents and questions.
- The consultation module generates a patient-controlled brief from authorized data.

### Patient control, audit and spending safety

- Signal-by-signal proactive permissions.
- Quiet hours, temporary snooze and reversible rule muting.
- Optional deterministic urgent-safety bypass.
- Public operational audit log without private model reasoning.
- Structured patient JSON export with internal storage paths removed.
- Zero-spend local mode by default.
- Visible Google AI on/off switch with a hard request ceiling per process.
- Model output-token ceiling and low-thinking configuration.
- Guarded Cloud Run deployment and explicit cleanup scripts.

## Internal agent architecture

The runtime activates the minimum useful specialist instead of running every module for every message. Internal implementation names are documented for maintainers but are never exposed in the patient-facing interface.

The Google ADK application lives in `healthia_agent/agent.py`. HealthIA now also has a bounded background mission runtime in `healthia_one/adk_runtime.py`: authorized events can travel through Pub/Sub, be decided by Google ADK, validated against deterministic safety, execute one bounded mission tool, persist evidence in Firestore and emit a correlation trace. The local FastAPI demo remains deterministic and usable without an API key.

## Clinical truth boundary

HealthIA ONE is not a physician, emergency service, prescription engine or autonomous diagnostic system.

It may:

- organize patient-entered information;
- detect deterministic thresholds and missing follow-up;
- explain what a result measures and what it does not prove;
- generate questions for a professional;
- maintain patient-controlled health missions;
- recommend an appropriate level of human care.

It may not:

- confirm a diagnosis;
- prescribe, stop, duplicate or change medication;
- declare a dangerous situation safe;
- predict that a hereditary disease will occur;
- sign clinical orders or replace professional evaluation.

Do not upload real patient identifiers or clinical records to the public hackathon environment.

## Run locally on Windows — zero spend by default

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\deployment\run-local-secure.ps1
```

This default mode does not request an API key and sends zero calls to Google AI. Open `http://127.0.0.1:8000` and press `Ctrl+F5` after updating the repository.

## Run locally on macOS or Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock \
HEALTHIA_COST_MODE=local \
HEALTHIA_AI_REQUEST_LIMIT=0 \
uvicorn app.main:app --reload --port 8000
```

## Guarded Google Gemini testing

To load a Gemini key while keeping model calls off until you explicitly enable them:

```powershell
.\deployment\run-local-secure.ps1 -GuardedAi -RequestLimit 10
```

The top bar shows one of these states:

- `Local · 0 llamadas`;
- `IA apagada · N restantes`;
- `IA activa · N restantes`.

Open the control to switch Google AI on or off, inspect remaining requests and spend exactly one request on a live probe. The guard reserves a request before contacting Google, counts failed attempts, turns off automatically at the ceiling and never claims to estimate exact dollars.

Optional guarded commands:

```powershell
# Start with Google AI enabled.
.\deployment\run-local-secure.ps1 -GuardedAi -RequestLimit 10 -StartEnabled

# Spend one request during startup on a real API probe.
.\deployment\run-local-secure.ps1 -GuardedAi -RequestLimit 10 -LiveProbe

# Reduce output length further.
.\deployment\run-local-secure.ps1 -GuardedAi -RequestLimit 10 -MaxOutputTokens 500
```

The key is held only in the launcher process and removed when the server stops. The cost switch can only be changed from localhost; a public visitor cannot activate model spending.

See [`docs/COST_CONTROL.md`](docs/COST_CONTROL.md) for budgets, spend caps, quotas, scale-to-zero deployment and cleanup policy.

The device page provides a real six-digit pairing flow for the Android bridge plus a synthetic path for demonstrations without hardware. A phone must use the computer's LAN address rather than `127.0.0.1`.

## Verification

```bash
pytest
python -m compileall -q app healthia_one healthia_agent tests scripts deployment/verify_google_ai.py
node --check web/app.js
node --check web/patient-record.js
node --check web/family-documents.js
node --check web/continuity.js
node --check web/privacy-controls.js
node --check web/profile-devices.js
node --check web/icons.js
node --check web/clinical-council.js
node --check web/cost-control.js
python scripts/smoke_test.py
python scripts/judge_omega.py
```

GitHub Actions repeats installation and verification in a clean Ubuntu/Python 3.12/Node 22 environment.

## Guarded Google Cloud agentic demonstration

Use a dedicated hackathon Google Cloud project. The deployment helper creates the low-spend proof path: private Cloud Run, Firestore, Secret Manager, Pub/Sub authenticated push and a Cloud Scheduler job that is **paused immediately**.

```powershell
.\deployment\deploy-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -FirestoreLocation us-central1 `
  -RequestLimit 6 `
  -MaxOutputTokens 350
```

The cloud runtime uses minimum instances `0`, maximum instances `1`, request-based CPU and no process-local proactive loop. An actionable ADK mission reserves the complete two-model-call worst-case budget before it starts; a non-actionable event uses zero Gemini calls.

Capture one strict real proof:

```powershell
.\deployment\capture-cloud-proof.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -ServiceName healthia-one-demo
```

A passing proof requires three real Google ADK mission runs with no fallback: one Cloud Scheduler background task and a two-event follow-up that reaches a persisted `completed` state. The script rejects missing Firestore/Pub/Sub/ADK, an incomplete trace or more than six reserved model calls and writes sanitized evidence to `dist/cloud-proof/`.

Then stop the execution resources:

```powershell
.\deployment\remove-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -ServiceName healthia-one-demo
```

See [`docs/CLOUD_AGENTIC_PROOF.md`](docs/CLOUD_AGENTIC_PROOF.md) for the exact evidence contract and [`docs/SUBMISSION_PACKAGE.md`](docs/SUBMISSION_PACKAGE.md) for the four-minute judge path.

The per-process request ceiling resets when Cloud Run starts a new instance. It must still be combined with Cloud Billing budgets/alerts, quotas and immediate resource cleanup. See [`docs/COST_CONTROL.md`](docs/COST_CONTROL.md).

Production beyond the hackathon still requires authenticated multi-patient isolation, hardened Firestore authorization, private encrypted object storage for document bytes, malware scanning, retention/deletion policy, clinical validation and independent privacy/security/legal review.

A green test suite or a successful hackathon demo is not proof of production safety or regulatory clearance.

## Demo paths

Useful chat requests:

```text
Desde ayer me arde al orinar y tengo que ir al baño a cada rato.
Muéstrame mi genograma y los patrones familiares que debo discutir con mi médico.
Organiza mis documentos del expediente.
Muéstrame mi tratamiento y las tomas registradas.
Prepara mi próxima consulta.
Enséñame mi línea de salud.
Quiero revisar mis permisos, auditoría y exportar mis datos.
```

See `docs/DEMO_SCRIPT.md` for the complete judge-facing flow.

## API highlights

- `/api/chat`
- `/api/cost-control` and `/api/ai/test`
- `/api/vitals`, `/api/weight`, `/api/activity`
- `/api/results/upload`
- `/api/family`
- `/api/documents` and `/api/documents/upload`
- `/api/timeline`
- `/api/treatment` and `/api/treatment/checkins`
- `/api/appointments`
- `/api/consultation-brief`
- `/api/consent`, `/api/consent/snooze`, `/api/consent/mute`
- `/api/audit`
- `/api/export`
- `/api/events/stream`
- `/api/judge/mission-runs` and `/api/judge/trace/{correlation_id}`
- `/api/internal/pubsub/mission` (private Cloud Run push target)

FastAPI exposes interactive API documentation at `/docs` while the service is running.

## Repository structure

```text
app/                 FastAPI gateway and static hosting
healthia_one/        contracts, safety, continuity, cost guard, consent and storage
healthia_agent/      Google ADK multi-agent application
deployment/          safe local, guarded cloud and cleanup helpers
demo/                synthetic fixtures
docs/                architecture, safety, controls and demo documentation
scripts/             end-to-end smoke verification
web/                 chat-first patient interface
tests/               deterministic regression and API tests
```

## Source disclosure

Product ideas, visual requirements and patient-flow lessons were informed by a private HealthIA v270 ZIP supplied by the project owner. The old codebase and its history were not imported. This repository is a new clean implementation, and no claim is made that pre-existing HealthIA work was created during this hackathon.

## Android devices and complete patient profile

The current release candidate includes a Health Connect ingestion contract, an Android companion source project, a complete patient profile, structured medication organization, pregnancy/postpartum context, BMI calculation, and device/medication cross-checks. See [`docs/ANDROID_HEALTH_AND_PATIENT_PROFILE.md`](docs/ANDROID_HEALTH_AND_PATIENT_PROFILE.md).

Hardware truth boundary: CI proves models, APIs, idempotency, UI contracts, and the Android source contract. It does not prove a physical watch or medical device until the bridge is installed and exercised on a compatible Android device with the required permissions.
