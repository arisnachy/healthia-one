# HealthIA ONE — Cost Control and Credit Preservation

## Security first

The promotional code, billing-account identifiers, API keys and service-account credentials must never be committed, pasted into issues, screenshots or demo recordings.

Use a dedicated Google Cloud project for the hackathon. Do not mix HealthIA testing with unrelated production resources.

## Three operating modes

### 1. Local safe — default

```powershell
.\deployment\run-local-secure.ps1
```

Properties:

- `HEALTHIA_LLM_BACKEND=mock`;
- no Google API key is requested;
- no Gemini or Vertex AI request is sent;
- local JSON state;
- deterministic clinical safety, interviews, UI and synthetic-device flows remain testable;
- the visible control reads `Local · 0 llamadas`.

Use this mode for normal development, UI work, regression tests, clinical-flow testing and demo rehearsal.

### 2. Guarded local AI

```powershell
.\deployment\run-local-secure.ps1 -GuardedAi -RequestLimit 10
```

The key is requested securely, but Google AI starts **off**. Open the cost-control pill in the top bar and activate it only for the messages that need a real model.

Optional flags:

```powershell
# Start enabled rather than requiring the UI switch.
.\deployment\run-local-secure.ps1 -GuardedAi -RequestLimit 10 -StartEnabled

# Spend one request immediately on a live readiness probe.
.\deployment\run-local-secure.ps1 -GuardedAi -RequestLimit 10 -LiveProbe

# Reduce maximum model output.
.\deployment\run-local-secure.ps1 -GuardedAi -RequestLimit 10 -MaxOutputTokens 500
```

Rules:

- every model request reserves one unit before contacting Google;
- failed or timed-out calls still count because provider work may have occurred;
- the switch turns off automatically when the process ceiling is reached;
- structured clinical interview blocks remain deterministic and do not consume a model call;
- proactive background checks are disabled in guarded AI mode;
- the limit is per process, not a dollar estimate and not a replacement for Cloud Billing controls.

### 3. Guarded Cloud demo

Prerequisites:

- dedicated Google Cloud project;
- billing linked to the promotional-credit account;
- Firestore enabled;
- Secret Manager secret containing the Gemini API key;
- low Cloud Billing budgets and eligible spend caps configured before deployment.

Deploy:

```powershell
.\deployment\deploy-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -SecretName healthia-gemini-api-key `
  -RequestLimit 20
```

The deployment helper enforces:

- Cloud Run minimum instances: `0`;
- Cloud Run maximum instances: `1`;
- request-based execution path;
- 512 MiB memory and one CPU;
- proactive in-process checks disabled;
- browser cost switch disabled in Cloud;
- a model-request ceiling and output-token ceiling;
- private service by default unless `-PublicDemo` is explicitly supplied.

The application limit is process-local and resets after a Cloud Run restart. It must be combined with Cloud Billing spend caps, budgets and service quotas.

After capturing the required proof:

```powershell
.\deployment\remove-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -ServiceName healthia-one-demo
```

For total cleanup of a project created only for this demo:

```powershell
.\deployment\remove-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -ServiceName healthia-one-demo `
  -DeleteSecret `
  -DeleteProject
```

Deleting only Cloud Run does not remove Firestore, Secret Manager, Artifact Registry or other project resources.

## Cloud Billing protection plan

### Dedicated project

Create one project exclusively for the hackathon. Scope every budget and spend cap to that project so unrelated services cannot consume the promotional credit unnoticed.

### Alerts-only project budget

Create a small project budget, for example USD 20, with alerts at 25%, 50%, 80% and 100%. This is an early-warning system, not a hard stop.

### Spend caps where available

Google Cloud currently offers spend caps in Preview for eligible services including Gemini API, the Vertex AI / Agent Platform service family, Cloud Run and Cloud Run functions.

A conservative starting plan is:

- Gemini API: USD 5 monthly spend cap;
- Cloud Run: USD 5 monthly spend cap;
- Vertex AI / Agent Platform: USD 5 monthly spend cap only if HealthIA uses it;
- project-wide alerts-only budget: USD 20.

Spend caps are based on gross estimated cost, not the promotional-credit net amount. Enforcement is not instantaneous, in-flight requests may finish, and persistent resources outside the capped service can continue to accrue cost.

### Quotas and rate limits

Set the lowest practical per-minute and daily API quotas for the demo project. Quotas reduce runaway request volume but are not a complete billing cap.

### Daily review

While Cloud resources exist:

1. Open Billing → Reports and filter to the HealthIA project.
2. Review service and SKU costs.
3. Review Cloud Run revisions and instance settings.
4. Review enabled APIs and quotas.
5. Delete unused revisions, images, secrets or the entire disposable project after evidence capture.

Billing data may be delayed, so do not wait for the report to stop an obviously runaway service.

## Judge evidence without keeping the app online

The hackathon permits proof that the project was built and deployed on Google Cloud without requiring it to remain live during judging. Capture in one recording:

- project and Cloud Run service;
- revision and scale settings;
- service URL or authenticated invocation;
- correlated Cloud Logging entry;
- Firestore persistence;
- one controlled Gemini request;
- cost-control panel showing remaining requests;
- cleanup command or deleted service after recording.

Do not display the API key, promotional code, billing account ID or secret value.

## Truth boundary

The in-app control protects against accidental model calls from one running process. Only Google Cloud billing controls, quotas, resource cleanup and account monitoring can protect the full project. No software switch can guarantee an exact zero-dollar overage because usage reporting and enforcement can be delayed.

Official references:

- Cloud Billing budgets: https://cloud.google.com/billing/docs/how-to/budgets
- Spend cap budgets: https://cloud.google.com/billing/docs/how-to/budgets-spend-caps
- Cloud Run minimum instances: https://cloud.google.com/run/docs/configuring/min-instances
- Cloud Run autoscaling: https://cloud.google.com/run/docs/about-instance-autoscaling
