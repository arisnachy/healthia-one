# Building HealthIA ONE: From Health Chat to Durable Agentic Work

> **This article was created for the purposes of entering the All Things Agentic Hackathon 2026.**

HealthIA ONE started from a simple healthcare problem: a patient's story is scattered across conversations, laboratory reports, images, medications, appointments, devices, support organizations, and public assistance programs. Traditional chat systems can answer a question about one fragment, but the unfinished work usually disappears when the conversation ends.

We built HealthIA ONE around a different idea: **continuity itself should be the workflow**.

HealthIA ONE is a patient-owned continuity agent in the Taskmaster category. Its job is not merely to generate medical text. It preserves evidence, maintains durable patient-scoped missions, stops when human permission is required, resumes the same mission after consent, and uses real Google services to move work forward.

## The core design

The system deliberately combines three kinds of decision-making:

1. **AI reasoning** when interpretation, multimodal understanding, or planning is valuable.
2. **Deterministic logic** when the answer must be exact, such as selecting the second candidate a patient was shown.
3. **Human consent** when the decision belongs to the patient.

That separation became one of the most important lessons of the project. More autonomy is not always better autonomy. A useful agent must know when it can act, when it must stop, and how to resume without losing the original mission.

## Google architecture

HealthIA ONE uses:

- **Gemini 3.5 Flash on Vertex AI** for reasoning and bounded multimodal understanding;
- **Google Agent Development Kit (ADK)** for demand-driven agent execution;
- **Google GenAI SDK**;
- **Cloud Run** for the application runtime;
- **Firestore** for durable patient and mission state;
- **private Google Cloud Storage** for original clinical evidence;
- **Secret Manager** for sensitive configuration;
- **Google Places / Maps Platform** for consent-authorized real-world resource discovery.

The Cloud path uses service identity / ADC rather than embedding a Gemini key in the application runtime.

## Evidence first, interpretation second

When a synthetic clinical PDF or image is uploaded, HealthIA preserves the original bytes before model interpretation. Gemini then performs bounded multimodal extraction, and structured findings are linked back to the original evidence.

If the evidence cannot be interpreted reliably, the workflow fails closed. HealthIA does not invent a finding just to keep the interaction moving.

That evidence boundary also applies to longitudinal references. A phrase such as “that result” must resolve to durable evidence. If the reference is ambiguous, HealthIA should admit uncertainty rather than attach new reasoning to the wrong event.

## Durable missions instead of prompt memory

A HealthIA mission is not complete because a language model generated a convincing paragraph. The requested outcome has to exist in durable state.

Mission state, evidence, patient decisions, and selected resources survive logout/login. The state belongs to the patient context rather than to one prompt window.

This distinction became central to the demo: **persistence is not the same thing as prompt memory**.

## The human boundary

One of the strongest Taskmaster flows occurs when HealthIA needs location to find real-world support.

The agent stops before calling Google Places. It explains why location is needed and asks for mission-scoped consent. Before authorization, the verified LIVE proof records **zero external Places searches**.

After the patient agrees, HealthIA resumes the same durable mission and performs bounded real Google Places discovery.

The exact Wave 4 LIVE proof returned nine deduplicated real candidates across care, community support, government/financial support, and general support-resource categories. All nine had Google Maps URIs.

## “The second one.”

After candidates are displayed, the patient can say:

> The second one.

That bounded choice does not need another language-model interpretation. HealthIA deterministically selects exactly the second visible candidate and persists that choice inside the mission.

This reduces latency and cost while protecting exact human intent.

## Opportunity Autopilot

HealthIA also contains an evidence-bounded opportunity layer for scientific and practical support.

It can maintain patient/family watch topics, discover scientific opportunities from sources such as PubMed/NLM, Europe PMC, and ClinicalTrials.gov, and surface assistance-program candidates.

Program requirements are not treated as known simply because an AI found a program. Requirements must be verified against an official source. Eligibility remains `MATCHED`, `UNMET`, or `UNKNOWN`, and missing documents are represented separately.

Application state can be prepared for human review, but HealthIA does **not** claim that an external government or benefits application was submitted unless a real external adapter returns a durable receipt.

## Real Google action loop

Before Wave 4, HealthIA's frozen Google Health Constellation proof demonstrated a real external action loop:

`Safety → Mission Router → Places → Gmail send → Gmail watch → Pub/Sub → Gmail history → exact reply correlation → Calendar FreeBusy → Calendar event → Google Task → durable receipts → COMPLETED`

The proof includes a real Gmail send, reply recovery with exact thread correlation, a real Calendar event created and reread, a real Google Task created and reread, durable receipts, and idempotent duplicate Pub/Sub handling.

The important lesson was that **authorization is not execution evidence**. A system should not claim that an action happened merely because it planned or authorized it. A real action needs a real receipt.

## Production-minded boundaries

During the build we repeatedly found defects only because the evidence gates were strict. Examples included a hidden UTF-8 BOM in a Maps secret and provenance loss when the same real resource appeared in multiple semantic searches.

We did not lower the gates to turn those failures green. We fixed the product and reran the proof.

Other boundaries include:

- synthetic patient data only in hackathon demonstrations;
- bounded model-request budgets;
- mission-scoped consent;
- patient-scoped state;
- cross-patient evidence isolation;
- original evidence preserved before AI interpretation;
- no autonomous prescribing or medication changes;
- no fabricated provider referral, benefit eligibility, or external submission receipt.

## What we learned

The biggest lesson from HealthIA ONE is that agentic systems become more trustworthy when they combine autonomy with explicit boundaries.

A useful health agent should not merely answer faster. It should remember what still needs to happen, preserve where information came from, take real action when authorized, stop when the human owns the decision, and continue the same work afterward.

That is the idea behind HealthIA ONE:

**Your health never starts over.**

## Judge evidence

- Final Wave 4 submission candidate: https://github.com/arisnachy/healthia-one/pull/41
- Preserved Google action-loop proof: https://github.com/arisnachy/healthia-one/pull/37
- Public demo: https://youtu.be/-NWS65Hv_h0

All hackathon clinical demonstrations use synthetic patient data.