# HealthIA ONE — approximately 4-minute unedited judge demo

## Living System replacement contract

The current replacement take must be recorded by the exact-head GitHub Actions
pipeline with Google Cloud Text-to-Speech voice
`en-US-Chirp3-HD-Charon` (male). It must visibly use the real `/living` page,
keep the capability secret off screen and prove:

1. the system begins locked and synthetic-only;
2. four authorized signals update the versioned Patient Twin;
3. the same durable mission stops at `WAITING_HUMAN`, event 10/14;
4. no autonomous diagnosis, prescription or clinical sensor verification is claimed;
5. a persisted synthetic human measurement receipt resumes the mission;
6. Twin v3 and event 14/14 are visible;
7. reload rereads the durable replay;
8. the closing proof displays the exact candidate SHA, Cloud Run revision and
   zero model calls for the Living circuit.

The published MP4 and `public-video-proof.json` in release
`healthia-one-autonomous-winner-demo-2026` are authoritative only after CUTLOCK,
anonymous download and byte-identical SHA-256 verification pass. The older
recording below is retained as historical evidence until that replacement is
published; it must not be described as showing the new `/living` UI.

## Historical recording and publication status — PASS

A continuous, unmocked judge-demo recording has been captured and the exact verified WebM is published at a stable public GitHub Release URL.

- GitHub Actions recording run: `31265639488`
- recording candidate SHA: `3f99e511f6518e8dc9b45ebfd0cbdc37aaa9768e`
- source artifact: `HealthIA-ONE-final-judge-demo` / `9024139098`
- source artifact digest: `sha256:71ee6e2ce665a9b98e44ca11aae7c7334849b73ac7e756b157afa47b3a249f33`
- video SHA-256: `cfd91b0d08cf6659e1fb924c2e85071cd3b79bd414578b7112908c46f91adb19`
- continuous duration: `290.16 s`
- live Cloud Run revision shown: `healthia-one-demo-00016-mct`
- synthetic data only
- zero browser console/page errors

**Public judge video:**  
`https://github.com/arisnachy/healthia-one/releases/download/healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm`

**Release page:**  
`https://github.com/arisnachy/healthia-one/releases/tag/healthia-one-hackathon-judge-demo-2026`

Publication proof run `31267268584` revalidated the original artifact SHA, published the Release asset, downloaded it without credentials and matched the exact video SHA again. Independent probe run `31267268597` separately repeated the anonymous full download and SHA match. Permanent evidence is in `hackathon/evidence/public_judge_video_proof.json`.

The recorder reused the existing private Cloud Run deployment; it did not deploy another revision. The exact sanitized recording metadata is preserved in `hackathon/evidence/final_judge_demo_proof.json`.

---

## Recording rule / human narration version

If a narrated replacement is ever needed, record it as **one continuous take**. Do not splice out loading states or failures. Use synthetic data only. The objective is to prove the Taskmaster workflow and the Google Cloud runtime, not to enumerate every screen.

Before recording:

- use the proven Cloud-backed application flow;
- confirm `/api/readiness` reports Gemini 3.5 Flash, ADK ready, Firestore and GCS;
- start with a clean synthetic demo patient;
- prepare one tiny synthetic laboratory PDF;
- keep Google Cloud Console open on the Cloud Run service/revisions page for the closing proof;
- do not expose secrets, identity tokens or service-account JSON.

## 0:00–0:25 — Problem and promise

**Show:** HealthIA ONE chat home.

**Say:**

> “Patients do not have one clean health record. They have PDFs, images, devices, medications and pieces of memory. Most AI can discuss those fragments, but the work disappears with the chat. HealthIA ONE turns them into durable patient-owned missions. It asks what is missing, preserves the original evidence, acts with Gemini and Google ADK, and only closes the task when the evidence-backed outcome exists.”

## 0:25–1:20 — Gemini + ADK adaptive interview

**Type a synthetic complaint:**

> “Desde ayer me arde al orinar y tengo que ir al baño a cada rato. Quiero orientación sobre qué información hace falta.”

**Show:** first five-question block.

**Say:**

> “This is not a fixed questionnaire. Google ADK runs on demand. The clinical runtime makes one real `inspect_clinical_baseline` tool call, which executes the mandatory interview and safety checks. Gemini 3.5 Flash then returns exactly five case-specific questions under structured output.”

Answer a few questions, including one detail that should not be asked again.

**Show:** second five-question block or resulting orientation.

**Say:**

> “The next block receives the actual previous questions and answers. The system avoids repeating known facts, and the tool evidence comes from what actually executed — not from the model claiming that a tool ran.”

## 1:20–2:30 — Multimodal evidence becomes durable state

Navigate to **Resultados** and upload the prepared synthetic PDF.

**Show:** interpreted result card, `parsed` state, explanation, `Ver archivo original`, and `Gemelo vinculado`/provenance indicator.

**Say:**

> “The original bytes are stored first in private Google Cloud Storage. Only then does Gemini 3.5 Flash on Vertex AI extract readable evidence into structured JSON. Firestore stores the patient-scoped result and the clinical twin keeps provenance back to the original. If interpretation fails, HealthIA leaves the original available and marks the analysis pending instead of inventing findings.”

Open the original-document link briefly.

## 2:30–3:10 — Close the Taskmaster mission

Return to chat and ask:

> “Explícame el resultado que acabo de subir y confirma que quedó guardado.”

**Show:** the response and completed result-explanation mission.

**Say:**

> “This is the Taskmaster loop. HealthIA retrieves the persisted result and original-document metadata, returns the saved explanation and closes the mission only when the durable evidence exists. It keeps correlated result and document IDs. It does not spend another Gemini request merely to paraphrase the same stored evidence.”

## 3:10–3:32 — Persistence that a judge can see

Logout and log back in with the same synthetic patient.

**Say:**

> “This continuity is backed by Firestore and private GCS, not browser memory. Our automated proof also forced a genuinely new Cloud Run revision with the same image and verified that the result, mission, twin provenance and exact GCS object survived while a second patient remained isolated.”

## 3:32–3:58 — Visible Google Cloud proof

Show the live `.run.app` URL plus `/api/readiness`, or Google Cloud Console.

**Show:**

- Cloud Run service `healthia-one-demo` or `.run.app` URL;
- current ready revision;
- project `healthia-6088a` / region `us-central1`;
- readiness showing Gemini 3.5 Flash, ADK, Firestore and GCS;
- no secret values.

**Say:**

> “This is running on Google Cloud: Cloud Run for the application, Gemini 3.5 Flash through Vertex AI and service identity, Firestore for canonical patient state, and private Cloud Storage for original evidence. The repository preserves the exact passing run IDs, artifact digests and cross-revision proof.”

## 3:58–4:05 — Close

> “HealthIA ONE does not reset the patient's story when the conversation ends. The mission is not complete when the model talks — it is complete when the evidence-backed outcome exists and survives.”

---

## Truth boundary for the recording

**Do not claim:**

- **confirmed diagnosis** — HealthIA organizes evidence and safety context but does not establish a diagnosis from insufficient data;
- **prescription authority** — it does not autonomously start, stop or change medications;
- **genetic prediction** — the family genogram is provenance-linked family history, not a predictive genetics engine;
- **regulatory clearance** — this hackathon build is not presented as a cleared or approved medical device.

Also do not claim universal clinical efficacy, universal security, or production regulatory compliance. The evidence proves the tested software behavior and Google Cloud architecture with synthetic data.

## Evidence behind the recording

### Final continuous judge-demo artifact — PASS

- run `31265639488`
- candidate `3f99e511f6518e8dc9b45ebfd0cbdc37aaa9768e`
- artifact `9024139098`
- video SHA-256 `cfd91b0d08cf6659e1fb924c2e85071cd3b79bd414578b7112908c46f91adb19`
- duration `290.16 s`
- live revision `healthia-one-demo-00016-mct`
- zero console/page errors

### Public Release publication — PASS

- publication run `31267268584`
- proof artifact `9024528554`
- proof artifact digest `sha256:281703f31d7a5a42bd28fdce18f455cfe46b91263304e1e9b8c2fbfbf62cb7d5`
- anonymous download: PASS
- exact SHA match: PASS

### Independent public URL probe — PASS

- run `31267268597`
- artifact `9024526089`
- digest `sha256:ff151da75a8809b4ac493b909f526dd484ef7c6e9248e4c7b11bb0e0569d06d7`
- authentication required: false
- full video SHA match: PASS

### Exact-candidate Cloud + Chromium — PASS

- run `31262429792`
- candidate `a28955c3641c37a9e5a06f5f0ccf943ccb197bbd`
- Cloud revision `healthia-one-demo-00012-jvl`
- artifact `9023242539`
- unmocked Chromium: PASS

### Cross-revision continuity — PASS

- run `31262903731`
- before `healthia-one-demo-00013-2bz`
- after `healthia-one-demo-00014-ns8`
- same image: true
- artifact `9023298988`

See `docs/EVIDENCE.md` for the permanent sanitized evidence index.

## Fail criteria for any replacement take

- dynamic question block falls back instead of live Gemini/ADK;
- result remains `pending_multimodal`;
- original-document provenance is missing;
- mission does not become completed;
- relogin loses persisted result/mission;
- browser shows an obvious application error;
- Cloud runtime proof is not visible;
- a secret/token/private credential appears on screen;
- take materially exceeds the allowed time.

## Final submission URL

**PUBLIC/JUDGE VIDEO URL:**  
`https://github.com/arisnachy/healthia-one/releases/download/healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm`

PR #29 was merged as `a1525ec` after its candidate passed CI + JUDGE Ω. Later working-tree hardening is not part of that preserved candidate until a new exact-head gate is run.
