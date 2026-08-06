# HealthIA ONE

**Your health never starts over.**

HealthIA ONE is a patient-owned health continuity system. The chat is the main interface, while a small team of health agents maintains longitudinal context, checks authorized signals, explains results, prepares safe next steps, and follows active health missions over time.

## What exists in this first vertical slice

- Chat-first patient interface inspired by the privately supplied HealthIA v270 product requirements.
- Patient timeline with vitals, weight, activity, uploaded results, and active missions.
- Proactive asynchronous checks for missing measurements, material weight change, low activity, unreviewed results, and high blood pressure.
- Explainable messages that state what was detected, why it matters, what is missing, and the safest next action.
- Dynamic public agent plan: HISTORIA, SENTINEL, LUMEN, VITA, NAVIGATOR, BASTION, and KIRA.
- Server-Sent Events so background agent messages appear without refreshing or sending a new prompt.
- Safe upload path for JSON, CSV, and TXT lab/result files; PDF and images are accepted as pending multimodal review.
- Deterministic safety boundary for urgent symptoms and extreme vital values.
- Optional Google ADK agent app using Gemini; the local demo works in mock/deterministic mode without an API key.
- JSON persistence locally and an explicit Firestore production adapter boundary.
- Cloud Run container and CI.

## Clinical boundary

HealthIA ONE is not a medical device, emergency service, physician, prescription engine, or autonomous diagnostic system. It can organize patient-provided information, identify deterministic thresholds, explain data, generate questions, and recommend an appropriate level of human care. It does not confirm diagnoses or change treatment.

Use synthetic data for the hackathon demo. Do not upload real patient identifiers or clinical records to the public demo.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[test]"
uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000`.

The demo boots with a synthetic patient and runs a proactive check every 20 seconds. Press **Run agent check** to trigger it immediately.

## Run the Google ADK agent

Set a fresh key only in your local environment; never commit or paste it into chat:

```bash
export HEALTHIA_LLM_BACKEND=gemini_api
export GOOGLE_API_KEY="..."
```

Then use the ADK/Agents CLI against `healthia_agent/agent.py`. The model defaults to `gemini-3.6-flash` and can be changed with `HEALTHIA_MODEL`.

## Tests

```bash
pytest
node --check web/app.js
```

## Cloud Run

```bash
gcloud run deploy healthia-one --source . --region us-central1
```

For production, use Secret Manager, Firestore, authenticated access, and a private data policy. The public hackathon deployment must stay synthetic.

## Source disclosure

This repository is a new, clean implementation created for the hackathon. Product ideas, visual requirements, and patient-flow lessons were informed by a private HealthIA v270 ZIP supplied by the project owner. The old codebase and its history were not imported. No claim is made that pre-existing HealthIA work was created during this hackathon.

## Repository structure

```text
app/                 FastAPI service and static hosting
healthia_one/        contracts, storage, safety, proactive engine, orchestration
healthia_agent/      Google ADK multi-agent application
demo/                synthetic result file
docs/                architecture and clinical safety contracts
web/                 chat-first patient interface
tests/               deterministic regression tests
```
