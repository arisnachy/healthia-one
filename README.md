# HealthIA ONE

**Your health never starts over.**

HealthIA ONE is a patient-owned health continuity operating system. Chat is the primary control surface, while a dynamic team of health agents organizes authorized longitudinal context, detects care gaps, explains patient-provided information, prepares safe next steps, and keeps health missions alive over time.

This repository is a clean hackathon implementation. The public demo uses a synthetic patient only.

## What the release candidate does

### Chat-first patient experience

- One conversational entry point for measurements, results, documents, treatment, appointments, family history, privacy and follow-up.
- An always-visible ChatGPT-style composer with attachment, voice dictation and quick actions.
- Contextual action buttons inside KIRA responses.
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
- HEREDITAS identifies family aggregation only to prepare preventive questions.
- Family patterns never become a diagnosis or a prediction that disease will occur.

### Patient document operating system

- Laboratory, imaging, prescription, consultation, discharge, vaccine, insurance, identity and other categories.
- Safe filename handling, allowlisted formats, size limits and patient-scoped local paths.
- Downloadable originals and an indexed archive.
- PDF and image files remain `pending_review` when verified multimodal extraction is unavailable. HealthIA does not invent unread content.

### Treatment and consultation continuity

- Structured medication plans and patient-reported check-ins: taken, late, skipped or unknown.
- MEDSAFE prevents dose changes, duplication, substitution or unsafe compensation advice.
- Appointments with specialty, location, required documents and questions.
- ADVOCATE generates a patient-controlled consultation brief from authorized data.

### Patient control and audit

- Signal-by-signal proactive permissions.
- Quiet hours, temporary snooze and reversible rule muting.
- Optional deterministic urgent-safety bypass.
- Public operational audit log without private model reasoning.
- Structured patient JSON export with internal storage paths removed.

## Agent team

KIRA activates the minimum useful specialist instead of running every agent for every message.

| Agent | Responsibility |
|---|---|
| KIRA Health | Coordinates the mission and final patient-facing response |
| HISTORIA | Longitudinal context and timeline |
| SENTINEL | Deterministic safety boundary and care urgency |
| LUMEN | Result and health-information explanation |
| VITA | Low-risk habits, barriers and micro-goals |
| NAVIGATOR | Missions, next steps and closure conditions |
| HEREDITAS | Pathological genogram and family-history context |
| ARCHIVUM | Patient document organization and provenance |
| MEDSAFE | Treatment organization and medication-safety boundary |
| ADVOCATE | Patient-controlled consultation preparation |
| BASTION | Consent, privacy, quiet hours and reversible controls |

The Google ADK application lives in `healthia_agent/agent.py`. The local FastAPI demo remains deterministic and usable without an API key; a real Gemini run is a separate configured execution path.

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

## Run locally on Windows

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\deployment\run-local-secure.ps1
```

Open `http://127.0.0.1:8000` and press `Ctrl+F5` after updating the repository.

## Run locally on macOS or Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
uvicorn app.main:app --reload --port 8000
```

## Optional Google ADK / Gemini configuration

Use a fresh secret in the local environment. Never commit or paste an API key into a repository, screenshot or chat.

```powershell
$env:HEALTHIA_LLM_BACKEND = "gemini_api"
$env:HEALTHIA_MODEL = "gemini-3.6-flash"
$env:GOOGLE_API_KEY = Read-Host -AsSecureString "Gemini API key"
```

The secure PowerShell launcher prompts for the key without storing it in a file and removes process variables when the server stops.

The web application's deterministic safety and continuity routes do not depend on a model call. A full Google ADK mission must be verified separately before claiming cloud AI execution.

## Verification

```bash
pytest
python -m compileall -q app healthia_one healthia_agent tests scripts
node --check web/app.js
node --check web/ui-v2.js
node --check web/ui-v3.js
node --check web/ui-v4.js
node --check web/ui-v5.js
python scripts/smoke_test.py
```

GitHub Actions repeats installation and verification in a clean Ubuntu/Python 3.12/Node 22 environment.

## Cloud Run

```bash
gcloud run deploy healthia-one \
  --source . \
  --region us-central1 \
  --set-env-vars HEALTHIA_ENV=cloud,HEALTHIA_STORE_BACKEND=firestore
```

The repository includes a Firestore state-store boundary, but a production deployment still requires:

- authenticated patient access and per-patient authorization;
- Firestore security rules and transaction/idempotency verification;
- private encrypted Cloud Storage for document bytes;
- Secret Manager;
- durable scheduling through Cloud Tasks or Pub/Sub;
- malware scanning and content validation;
- retention, deletion, export and incident-response policies;
- clinical, privacy, legal and independent security review.

A local green test suite is not proof of production safety or regulatory clearance.

## Demo paths

Useful chat requests:

```text
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

FastAPI exposes interactive API documentation at `/docs` while the service is running.

## Repository structure

```text
app/                 FastAPI gateway and static hosting
healthia_one/        contracts, safety, continuity, family, documents, consent and storage
healthia_agent/      Google ADK multi-agent application
deployment/          safe local and cloud launch helpers
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
