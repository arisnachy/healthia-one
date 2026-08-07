# Identity, on-demand agents and the USD 50 safety envelope

## Why this direction wins

HealthIA should not pay for an agent merely because that agent exists. The chat is the universal entry point and the orchestrator activates specialist work only when it changes the next action, safety decision or evidence state.

The cost hierarchy is:

1. **No model call** when deterministic routing/safety can answer or when a background event has no useful work.
2. **One Gemini call** for a normal adaptive clinical question block or patient-facing enhancement.
3. **One bounded ADK mission** only for an actionable background event. The runtime may use at most two model calls in that single mission run.
4. Deterministic specialist tools execute after selection without independent LLM calls.

This avoids a 24/7 multi-agent swarm while preserving a real agentic architecture.

## Identity Platform setup

The cloud judge build supports:

- Continue with Google.
- Email/password account creation.
- Email/password login.
- Firebase/Identity Platform ID tokens verified by `firebase-admin` in FastAPI.
- Firestore documents keyed only by the immutable verified `uid`.
- Per-user SSE streams, audit events, uploads, devices and mission state.
- Device pairing tokens bound to the patient UID that created the pairing code.

### Console steps

1. Use the same Google Cloud project as HealthIA.
2. Add Firebase to the existing Cloud project or enable Identity Platform.
3. Register a **Web App**.
4. In Authentication / Identity Platform, enable:
   - Google provider.
   - Email/password provider.
5. Copy the public web config values:
   - `apiKey`
   - `authDomain`
   - `appId`
6. Add the final Cloud Run domain to authorized domains.
7. Deploy with:

```powershell
.\deployment\deploy-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -PublicDemo `
  -EnablePatientAuth `
  -FirebaseApiKey "PUBLIC_WEB_API_KEY" `
  -FirebaseAuthDomain "YOUR_PROJECT.firebaseapp.com" `
  -FirebaseAppId "WEB_APP_ID"
```

The Firebase web API key is a public project identifier used by the client SDK. The Gemini key remains a server secret in Secret Manager and must never be placed in the frontend.

## Isolation contract

An authenticated request is accepted only after the backend verifies the Firebase/Identity Platform ID token. The verified `uid` is placed in a request-scoped context. The Firestore adapter resolves:

```text
healthia_one_patients/{verified_uid}
```

No route accepts an email address or frontend-supplied patient ID as an authorization boundary.

The Android bridge uses a different path: the authenticated patient creates a six-digit pairing code, and the resulting device token is bound to that same UID. Future device syncs resolve the UID from the hashed device token before touching state.

The browser event stream captures the verified UID before returning its streaming response, so the stream cannot fall back to the synthetic/default scope after middleware completion. On sign-out the browser aborts that stream and clears patient-rendered lists from the DOM.

A public judge-facing Cloud Run service does not make the internal Pub/Sub mutation endpoint public. Pub/Sub sends an OIDC token from a dedicated push service account; HealthIA verifies the token audience and the exact service-account email before accepting the message.

### Automated isolation evidence

CI must prove all of the following without live Google credentials:

- two verified synthetic UIDs receive different state and cannot see each other's measurements;
- all stored records and audit entries inherit the verified UID;
- upload paths are patient scoped;
- pairing/device tokens resolve only to their owner UID;
- SSE subscribers are separated by patient scope;
- every patient-facing JavaScript module uses the single authenticated HTTP transport;
- an untrusted call to the internal Pub/Sub endpoint is rejected before payload processing.

## USD 50 global safety objective

The desired absolute ceiling for development and demo is **USD 50**, but Google Cloud billing data and spend-cap enforcement have latency. Therefore HealthIA uses a layered envelope rather than claiming an impossible exact dollar stop.

### Recommended controls

Before deploying, configure in Cloud Billing:

- Project-wide normal budget: **USD 45** with alerts before the target.
- Gemini API spend cap, when eligible: **USD 25**.
- Cloud Run spend cap, when eligible: **USD 10**.
- Keep at least USD 10–15 of the USD 50 envelope unallocated as latency/persistent-service buffer.

Spend caps are currently a Preview Cloud Billing feature and are service-specific. They can pause new usage for eligible services after the cap is enforced, but enforcement is not instantaneous and does not stop ongoing fixed/persistent resources. Firestore/storage and other non-eligible costs still require monitoring and cleanup.

### HealthIA's additional defenses

- Cloud Run minimum instances `0`.
- Maximum instances `1` for the hackathon demo.
- CPU throttling / request-based work.
- Scheduler is created **paused**.
- Process-local proactive polling is disabled in cloud.
- Non-actionable events do not invoke Gemini.
- Agents are selected on demand.
- The internal request counter remains only as a high emergency fuse, not as the main economic policy.
- Proof mode can temporarily use `-RequestLimit 6` for exactly three bounded ADK missions.
- `remove-cloud-demo.ps1` removes execution resources immediately after capture.

## Judge availability strategy

After strict cloud proof is captured:

1. Remove the proof resources.
2. Redeploy the judge build with Identity Platform enabled and Cloud Run scale-to-zero.
3. Keep Scheduler paused.
4. Keep agents demand-driven.
5. Leave only the authenticated web app available for judges.
6. Watch Billing alerts during the judging window.
7. If spend approaches the USD 45 working target, disable the public service before the USD 50 absolute objective is threatened.

The repository deliberately does not claim that an application-side counter can know the exact Google Cloud bill in real time.
