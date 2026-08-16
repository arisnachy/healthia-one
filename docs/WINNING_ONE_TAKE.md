# HealthIA ONE — Final Winning One-Take (Wave 4)

This is the **replacement-judge contract**, not permission to publish an unverified recording. The currently submitted video remains the fallback until a new exact-head take passes its own CI, Cloud, browser and publication gates.

## North star

**Do not demo a list of APIs. Do not end with slides. Do not narrate architecture that the judge cannot see happening.**

Demonstrate one patient-owned mission that:

1. starts in ordinary language;
2. uses evidence instead of inventing context;
3. becomes durable state;
4. advances safe work autonomously;
5. visibly stops at the human boundary;
6. resumes the **same mission** after consent;
7. performs a real Google action;
8. leaves a durable receipt/outcome that survives the session.

The judge should understand the product even with the audio muted.

## Target structure — approximately four minutes

### 0:00–0:20 — Problem + promise, inside the real app

Show the Cloud Run application immediately. No title-card sequence.

Overlay/narration:

> A patient's health story is fragmented across chats, results, appointments, devices and support systems. HealthIA turns unfinished health work into a durable mission. Your health never starts over.

Visible proof before moving on:

- real HealthIA UI;
- `.run.app` runtime or equally explicit Google Cloud runtime evidence;
- synthetic patient only.

### 0:20–0:55 — Evidence and conversation intelligence

Use a short natural interaction that establishes the distinction between memory and hallucination.

First deliberately use an unanchored reference:

> “What about that?”

PASS: HealthIA asks for clarification and does not manufacture an antecedent.

Then establish a real result/evidence context. The interaction may use a compact clinical request or proceed directly to the synthetic result upload if time is tight.

The point is not to impress with long medical prose. The point is to show **bounded reasoning**.

### 0:55–1:25 — Evidence-first multimodal result

Upload one synthetic PDF/image.

PASS requires:

- original bytes persisted first in private GCS;
- Gemini 3.5 Flash on Vertex AI extracts only readable evidence;
- structured patient-scoped result persists in Firestore;
- clinical-twin provenance links back to the original;
- no fabricated finding on extraction failure;
- original remains retrievable later.

Show the persisted result briefly. Do not spend the demo reading the interpretation.

### 1:25–2:35 — Flagship Taskmaster mission: support → boundary → real Places

This is the center of the demo.

Patient:

> “Find autism support groups and community resources near Santiago de los Caballeros.”

PASS before consent:

- HealthIA creates/recovers a durable Google mission;
- location authorization is explicitly required;
- **zero external Places searches** have executed;
- the UI makes the human boundary visible instead of hiding it in narration.

Patient:

> “I authorize my location for this mission.”

PASS after consent:

- the **same mission** resumes;
- real Google Places discovery executes;
- verified candidate cards appear with real names/addresses/Maps links and only fields Google actually returned;
- no provider referral or eligibility claim is invented.

This transition — **no action → human consent → autonomous real action** — must be visually unmistakable.

### 2:35–2:55 — Exact human choice without another LLM guess

Patient:

> “The second one.”

PASS:

- the active mission is recovered without asking for a mission ID;
- exactly the second displayed candidate is selected;
- the bounded ordinal choice is deterministic;
- the mission receipt updates.

This scene differentiates HealthIA from systems that use an LLM for every trivial state transition.

### 2:55–3:30 — Real external-action proof

**Preferred final take:** continue the same authorized mission through the already-proven Google connector path when the demo account is provisioned for it:

```text
selected resource
→ exact external-write authorization
→ Gmail send
→ event-driven Gmail reply / Pub/Sub
→ Calendar FreeBusy
→ exact slot selection
→ Calendar authorization
→ Calendar event
→ Google Task
→ durable receipts
```

Every mutation must be backed by the real connector outcome. Gemini cannot self-authorize a write.

If the recording environment cannot safely provision the real Google account for the fresh synthetic patient, **do not fake this scene**. Instead keep the Wave 4 Places mission as the live one-take and show the preserved Google Health Constellation LIVE evidence only through a truthful in-product/evidence view or a clearly labeled proof reference. Never splice a simulated external write into a LIVE claim.

### 3:30–3:50 — Continuity survives logout/login

Logout and log back in.

PASS requires recovery of the same patient-scoped state, including at minimum:

- persisted result and original-document relationship;
- completed/open Taskmaster mission state as appropriate;
- selected Google resource;
- durable receipt/provenance.

The judge should see that continuity does not live in a browser variable or prompt window.

### 3:50–4:05 — Google Cloud proof + closing line

Show a concise exact-candidate runtime proof:

- candidate SHA;
- Cloud Run URL/revision;
- Gemini 3.5 Flash;
- ADK ready;
- Firestore state backend;
- GCS evidence backend.

Close on the live product, not a PowerPoint:

> **HealthIA does not win by talking longer. It wins by doing every safe step it can prove, stopping exactly where a human must decide, and preserving the outcome so the patient never starts over.**

## What the video must make obvious

A judge should be able to answer **yes** to all of these without reading the repository:

- Is this more than chat?
- Did a real multi-step mission exist?
- Did the agent perform real external read/action work?
- Did it stop before a sensitive/human decision?
- Did the same mission resume afterward?
- Was the patient's exact choice preserved?
- Did the outcome survive logout/login?
- Is Google Cloud visibly running the backend?
- Is evidence distinguished from model prose?

## Hard fail criteria

- static slides replace the live product for a material part of the demo;
- stale topic overrides a current correction;
- an unresolved pronoun is guessed;
- a Google mission continuation is lost because the patient says “the second one / la segunda / ese / continúa”;
- Places executes before mission-scoped location consent;
- model prose is presented as tool-execution proof;
- provider/contact/Calendar/Task write occurs without exact durable authorization;
- an external reply is invented or obtained by permanent polling;
- a receipt says an action succeeded without a durable connector outcome;
- real PHI, OAuth material, raw tokens, secrets or private credentials appear;
- a prior LIVE PASS is regressed or silently reinterpreted;
- exact final HEAD is not green before recording/publication;
- Devpost, repository and published video point to different product stories.

## Replacement gate

The existing public judge video remains the fallback until the new candidate satisfies **all** of the following:

1. full pytest + full-system check + DialogBench + Chromium + JUDGE Ω;
2. Wave 4 location-consent / real-Places / ordinal-selection contract;
3. preserved Google action-loop regression contracts;
4. one continuous unedited Cloud take;
5. duration near the hackathon's ~4-minute target;
6. zero browser console/page errors;
7. public video publication and anonymous byte/SHA verification;
8. Devpost + `README.md` + `JUDGES_START_HERE.md` + evidence index aligned to the same exact candidate and video.

**No gate is lowered to make the replacement pass.**
