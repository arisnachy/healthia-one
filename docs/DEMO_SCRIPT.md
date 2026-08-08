# HealthIA ONE — four-minute judge demo

**Record one continuous take. Use synthetic data only. Do not hide failed steps or splice a successful output into the recording.**

The goal of this demo is to prove three things fast:

1. HealthIA is a **Taskmaster workflow**, not a chatbot;
2. Gemini 3.5 Flash + Google ADK perform real, demand-driven work;
3. the backend and durable evidence actually run on Google Cloud.

## Before recording

Have these tabs ready:

- HealthIA Cloud Run UI;
- Google Cloud Console → Cloud Run service/revision;
- Google Cloud Console → Firestore;
- Google Cloud Console → Cloud Storage evidence bucket;
- GitHub Actions evidence run.

Use a fresh synthetic patient account. Keep the synthetic PDF ready for upload. Do not show service-account JSON, API keys, session secrets or other credentials.

---

## 0:00–0:25 — Problem + one-sentence promise

Show the HealthIA login/home screen and say:

> Health data is fragmented across conversations, PDFs, devices and memory. A normal chatbot answers and forgets. HealthIA ONE turns patient evidence into durable health missions: it decides what it needs, preserves the source, updates longitudinal state and keeps working until the mission has a verifiable outcome.

On screen, briefly show **Your health never starts over.**

---

## 0:25–0:50 — Prove the backend is Google Cloud

Switch briefly to Google Cloud Console.

Show, without lingering:

- project `healthia-6088a`;
- Cloud Run service `healthia-one-demo` and its ready revision;
- the `.run.app` service URL;
- Vertex AI / Cloud logs for the same deployed service.

Say:

> The application is running on Cloud Run. Gemini 3.5 Flash is accessed through Vertex AI using the runtime service identity — there is no Gemini API key inside the Cloud Run service.

Return to HealthIA.

---

## 0:50–1:30 — Adaptive Gemini + ADK interview

Log in as the synthetic patient and send:

```text
Desde ayer me arde al orinar y tengo que ir al baño a cada rato.
```

Show that the interface produces **five case-specific questions** rather than a static questionnaire.

Answer the block. If a second block is generated, point out that it changes based on the previous answers instead of repeating them.

Open the compact execution/audit evidence and say:

> Google ADK executes the mandatory interview and safety tools and activates additional specialists only when the case needs them. The agent team is demand-driven; there is no permanent swarm spending tokens in the background.

Do not claim a diagnosis. Let HealthIA finish with its patient-facing orientation when Gemini decides the available information is sufficient.

---

## 1:30–2:35 — The Taskmaster moment: upload → action → durable outcome

Upload the synthetic PDF result.

While the real request runs, narrate the workflow:

> HealthIA stores the original evidence first. Gemini 3.5 Flash then extracts the readable clinical information under a structured JSON contract. The result is committed to the patient's state and the clinical twin keeps provenance back to the original file.

When processing completes, show:

- identified result/panel;
- extracted observations;
- patient explanation and limitations;
- **Abrir original** / original document link;
- the relevant clinical-twin/timeline entry.

Then ask in chat:

```text
Explícame el resultado que acabo de subir y confirma que quedó guardado.
```

Show the resulting Taskmaster mission as **COMPLETED**.

Point out the correlated evidence IDs / original link and say:

> This second step does not need another Gemini call just to paraphrase the same data. HealthIA retrieves the persisted evidence, returns the saved explanation and closes the mission only because the result actually exists.

This is the central proof: the agent changed durable state and completed a multi-step workflow; it did not merely generate text.

---

## 2:35–3:05 — Prove durability and isolation

Log out, then log back into the same synthetic patient.

Show that the uploaded result, original evidence and completed mission are still present.

If the demo environment is prepared with a second synthetic account, switch briefly to patient B and show that patient A's result is absent.

Say:

> Patient state, documents, missions and device identity are scoped by authenticated patient identity. Continuity survives a new session without leaking another patient's data.

---

## 3:05–3:35 — Prove Firestore + GCS, not just the UI

Switch to Google Cloud Console.

Show the matching synthetic evidence created during the demo:

- Firestore patient-state document / update;
- private Cloud Storage object for the uploaded original;
- Cloud Run log entries from the mission;
- Vertex/ADK execution evidence if visible in the logging view.

Use the same patient/result identifiers visible in the UI where practical so the judge can correlate the layers.

Say:

> The browser is not the evidence source. The canonical state is in Firestore and the original bytes are in private Cloud Storage. The UI is reading the same durable workflow state.

---

## 3:35–4:00 — Architecture + close

Show the README architecture diagram or `docs/ARCHITECTURE.md` for only a few seconds:

**Patient → Cloud Run → safety/orchestrator → Google ADK + Gemini 3.5 Vertex → Firestore/GCS → clinical twin → patient.**

Then show the green GitHub evidence run and close with:

> A chatbot answers a question. HealthIA ONE takes a patient goal, performs the work, preserves the evidence, updates longitudinal state and proves when the mission is actually complete. Your health never starts over.

---

## Judge evidence to capture in the final take

The video should visibly contain:

- Cloud Run service URL and ready revision;
- Gemini **3.5 Flash** / Vertex AI evidence;
- live Google ADK adaptive interview behavior;
- real multimodal result upload;
- original evidence link;
- clinical-twin/timeline update;
- Taskmaster mission `COMPLETED`;
- Firestore persisted state;
- private GCS object;
- logout/login durability;
- green GitHub verification/proof evidence.

## What not to waste four minutes on

Genogram, device pairing, medication continuity, permissions, export and the full patient OS are valuable secondary capabilities. Mention them in the write-up or show them only if the core flow finishes early. Do **not** sacrifice the Cloud + Taskmaster evidence to tour every menu.

## Required honesty

Do not claim:

- confirmed diagnosis;
- prescription authority or treatment modification;
- genetic prediction;
- clinical effectiveness;
- regulatory clearance;
- production security certification;
- Cloud deployment until the real Cloud strict proof is green;
- a result was interpreted by Gemini if the recorded run did not actually execute it.
