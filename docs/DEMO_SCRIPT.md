# HealthIA ONE — approximately 4-minute unedited judge demo

## Recording rule

Record this as **one continuous take**. Do not splice out loading states or failures. Use synthetic data only. The objective is to prove the Taskmaster workflow and the Google Cloud runtime, not to enumerate every screen.

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

Point to the UI label that the questions were generated for this case by Gemini + ADK.

**Say:**

> “This is not a fixed questionnaire. Google ADK runs on demand. The clinical runtime makes one real `inspect_clinical_baseline` tool call, which executes the mandatory interview and safety checks. Gemini 3.5 Flash then returns exactly five case-specific questions under structured output.”

Answer a few questions, including one detail that should not be asked again.

**Show:** second five-question block or the resulting orientation.

**Say:**

> “The next block receives the actual previous questions and answers. The system avoids repeating known facts, and the tool evidence comes from what actually executed — not from the model claiming that a tool ran.”

## 1:20–2:30 — Multimodal evidence becomes durable state

Navigate to **Resultados** and upload the prepared synthetic PDF.

The sample can contain simple values such as glucose and hemoglobin; no real patient data.

**Show:** interpreted result card, `parsed` state, explanation, `Ver archivo original`, and `Gemelo vinculado`/provenance indicator.

**Say:**

> “The original bytes are stored first in private Google Cloud Storage. Only then does Gemini 3.5 Flash on Vertex AI extract readable evidence into structured JSON. Firestore stores the patient-scoped result and the clinical twin keeps provenance back to the original. If interpretation fails, HealthIA leaves the original available and marks the analysis pending instead of inventing findings.”

Open the original-document link briefly to prove the evidence exists.

## 2:30–3:10 — Close the Taskmaster mission

Return to chat and ask:

> “Explícame el resultado que acabo de subir y confirma que quedó guardado.”

**Show:** the response and the mission becoming completed.

Navigate to **Misiones de salud** if needed and point to the completed result-explanation mission.

**Say:**

> “This is the Taskmaster loop. HealthIA retrieves the persisted result and original-document metadata, returns the saved explanation and closes the mission only when the durable evidence exists. It keeps correlated result and document IDs. It does not spend another Gemini request merely to paraphrase the same stored evidence.”

## 3:10–3:32 — Persistence that a judge can see

Logout and log back in with the same synthetic patient.

Return to **Resultados** or **Misiones** and show that the result/document/completed mission are still present.

**Say:**

> “This continuity is backed by Firestore and private GCS, not browser memory. Our automated proof also forced a genuinely new Cloud Run revision with the same image and verified that the result, mission, twin provenance and exact GCS object survived while a second patient remained isolated.”

## 3:32–3:58 — Visible Google Cloud proof

Switch to Google Cloud Console.

**Show:**

- Cloud Run service `healthia-one-demo`;
- current ready revision;
- project `healthia-6088a` / region `us-central1`;
- optionally the revisions list showing the continuity proof changed revisions;
- do **not** open secret values.

**Say:**

> “This is running on Google Cloud: Cloud Run for the application, Gemini 3.5 Flash through Vertex AI and service identity, Firestore for canonical patient state, and private Cloud Storage for original evidence. The repository preserves the exact passing run IDs, artifact digests and cross-revision proof.”

## 3:58–4:05 — Close

Return to HealthIA.

**Say:**

> “HealthIA ONE does not reset the patient's story when the conversation ends. The mission is not complete when the model talks — it is complete when the evidence-backed outcome exists and survives.”

Stop recording.

---

## Truth boundary for the recording

**Do not claim:**

- **confirmed diagnosis** — HealthIA organizes evidence and safety context but does not establish a diagnosis from insufficient data;
- **prescription authority** — it does not autonomously start, stop or change medications;
- **genetic prediction** — the family genogram is provenance-linked family history, not a predictive genetics engine;
- **regulatory clearance** — this hackathon build is not presented as a cleared or approved medical device.

Also do not claim universal clinical efficacy, universal security, or production regulatory compliance. The evidence proves the tested software behavior and Google Cloud architecture with synthetic data.

## Evidence behind the recording

The recording is presentation evidence; it does not replace automated proof.

### Exact-candidate Cloud + Chromium — PASS

- run `31262429792`
- candidate `a28955c3641c37a9e5a06f5f0ccf943ccb197bbd`
- Cloud proof revision `healthia-one-demo-00012-jvl`
- artifact `healthia-exact-candidate-cloud-proof` / `9023242539`
- artifact digest `sha256:4760e89b6985fa81b532e4ed2fb094abcb8859f57c92259886c152d4632a55b6`
- unmocked Chromium journey: PASS
- browser console/page errors: zero

### Cross-revision continuity — PASS

- run `31262903731`
- before `healthia-one-demo-00013-2bz`
- after `healthia-one-demo-00014-ns8`
- same image across revision: true
- artifact `healthia-cloud-revision-continuity-proof` / `9023298988`
- artifact digest `sha256:4a30950483141ce55fa6f1256fa83998f0337a5e873576fa6f8598b111592263`

See `docs/EVIDENCE.md` for the permanent sanitized evidence index.

## Fail criteria — restart the take if any occurs

- the question block falls back instead of being generated by the live Gemini/ADK path;
- the result remains `pending_multimodal`;
- original-document provenance is missing;
- the mission does not become completed;
- relogin loses the persisted result/mission;
- browser shows an obvious application error;
- Cloud Console proof is not visible;
- a secret/token/private credential appears on screen;
- the take materially exceeds the allowed time.

## Final submission placeholder

**VIDEO URL: TODO**

Do not mark the project `100/100` or `SUBMISSION_LOCKED` until this final unedited video is recorded, uploaded, linked in `docs/DEVPOST_SUBMISSION.md`, and the final submission head passes CI + JUDGE Ω.
