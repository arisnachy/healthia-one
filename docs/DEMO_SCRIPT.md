# Four-minute demonstration script

Use synthetic data only. Record the demonstration without hidden manual edits between steps.

## 0:00–0:25 — Problem and promise

Show the chat home.

> Health information is fragmented across measurements, PDFs, medications, family history and appointments. Patients repeatedly reconstruct their story. HealthIA ONE is a patient-owned agent team that preserves continuity and acts only within explicit permissions.

Show the visible composer and the statement: **Your health never starts over.**

## 0:25–0:55 — Asynchronous intervention

Press **Revisión agentica** or allow the synthetic background check to run outside quiet hours.

Show one intervention containing:

- what was detected;
- why it matters;
- evidence IDs / activated team;
- a safe next step;
- `Silenciar este tipo`.

Explain that deterministic safety runs before model routing and that repeated rules are idempotent.

## 0:55–1:25 — Chat controls the patient OS

Send:

```text
Muéstrame mi genograma y los patrones familiares que debo discutir con mi médico.
```

Show:

- HEREDITAS, HISTORIA, SENTINEL and KIRA in the expandable public agent plan;
- explicit no-diagnosis language;
- the **Abrir genograma** action.

Open the genogram and briefly show generations, maternal/paternal lineage, conditions and age at diagnosis.

## 1:25–1:50 — Documents and longitudinal record

Send:

```text
Organiza mis documentos del expediente.
```

Open Documents and upload `demo/synthetic-labs.json` or a small synthetic text file.

Show:

- category;
- provenance and status;
- downloadable original;
- pending-review behavior for unread PDF/image files.

State clearly that HealthIA never fabricates unread values.

## 1:50–2:20 — Treatment safety

Send:

```text
Muéstrame mi tratamiento y las tomas registradas.
```

Open Treatment and register one synthetic dose as taken.

Show:

- exact registered plan;
- patient-reported adherence;
- MEDSAFE boundary: no doubling, stopping or changing medication.

## 2:20–2:50 — Consultation preparation

Send:

```text
Prepara mi próxima consulta.
```

Open Citas y consulta. Show the generated brief with:

- confirmed conditions;
- medication;
- measurements;
- recent results;
- family context;
- required documents;
- prioritized questions.

Emphasize that the patient reviews the brief before sharing it.

## 2:50–3:15 — Unified timeline

Send:

```text
Enséñame mi línea de salud.
```

Show the chronological combination of vitals, weight, activity, result, document, medication check-in, appointment and mission.

Explain that backdated records are sorted by their actual event time rather than upload order.

## 3:15–3:40 — Patient control

Send:

```text
Quiero revisar mis permisos, auditoría y exportar mis datos.
```

Show:

- signal-by-signal permissions;
- quiet hours;
- 24-hour snooze;
- reversible muted rules;
- urgent deterministic safety authorization;
- audit events;
- structured patient export.

State that the audit exposes operational facts, not private chain-of-thought.

## 3:40–4:00 — Google Cloud proof and close

For the final hackathon recording, show:

- Cloud Run revision and service URL;
- Firestore patient-state document;
- Cloud logs for the same mission;
- Gemini/Google ADK execution evidence;
- repository CI in green.

Close with:

> A chatbot answers one question. HealthIA ONE keeps the patient's authorized health story connected, explains why it intervenes, and stays with each health mission until the next safe step.

## Required honesty

Do not claim:

- confirmed diagnosis;
- prescription authority;
- treatment modification;
- genetic prediction;
- clinical effectiveness;
- production security;
- regulatory clearance;
- real Gemini multimodal extraction unless it is visibly executed in the recorded run.
