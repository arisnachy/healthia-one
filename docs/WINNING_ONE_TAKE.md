# HealthIA ONE — Winning One-Take (Wave 3)

This is the replacement-judge target for the final exact-head candidate. It does **not** invalidate the preserved passing video until this new take passes its own exact-head gate.

## North star

Do not demo a list of APIs. Demonstrate one patient-owned mission that begins in natural language, survives corrections and references, uses only verified evidence, advances autonomously through safe steps, stops at human authorization/external-event boundaries, and leaves a durable receipt.

## Scene 1 — Natural conversation and reference repair

Patient:

> “Quiero revisar el resultado que subí y después buscar dónde puedo llevar este seguimiento.”

After HealthIA responds, deliberately correct it:

> “No, me refería al resultado, no a mi presión.”

Then use an elliptical follow-up:

> “¿Y eso cambia lo que debo llevar a la cita?”

PASS requires the Conversation Brain to preserve the current correction, resolve the later pronoun from evidence-backed recent context, and never rewrite the patient's words. If the referent cannot be proven, HealthIA must ask one concise clarification instead of guessing.

## Scene 2 — Evidence-first clinical result

Upload one synthetic PDF/image.

PASS requires:

- original bytes persisted first in private GCS;
- Gemini/Document AI extraction only from readable evidence;
- structured patient-scoped Firestore result;
- clinical-twin provenance back to the original;
- no fabricated finding on extraction failure;
- original retrievable later.

## Scene 3 — Autonomous navigation mission

Patient:

> “Búscame un centro que pueda ayudar con este seguimiento en Santiago.”

HealthIA should create/advance a Google health mission and continue every safe/read-only step that is deterministically available. The patient should be able to continue naturally:

> “No, la segunda.”

or

> “Ese me sirve; continúa con eso.”

PASS requires the active durable mission to be recovered without forcing the patient to repeat its ID or restate the whole request.

## Scene 4 — Human authorization is visible, not hidden

When the next action is an external write (provider contact, Calendar event or follow-up Task), HealthIA must stop at the exact authorization boundary.

The message must visibly contain **Comprobante de misión** showing:

- verified steps actually executed;
- current durable mission state;
- whether human authorization is required;
- the next action;
- no claim that an external write happened when it was blocked.

After exact authorization is provided through the product's existing deterministic boundary, only the authorized payload may execute.

## Scene 5 — Event-driven continuation

If a provider reply is part of the take, it must be a real mission-linked external event or a clearly labeled synthetic deterministic fixture in a non-LIVE rehearsal. The final LIVE take must never fabricate a Gmail reply or poll continuously.

When a reply offers appointment slots, the patient can say:

> “La segunda me sirve.”

HealthIA should recover the mission, apply the exact offered slot selection, then stop again at the Calendar authorization boundary if required.

## Scene 6 — Durable close and continuity

After the permitted action succeeds:

- durable connector receipt exists;
- mission reaches the correct terminal/waiting state;
- Calendar/Task/Gmail resource identifiers are projected only from real connector outcomes;
- FCM may notify the physical Android only through the already-proven neutral-notification boundary;
- logout/login or a new request can recover the same mission state and evidence.

## Closing line

> “HealthIA does not win by talking longer. It wins by understanding what the patient means, doing every safe step it can prove, stopping exactly where a human must decide, and preserving the outcome so the patient never starts over.”

## Hard fail criteria

- stale topic overrides a current correction;
- an unresolved pronoun is guessed;
- a Google mission continuation is lost because the patient says “la segunda/ese/continúa”;
- model prose is presented as tool-execution proof;
- provider/contact/Calendar/Task write occurs without exact durable authorization;
- external reply is invented or obtained by permanent polling;
- receipt says an action succeeded without a durable connector outcome;
- real PHI, OAuth material, raw tokens, secrets or private credentials appear;
- any preserved provider LIVE PASS is regressed;
- exact final HEAD is not green before recording/publication.

## Final replacement rule

The old judge video remains the submission fallback until the Wave 3 exact-head candidate passes:

1. full CI + DialogBench + Chromium + LAB OMEGA + JUDGE OMEGA;
2. autonomous mission adversarial contract;
3. one continuous unedited Cloud take;
4. public video publication + anonymous SHA verification;
5. Devpost/README/EVIDENCE all pointing to the same exact candidate and video.
