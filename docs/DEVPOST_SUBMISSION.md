# HealthIA ONE — Devpost submission draft

## Category

**The Taskmaster**

## One-line pitch

**HealthIA ONE turns scattered patient evidence into durable, consent-aware health missions — then keeps working in the patient's language, preserves the original evidence, takes bounded Google actions, and can create a private evidence-grounded video explanation when understanding is the task.**

## The problem

A patient's health context is fragmented across PDFs, images, laboratory portals, medications, devices, family history and memory. Most AI health experiences are still transient chat: they can discuss a result once but do not reliably preserve the original evidence, reconnect it to longitudinal state, resume an interrupted task, or prove that a multi-step outcome actually exists.

HealthIA ONE treats **continuity itself as the job**.

A second source of friction is understanding. A patient may have a correct report or diagnosis in front of them and still not understand what it means. HealthIA ONE can turn that already-authorized evidence into a private, patient-facing audiovisual explanation without sending patient-specific values to a generative video model.

## What HealthIA ONE does

### Adaptive patient interview

The patient describes a problem in natural language. Google ADK runs on demand, executes a real aggregate clinical baseline tool containing deterministic interview + safety checks, and Gemini 3.5 Flash generates exactly five context-specific questions under a structured-output contract. Later blocks receive prior questions/answers so the system avoids asking known facts again and decides when the interview is sufficiently complete to orient the patient to the next safe step.

### Language follows the patient

HealthIA separates **interface language** from **clinical conversation language**.

- The shipped patient UI automatically follows the browser/operating-system locale for the production English/Spanish interface packs and preserves a manual override.
- Clinical conversation and HealthIA Explain resolve the language from the patient's current message first, then fall back to the browser/profile locale when the text is too short or ambiguous.
- The evidence values themselves are never translated loosely: medication names, numbers and units remain exact when they come from the patient record.
- The current content/video language layer is bounded to explicit supported locales instead of letting an LLM invent locale behavior.

This means an English interface can safely answer a patient who writes in Spanish, and the resulting educational video is narrated in Spanish; the reverse works as well.

### Evidence-first multimodal results

When the patient uploads a PDF or clinical image:

1. HealthIA stores the **original bytes first** in private Google Cloud Storage;
2. Gemini 3.5 Flash on Vertex AI extracts only readable/visible evidence into structured JSON;
3. Firestore stores the patient-scoped result/document state;
4. the clinical twin receives provenance linking the derived result to the original;
5. if AI interpretation fails, the original remains available and the result stays pending instead of inventing findings.

PDFs use low visual-media resolution with native PDF text to reduce latency/cost; clinical images retain high visual resolution.

### Closed-loop Taskmaster mission

A later request such as “explain the result I just uploaded” retrieves the **persisted** result and original-document metadata, returns the saved patient explanation/original link and closes a `result_explanation` mission only when the evidence exists. The completed mission retains correlated result/document evidence and survives logout/login and a real Cloud Run revision while remaining invisible to another authenticated patient.

### HealthIA Explain — private audiovisual patient education

When the patient asks for an explanation, HealthIA can offer a private video. If the patient accepts, the same patient-scoped system creates a durable `patient_education_video` mission:

```text
patient question
  → resolve the patient's current language
  → select only topic-relevant authorized evidence
  → Gemini builds a bounded educational storyboard
  → exact patient values remain on controlled HealthIA cards
  → optional Veo scene receives only a generic PHI-free visual prompt
  → Gemini TTS narrates in the patient's language
  → HealthIA renders and privately stores the MP4
  → mission closes only when the media artifact exists
```

The generated explanation is educational. It cannot autonomously diagnose a new condition, prescribe, change a dose or tell the patient to stop medication. If media generation fails, the mission remains retryable and HealthIA does not pretend a video was created.

### Human boundary + real Google actions

For location-sensitive resource discovery, HealthIA pauses the durable mission and asks for mission-scoped consent. Only after consent does it call Google Places/Maps, persist bounded real candidates and let the patient make an exact deterministic choice such as “the second one” without another LLM call. This keeps reasoning, consent and exact action visibly separate.

## Why it is agentic

HealthIA is not a permanent swarm and not a prompt wrapper. Work is event-driven and demand-driven:

```text
patient/event goal
  → auth + deterministic safety boundary
  → load patient-scoped longitudinal state
  → invoke the minimum Google agent/model/tool path that is needed
  → pause at human consent boundaries when required
  → persist outcome + evidence
  → resume the same mission
  → close only when the requested durable outcome exists
```

The clinical ADK path executes one real function-tool trajectory (`inspect_clinical_baseline`) that runs mandatory interview + safety checks. Tool execution is audited separately, and the runtime reconstructs specialist evidence from what actually executed instead of trusting model prose.

HealthIA Explain uses the same design principle: Gemini handles reasoning and patient-friendly structure; exact clinical values and safety boundaries remain deterministic; Veo is optional enrichment rather than a dependency.

## Google technologies

Core required stack:

- **Gemini 3.5 Flash** on Vertex AI
- **Google Agent Development Kit (ADK)**
- **Google GenAI SDK / Interactions transport**
- **Cloud Run**
- **Firestore**
- **Google Cloud Storage**
- **Secret Manager**
- **Cloud Build**
- **Google Places / Maps Platform**

Additional Google models/services used by HealthIA Explain:

- **Gemini 2.5 Pro TTS** through Google Cloud Text-to-Speech, promptable patient narration
- **Veo 3.1 Fast** on Vertex AI, optional PHI-free educational animation

No Gemini API key is injected into the Cloud Run proof deployment. Google model/tool access is routed through service identity / ADC and HealthIA's existing patient/mission authorization boundary.

## Architecture

See `docs/ARCHITECTURE.md` for the Mermaid architecture and evidence-flow diagrams.

```text
Patient UI
  → Cloud Run / FastAPI
  → patient auth + policy boundary
     ↳ Google ADK Runner → interview+safety tool → Gemini 3.5 structured questions
     ↳ multimodal pipeline → original GCS → Gemini 3.5 extraction
     ↳ HealthIA Explain → evidence subset → Gemini storyboard
                          → Gemini TTS narration
                          → optional PHI-free Veo clip
                          → private MP4
     ↳ consent boundary → Places/Maps real candidates → exact deterministic selection
  → Firestore canonical state + durable missions
  → provenance-linked clinical twin
  → patient UI / persisted outcome
```

## Data sources

The hackathon/demo paths use **synthetic patients and synthetic clinical files only**. The system may also accept patient-entered longitudinal state and a signed Android/Health Connect device bridge contract, but no real patient record is required for the submission demo.

HealthIA Opportunity Autopilot also uses public biomedical opportunity sources such as PubMed/NLM, Europe PMC and ClinicalTrials.gov with provenance and uncertainty boundaries; it does not fake external applications.

## Production-minded boundaries

- signed `HttpOnly` patient sessions;
- salted `scrypt` account hashes;
- patient-scoped Firestore state;
- private patient-scoped GCS object paths;
- cross-patient document denial;
- signed patient/device/connection identity;
- service-identity/ADC Google access;
- explicit AI request ceilings;
- demand-driven model/tool execution instead of a permanent polling swarm;
- original evidence persisted before model interpretation;
- fail-closed multimodal behavior;
- mission-scoped consent for sensitive Google actions;
- patient-specific clinical values excluded from Veo prompts;
- Gemini TTS media generation kept behind the existing Google grant/receipt boundary;
- synthetic data only in hackathon media proofs;
- explicit opt-in billable Cloud proof/recording/publication workflows.

## New integrated candidate — deterministic verification PASS

Integrated HealthIA Explain + multilingual content routing + the redesigned HealthIA ONE login passed the full repository gate on GitHub Actions run **`31767221658`**, branch head **`0de5adad497b0a15defbedc1c0341394dc1680fd`**.

The run passed:

- the complete pytest suite;
- Full System Verification;
- KIRA DialogBench;
- Chromium clinical E2E;
- LAB OMEGA core and secondary functional laboratories;
- compileall;
- smoke tests;
- JUDGE OMEGA evidence review;
- semantic frontend validation;
- release archive build/verification;
- pytest again from the extracted release archive.

This is a fresh software-regression proof for the new integrated branch. It does **not** replace the preserved Cloud/demo submission evidence until the refreshed Cloud/video proof is intentionally recorded and published.

## New live media proofs

### Vertex AI Veo 3.1 Fast — LIVE PASS

GitHub Actions run **`31758267226`** performed one explicitly authorized real generation using `veo-3.1-fast-generate-001` in Google Cloud:

- one synthetic 8-second clip;
- 720p / 16:9;
- person generation disabled;
- no text, labels, names, medications, laboratory values or patient data;
- downloaded output validated as MP4;
- temporary generation output removed from private GCS after artifact capture.

### Gemini 2.5 Pro TTS — LIVE PASS

GitHub Actions run **`31764094573`** performed one explicitly authorized real narration using:

- model `gemini-2.5-pro-tts`;
- prebuilt voice `Charon`;
- Spanish Latin America (`es-419`);
- natural-language direction for a warm, calm, professional clinical narration;
- synthetic patient content only.

The successful artifact proved that HealthIA can use the same Google Cloud account/authorization boundary for natural narration instead of the robotic local fallback used during early prototyping.

## Preserved submission proof

The pre-HealthIA-Explain candidate remains preserved and independently proven. The new branch does not erase that evidence.

### Continuous final judge demo — PASS

Run **`31265639488`** produced a continuous unmocked WebM covering problem/value, live Gemini+ADK clinical interaction, multimodal result, original-document evidence, clinical twin, completed Taskmaster mission, relogin continuity and the Cloud runtime.

- candidate SHA: `3f99e511f6518e8dc9b45ebfd0cbdc37aaa9768e`
- artifact: `HealthIA-ONE-final-judge-demo` (`9024139098`)
- video SHA-256: `cfd91b0d08cf6659e1fb924c2e85071cd3b79bd414578b7112908c46f91adb19`
- duration: `290.16 s`
- live revision: `healthia-one-demo-00016-mct`
- synthetic data only

### Exact-candidate Cloud + browser — PASS

Run **`31262429792`** proved Cloud Run, Vertex Gemini 3.5, real Google ADK execution, Firestore, private GCS, two-patient isolation, multimodal PDF extraction, twin provenance, original evidence round trip and a complete unmocked Chromium journey.

### Cross-revision continuity — PASS

Run **`31262903731`** forced a new Cloud Run revision with the same image and proved that patient state, result/document/mission/twin and exact GCS evidence survived while a second patient remained isolated.

### Stable public judge video — PASS

The preserved WebM is published as a public GitHub Release asset and was independently downloaded without credentials with a matching SHA-256. See `docs/EVIDENCE.md`.

## Findings and learnings

1. **Agentic does not mean always-on.** Demand-driven agents are easier to audit, cheaper and more natural for patient continuity than a permanent swarm.
2. **Evidence must exist before interpretation.** Persisting original bytes before Gemini creates a recoverable provenance boundary.
3. **Reasoning and exact action should be different layers.** Gemini can reason; deterministic code can preserve exact patient choices and values.
4. **Language is context, not a global toggle.** UI locale and the language the patient chooses to speak can differ safely.
5. **Patient education benefits from mixed media.** Exact values belong on controlled cards; generative video is best used for generic explanatory motion.
6. **Veo should not receive PHI just because the final video is private.** HealthIA keeps patient-specific facts out of the generative visual prompt entirely.
7. **Media generation must fail honestly.** A failed video remains a retryable mission rather than a fabricated success.
8. **Durability must be tested across a process boundary.** The project proves persistence across a genuinely new Cloud Run revision, not just refresh/logout.
9. **Cost control is architecture.** Billable proofs and media generations are explicit, bounded and auditable.
10. **Demo evidence should be reproducible.** A replacement judge video should be tied to one exact green candidate SHA.

## Spin-up instructions

### Local zero-spend mode

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
HEALTHIA_LLM_BACKEND=mock HEALTHIA_COST_MODE=local HEALTHIA_AI_REQUEST_LIMIT=0 uvicorn app.main:app --port 8000
```

Windows also includes `deployment/run-local-secure.ps1`.

### Cloud proof deployment

```powershell
.\deployment\deploy-cloud-demo.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -RequestLimit 20
```

The project expects required Google Cloud APIs/permissions to be preconfigured and fails closed otherwise. HealthIA Explain media is separately cost-gated and Veo requires explicit opt-in.

## Repository

`https://github.com/arisnachy/healthia-one`

## Hosted project

The preserved proof service is private at the Cloud Run IAM boundary even though the application also has patient authentication. A refreshed judge deployment should be a bounded synthetic-data environment with simple judge access, rate limits and no experimental features.

Preserved proven Cloud URL: `https://healthia-one-demo-tkuxk5r6rq-uc.a.run.app`

## Demo video

**Current preserved public video:**

`https://github.com/arisnachy/healthia-one/releases/download/healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm`

A refreshed Devpost video should replace this only after the integrated candidate receives its final exact-head Cloud/recording proof. The refreshed story should visibly show:

1. the new HealthIA ONE login;
2. OS/browser interface language;
3. a patient writing in a different language and HealthIA following the patient's language;
4. an evidence-grounded durable mission;
5. HealthIA offering and creating a private video explanation;
6. natural Gemini TTS narration and a real PHI-free Veo visual;
7. consent/action boundaries;
8. logout/relogin continuity;
9. visible Google Cloud / Vertex / ADK proof.

## Submission status

The preserved submission remains valid evidence while the integrated replacement is being prepared. Do **not** replace the Devpost video or canonical evidence references until the final integrated SHA has a fresh exact-head regression + Cloud/demo proof. A JUDGE Ω 100/100 score is an internal evidence-backed rubric result, not a guarantee of external judging outcome.
