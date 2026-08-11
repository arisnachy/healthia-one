# HealthIA ONE — Bonus Content Pack

These drafts are prepared for public publication but are **not** evidence that they have been published. Add the final public URLs to Devpost only after publication.

## Technical article draft

### From Health Chatbot to Durable Agent: Building HealthIA ONE with Gemini 3.5 + Google ADK

I created this piece of content for the purpose of entering the **All Things Agentic Hackathon**.

Most health AI demos begin with a prompt and end with an answer. HealthIA ONE started from a different question: what if the difficult part is not answering, but keeping the patient's unfinished health work from disappearing between conversations?

HealthIA ONE treats continuity as a durable Taskmaster mission. A patient can describe a problem naturally, upload evidence, return later, refer to what happened before, authorize a location-dependent step, choose among verified options, log out and come back without forcing the workflow to start from zero.

The core stack uses Gemini 3.5 Flash on Vertex AI, Google ADK, Cloud Run, Firestore, private Cloud Storage and Secret Manager. Google Places is invoked only after explicit mission-scoped location consent.

Three engineering decisions became especially important.

**Evidence before interpretation.** Clinical PDFs/images are stored first in private Cloud Storage. Only then does Gemini extract readable evidence into a bounded structured contract. If interpretation fails, the original evidence still exists and the result stays pending instead of being fabricated.

**Autonomy should stop at real human boundaries.** If a durable mission needs location, HealthIA does not silently continue. It stops, requests mission-scoped consent, then resumes the same mission after consent and performs real Places discovery.

**Not every user choice needs another LLM round.** Once verified candidates exist, a statement such as “The second one.” is a bounded deterministic choice. HealthIA applies the exact second candidate directly, reducing latency/cost and avoiding unnecessary reinterpretation.

The final Wave 3 laboratory also forced us to fix failures that ordinary local testing had not exposed: English clinical routing, model timeout behavior, recorder/UI drift, consent that failed to resume Places, Secret Manager wiring and deterministic candidate selection. A failure was never promoted as a pass; the final private one-take passed 15 semantic checks on a fresh Cloud Run process using the identical deployed product image.

The lesson was simple: production-minded agents need more than a tool call. They need durable state, provenance, bounded autonomy, human boundaries, safe failure and evidence that the action really happened.

HealthIA ONE's thesis is: **your health should not start over every time the chat does.**

Project repository: https://github.com/arisnachy/healthia-one

#AllThingsAgenticHackathon

---

## LinkedIn / X launch draft

I built **HealthIA ONE** for the #AllThingsAgenticHackathon: a patient-owned continuity agent built with **Gemini 3.5 Flash + Google ADK + Google Cloud**.

The goal is not another health chatbot. HealthIA carries a durable mission across turns: it preserves original evidence before interpretation, adapts clinical questions, resolves later references from persisted state, stops for mission-scoped location consent, performs real Google Places discovery after permission, applies the patient's exact verified choice, and preserves the outcome across logout/login.

Our Wave 3 private one-take ran on Cloud Run and passed **15/15 semantic checks**, including live Gemini + ADK, multimodal evidence persistence, a completed Taskmaster mission, fail-closed ambiguity, consent → real Places → exact candidate selection, continuity after relogin and zero browser console/page errors.

The design principle I care most about: **autonomous agents should know not only how to act, but exactly when they must stop and let a human decide.**

Repository: https://github.com/arisnachy/healthia-one

#GoogleCloud #Gemini #GoogleADK #AgenticAI #HealthAI #AllThingsAgenticHackathon

---

## Publication proof checklist

When either draft is actually published:

- preserve the final public URL;
- confirm it is public, not unlisted/private;
- retain the exact hackathon-purpose disclosure in the technical content;
- preserve `#AllThingsAgenticHackathon` in the social post;
- add only the verified public URL to the corresponding Devpost bonus field.
