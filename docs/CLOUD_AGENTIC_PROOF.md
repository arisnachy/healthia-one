# Controlled Google Cloud proof

This procedure is intentionally small. Its purpose is to create judge-grade evidence while protecting the hackathon credit balance.

## What a passing proof demonstrates

One execution package must show all of the following on the **same deployed service**:

1. Cloud Run revision exists and is private by default.
2. Firestore is the active state backend.
3. Pub/Sub is the durable event dispatcher.
4. Google ADK is the active mission runtime.
5. Gemini 3.6 Flash is configured.
6. Cloud Scheduler publishes one background event.
7. The scheduled event completes a consultation-preparation mission and persists an artifact.
8. A high synthetic blood-pressure event opens a follow-up mission.
9. A second synthetic event satisfies the closure condition and completes the mission.
10. Every live mission run reports `runtime=google_adk`.
11. The final trace contains `trigger`, `decision`, `tool`, `persistence`, and `closure`.
12. The total reserved model-call budget is no more than six.

Synthetic clinical inputs are deliberate. The proof is about agent architecture and autonomous workflow, not medical efficacy.

## 1. Deploy

From the repository root in PowerShell:

```powershell
.\deployment\deploy-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -FirestoreLocation us-central1 `
  -RequestLimit 6 `
  -MaxOutputTokens 350
```

The helper:

- enables only the required APIs;
- creates dedicated runtime and Pub/Sub push service accounts;
- creates Firestore if the default database is absent;
- stores the Gemini key in Secret Manager if it is not already present;
- deploys Cloud Run with min `0`, max `1` and request-based CPU;
- creates the Pub/Sub topic and authenticated push subscription;
- creates Cloud Scheduler but **pauses it immediately**;
- prints the Cloud Run URL and exact proof command.

Do not use `-PublicDemo` for the evidence run unless there is a specific reason. Private Cloud Run plus an identity token is cleaner and safer.

## 2. Capture one bounded real proof

```powershell
.\deployment\capture-cloud-proof.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -ServiceName healthia-one-demo `
  -SchedulerName healthia-agentic-tick
```

The script fails rather than accepting weak evidence. It rejects the proof when:

- Firestore, Pub/Sub or ADK is not active;
- fewer than six model-call slots remain;
- any live run falls back from Google ADK;
- the scheduler mission does not produce an artifact and close;
- the measurement mission does not move `waiting_patient → completed`;
- the final trace lacks a required stage;
- the observed reserved model-call count exceeds six.

A successful run writes only sanitized evidence under:

```text
dist/cloud-proof/
  healthia-cloud-proof.json
  cloud-run-service.json
  firestore-database.json
  cloud-scheduler-job.json
  cloud-run-agentic-logs.json
```

No API keys or identity tokens are written to these files.

## 3. Capture the visual evidence for the video

Before deleting the service, record a short continuous pass showing:

- Cloud Run service and ready revision;
- the `.run.app` URL;
- Pub/Sub topic/subscription;
- Firestore database;
- Cloud Scheduler job and the manual run;
- HealthIA Misiones → **Ejecuciones autónomas verificables**;
- a `Google ADK` run with a closure stage;
- Cloud Logging lines containing the same correlation ID.

Do not show Secret Manager values, API keys, access tokens, billing identifiers or private medical data.

## 4. Stop spend immediately

```powershell
.\deployment\remove-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -ServiceName healthia-one-demo
```

The normal cleanup removes Cloud Run, Pub/Sub and Scheduler. It deliberately keeps Firestore and the secret unless explicitly asked, because they may be needed as evidence.

For maximum cleanup after the submission is safely captured, use a dedicated hackathon project and delete that project.

## Truth boundary

A green GitHub Actions run does not count as this cloud proof. The hard gate moves to proven only after the generated `healthia-cloud-proof.json` from a real Google Cloud project is inspected and its correlated evidence is retained.
