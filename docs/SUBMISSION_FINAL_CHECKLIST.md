# HealthIA ONE — Final Submission Checklist

Purpose: prevent administrative or presentation losses after the product proof is already green.

## Official submission fields

- **Submitter type:** Individual (confirm before final submission if team status changes)
- **Country:** Dominican Republic
- **Category:** Taskmaster
- **Organization field:** use the entrant-appropriate value required by Devpost; do not invent an incorporated organization
- **Project start date:** repository and Devpost project were created on August 5, 2026 local time; confirm `08-05-26` as the entrant's truthful start date before final submit
- **Repository:** `https://github.com/arisnachy/healthia-one`
- **Reproducible README:** Yes
- **Google SDK:** Agent Development Kit (ADK), Google GenAI SDK
- **Google Cloud:** Cloud Run, Firestore (plus GCS/Secret Manager/Vertex documented in write-up where the dropdown is narrower)
- **Google AI models:** Gemini 3.5 Flash; do not claim Gemma/Veo/Lyria unless a real tested integration exists
- **Architecture diagram:** required file; use the Wave 3 evidence-first architecture artifact
- **Demo video:** required YouTube/Vimeo URL, approximately four minutes, with Google Cloud backend visibly demonstrated

## Judge-facing consistency gates

Before final submission, all three surfaces must tell the same truth:

1. Devpost write-up
2. repository README/evidence index
3. demo video

They must agree on:

- Taskmaster category;
- Gemini 3.5 Flash + ADK;
- Cloud Run + Firestore + private GCS;
- synthetic data only;
- no autonomous diagnosis/prescribing claim;
- evidence-first multimodal behavior;
- durable mission semantics;
- Wave 3 consent → Places → exact human choice flow;
- exact-source proof status;
- no claim that private proof automatically authorizes publication.

## Final video gate

A judge should be able to answer these questions after one viewing:

- What real patient friction is removed?
- What did the agent do rather than merely say?
- Where did it stop for human consent?
- Which Google services executed?
- What persisted after logout/login?
- How do we know the demo ran on Google Cloud?

If any answer is unclear, the video is not final.

## Evidence gate

Never replace a preserved passing artifact merely for cosmetic reasons. A replacement must be bound to an exact candidate and independently pass the corresponding runtime/browser/semantic gates.

## Bonus gate

Low-risk bonus points should be harvested before adding new product risk:

- public technical article created for the All Things Agentic Hackathon;
- public social post with `#AllThingsAgenticHackathon`;
- optional extra Google model only if useful, isolated and proven.

## Hard blockers before final submit

- [ ] YouTube/Vimeo demo URL populated in Devpost
- [ ] architecture diagram attached to required Devpost architecture field
- [ ] entrant/organization/start-date answers confirmed as truthful
- [ ] final submission status verified as Submitted (not merely a published project page)

Everything else should remain frozen unless a concrete judge-value defect is found.
