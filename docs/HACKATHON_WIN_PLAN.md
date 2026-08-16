# HealthIA ONE — Hackathon Victory Plan

## Submission lock

HealthIA ONE is now in **winner-mode** for the All Things Agentic Hackathon 2026, Taskmaster category.

The submission thesis is deliberately narrow and memorable:

> **HealthIA does not stop when the model answers. It carries unfinished patient work forward, stops exactly at the human boundary, resumes the same durable mission after consent, and only claims completion when the real outcome exists.**

The verified Wave 4 lineage on `main` is the submission foundation. Experimental Wave 5 Guardian work remains quarantined until it has end-to-end LIVE receipts and may not be used to inflate submission claims.

## What the judge must understand in one viewing

```text
patient need
→ deterministic safety + authorized patient context
→ Gemini 3.5 Flash + Google ADK reasoning
→ original evidence preserved before interpretation
→ durable patient-scoped mission
→ every safe step the system can prove
→ explicit human boundary when required
→ same mission resumes after consent
→ real Google tool action
→ exact deterministic human choice
→ durable receipt / patient-visible outcome
```

HealthIA intentionally uses three kinds of intelligence:

1. **AI reasoning** when interpretation, multimodal understanding or planning is useful.
2. **Deterministic logic** when bounded intent must be exact.
3. **Human consent** when the decision belongs to the patient.

## Exact submission evidence

### Current Wave 4 tested product candidate

- SHA: `a48710eeb5a2e8429a91f5004129064e5af37c1a`
- full CI / JUDGE run: `31562277991` — SUCCESS
- real Google Places Wave 4 run: `31562277909` — SUCCESS
- Opportunity Autopilot run: `31562277915` — SUCCESS
- final judge-surface verification head: `213e3cd327a82775f0ff61afbd52dabcd6d32739` — SUCCESS
- final consolidated `main`: `eebe1a197a99fe4c5d424601fdf623a8248e345c`

The Wave 4 live resource-navigation proof verified:

- 0 external Places searches before mission-scoped location consent;
- 4 bounded real Places searches after consent;
- 9 deduplicated real candidates;
- 9/9 Google Maps URIs;
- 6 website URIs returned by Google;
- 9 phone numbers returned by Google;
- multiple resource families with preserved query/category provenance.

### Preserved full Google external-action LIVE proof

- Golden SHA: `891745e1ab93dc78b9aa4e54d65b315befa885f2`
- relationship: ancestor proof of the current Wave 4 lineage

Verified external loop:

```text
Safety
→ Mission Router
→ Google Places
→ Gmail send
→ Gmail users.watch
→ authenticated Pub/Sub push
→ Gmail users.history.list / exact thread correlation
→ Calendar FreeBusy
→ Calendar event create + reread
→ Google Task create + reread
→ durable receipts
→ COMPLETED
```

Authorization is not execution evidence. No external mutation may be presented as complete unless the real connector returned a durable outcome.

## The final judge video — continuous live application

The winning replacement must be a **continuous live application capture**, not a slide deck, screenshot montage, generated mockup, or post-hoc reconstruction.

### Scene 1 — The promise

Open the real HealthIA application and establish the problem in one sentence:

> A patient's health story should not restart every time the conversation ends.

Keep this under 15 seconds.

### Scene 2 — Human-first conversation

Use a synthetic English complaint. Show that:

- the patient begins naturally in chat;
- deterministic safety runs before routine model behavior;
- Gemini 3.5 Flash + Google ADK are active on the deployed runtime;
- adaptive questions use prior answers rather than restarting;
- the UI remains conversational rather than exposing an internal questionnaire contract.

### Scene 3 — Evidence first

Upload a synthetic clinical PDF/image and show the resulting patient-visible state.

Narrative:

1. original bytes are preserved first in private GCS;
2. Gemini performs bounded multimodal extraction;
3. Firestore stores patient-scoped structured state;
4. the clinical twin preserves provenance to the original document;
5. failure remains pending/fail-closed rather than manufacturing a finding.

### Scene 4 — The flagship Taskmaster mission

Ask HealthIA to find relevant real-world support nearby.

Before location consent, visibly prove:

- the durable mission exists;
- HealthIA identifies the missing human authorization boundary;
- **zero Google Places searches occur**.

Then authorize mission-scoped location.

The **same mission** must visibly resume and show real Google Places candidates.

### Scene 5 — Exact human choice

The patient says:

> **The second one.**

HealthIA must select exactly the second displayed candidate deterministically. No model round should reinterpret the bounded ordinal choice.

This scene is important because it demonstrates that the architecture does not confuse “more AI” with “better autonomy.”

### Scene 6 — Real action / real receipt

If the demo account is fully provisioned for the preserved external-action loop, show a genuine consent-authorized mutation and durable receipt from the real connector path.

Permitted LIVE path when genuinely provisioned:

```text
Gmail send
→ event-driven reply continuation through Pub/Sub + Gmail history
→ Calendar FreeBusy
→ Calendar event
→ Google Task
→ durable receipts
```

If any connector is not provisioned in the recording environment, do **not** simulate it as execution. Instead show the already-proven sanitized evidence map and keep the live demo centered on real Places + durable mission behavior.

### Scene 7 — Durable continuity

Log out and back in.

Confirm that relevant patient-scoped result/mission state remains available. End on the live product, not on slides.

Final sentence:

> **HealthIA does not win by talking longer. It wins by carrying unfinished health work forward and proving the outcome exists.**

## CUTLOCK — non-negotiable video gates

A replacement submission video is rejected unless all applicable gates pass:

1. exact candidate SHA is recorded and shown in machine evidence;
2. temporary deployment is bound to the exact revision/image;
3. live application only for the product journey;
4. English judge-facing narrative;
5. real Gemini/Vertex + Google ADK runtime where claimed;
6. synthetic patient data only;
7. original clinical evidence has provenance;
8. mission state is durable, not prompt-only;
9. zero Places before consent in the flagship flow;
10. real Places only after consent;
11. bounded ordinal selection is exact;
12. external mutations are only claimed with real receipts;
13. logout/login continuity is demonstrated where applicable;
14. browser console/page errors are zero;
15. video contains both video and intelligible audio;
16. duration stays inside the hackathon limit;
17. no unsupported diagnosis, prescribing, regulatory or clinical-effectiveness claim;
18. no experimental Wave 5 claim is promoted without LIVE proof.

## Public judge package

The judge-facing surface must stay aligned across:

- `README.md`
- `JUDGES_START_HERE.md`
- `docs/DEVPOST_SUBMISSION.md`
- `docs/WINNING_ONE_TAKE.md`
- `docs/GOOGLE_HEALTH_CONSTELLATION.md`
- `docs/BUILDING_HEALTHIA_ONE_ALL_THINGS_AGENTIC.md`
- Devpost published project description
- selected public video

No document may silently present an older Wave as the current product.

## Hosted-demo rule

A hosted judge URL is advertised only after anonymous/judge accessibility is explicitly verified. A Cloud Run service existing behind IAM is not enough to claim a public demo.

If a public judge service is created, it must keep:

- Cloud Run `min=0`, `max=1`;
- strict request budget;
- app-level patient authentication;
- synthetic/demo-only data;
- no secrets exposed to the browser;
- private evidence bucket;
- clear cleanup path after judging.

## Experimental quarantine

Wave 5 Autonomous Guardian remains outside the current submission until all of the following exist on an exact-head lineage integrated from the then-current `main`:

1. private Cloud Run/Eventarc LIVE Guardian wake proof;
2. controlled-device FCM proof from a genuine Guardian event with explicit authorization;
3. durable notification/delivery receipt;
4. real email adapter + exact authorization + receipt for any claimed email mutation;
5. continuous judge-visible autonomous moment that preserves the human-first UX;
6. full CI/LAB/JUDGE after integration.

**Promotion rule: no LIVE receipt, no submission claim.**

## Definition of victory

After watching once, a judge should be able to say:

> **“HealthIA is the patient continuity agent that turns evidence into durable missions, keeps working until it reaches a genuine human boundary, resumes after consent, acts through real Google tools, and preserves the outcome so the patient never starts over.”**

This document is intentionally modified on the final winner-demo branch to trigger the repository's exact-candidate live-demo workflow without altering application behavior.
