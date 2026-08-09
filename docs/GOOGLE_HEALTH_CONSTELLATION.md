# HealthIA ONE · Google Health Constellation

Status: architecture contract for isolated branch `kira/google-health-constellation`.
Base: `kira/opportunity-autopilot` exact head `6358d9eeb74fe8b19bba74f7d09f2359dc9418af`.

## Goal

Turn HealthIA ONE from a chat that can call tools into a patient-controlled health agent that can coordinate real-world work across the Google ecosystem while preserving clinical safety, explicit authorization, idempotency, provenance, cost guards, and durable public receipts.

The chat remains the primary control surface. Service-specific screens are evidence surfaces, not separate workflows.

## Core orchestration rule

Every Google action must flow through:

`patient intent/event -> deterministic safety -> patient scope + consent -> plan -> read-only discovery -> proposed action -> explicit authorization when external mutation is sensitive -> tool execution -> durable receipt -> HealthIA synthesis -> longitudinal state update`

No connector is allowed to bypass the patient-scoped mission/receipt boundary.

## Agent constellation

### 1. Care Navigator Agent · Google Maps Platform

Purpose:
- Find nearby hospitals, clinics, pharmacies, laboratories, imaging centers, rehabilitation services, autism/community support centers, government offices, foundations, and other relevant places.
- Rank by distance/travel time, opening status, service relevance, and verified program/provider relationship.
- Preserve Place ID, address, coordinates, phone/website when available, search radius, field mask, and retrieval timestamp.
- Offer route/navigation handoff without claiming that a place provides a clinical service unless the source actually supports it.

Example:
`Find autism assistance -> verified program -> locate nearest enrollment offices/support centers -> show map + travel options -> offer to contact the selected center.`

Safety/truth boundary:
- A nearby place is not automatically an appropriate clinical referral.
- Do not infer service availability from category alone when a verified source is required.
- Location search requires an explicit patient location or device-location grant; locale is never residence.

### 2. Scheduling Agent · Google Calendar

Purpose:
- Read patient availability when authorized.
- Check free/busy windows.
- Propose appointment slots.
- Create/update/cancel patient calendar events only after the patient confirms the selected slot unless a narrow standing automation explicitly grants that authority.
- Store provider, address/Meet URL, required documents, preparation instructions, travel buffer, and source mission ID.

Example:
`The clinic offered Tuesday 10:30 -> check patient's calendar -> identify conflict -> propose Tuesday 11:30 -> after confirmation, create Calendar event + travel buffer + required-documents task.`

Receipt fields:
- calendar event ID
- action (`created|updated|cancelled`)
- event start/end/timezone
- source mission ID
- authorization ID

### 3. Communications Agent · Gmail + Pub/Sub

Purpose:
- Draft or send appointment/resource/program emails from the patient's authorized Gmail account.
- Keep replies in the same thread.
- Watch the mailbox using Gmail push notifications rather than permanent polling.
- Classify replies such as `appointment_offered`, `appointment_confirmed`, `application_received`, `approved`, `rejected`, `missing_documents`, `needs_information`, `no_response`.
- Never treat model classification as final administrative truth when the email text is ambiguous.

Example:
`Email three verified autism support centers asking about intake -> record Gmail message/thread IDs -> Gmail push detects reply -> HealthIA reads only the relevant thread -> extracts offered date/requirements -> asks patient before Calendar mutation.`

External-action gate:
- Drafting may be autonomous when requested.
- Sending requires explicit patient authorization for the message/recipient unless a narrowly scoped standing permission exists.
- Replying with new sensitive medical information requires a fresh authorization preview.

Receipt fields:
- Gmail message ID
- Gmail thread ID
- recipients
- subject hash / safe summary
- action status
- timestamp
- source mission ID

### 4. Family & Trusted People Agent · Google People API

Purpose:
- Read the patient's authorized Google Contacts.
- Match contact candidates to HealthIA genogram members only by strong identifiers or explicit patient confirmation.
- Let the patient designate trusted contacts/caregivers and communication permissions.
- Resolve email/phone details when a mission needs a family contact.

Important boundary:
Google Contacts is an address book, not a clinical family graph. A contact named `Mamá` must not become a biological-relative medical fact without patient confirmation.

Example:
`Tell my wife what documents we need -> resolve confirmed caregiver contact -> show message preview -> send only after authorization -> store receipt.`

### 5. Education Studio Agent · Gemini + Veo + YouTube

Two distinct modes:

#### A. Curated education
- Search YouTube for relevant public education videos.
- Filter by language, captions/embeddability where possible, trusted channel/source policy, freshness when relevant, and topic fit.
- Present the original source and never imply HealthIA produced the content.

#### B. Generated education
- Gemini converts the patient's approved educational objective into a plain-language storyboard/script.
- Veo generates short explanatory visual segments when suitable.
- HealthIA assembles them into an education asset with a truth boundary and source references.
- Patient-specific clinical identifiers must not be published to YouTube.
- Generated patient-specific media should remain inside HealthIA/private storage unless the patient explicitly exports it.

Example:
`Explain my pneumonia to me -> 60-second educational package: what pneumonia is, why hydration/medication adherence matter, alarm signs, follow-up -> optional Veo visual sequence -> private HealthIA playback.`

### 6. Document & Application Agent · Google Drive + HealthIA document store

Purpose:
- Save patient-approved copies of generated applications, appointment letters, referral summaries, educational assets, receipts, and source PDFs to a dedicated Drive folder when authorized.
- Preserve canonical HealthIA evidence IDs and Drive file IDs.
- Avoid making Drive the clinical source of truth; HealthIA remains canonical and Drive is an export/synchronization target.
- For assistance applications, connect required documents to the existing Opportunity Application Packet before any external submission.

Example:
`Program requires ID + diagnosis letter -> HealthIA identifies existing documents -> patient adds missing letter -> application packet becomes complete -> export review copy to Drive -> patient authorizes submission.`

### 7. Mission / Follow-up Agent · Google Tasks

Purpose:
- Create patient-visible tasks for actionable steps such as obtaining a document, calling a clinic, fasting before a lab, carrying insurance, or following up after no reply.
- Keep HealthIA mission state canonical and synchronize only tasks the patient has authorized.
- Completing a Google Task does not automatically prove the clinical action occurred; HealthIA may request supporting evidence when needed.

Example:
`Bring ID and insurance card before Tuesday appointment -> two Tasks with due date -> appointment mission references both task IDs.`

### 8. Conversational Presence Agent · Gemini Live

Purpose:
- Real-time low-latency voice interaction with the same HealthIA Conversation Brain.
- Voice/vision is an interface, not an independent clinical brain.
- All tool use routes through the same deterministic safety, consent, authorization, and receipt layer.

Example:
Patient says aloud: `Busca un centro cerca para terapia de lenguaje y escríbele para preguntar disponibilidad.`
HealthIA can search Maps immediately, present 2–3 candidates, resolve contact channels, draft the inquiry, and request send authorization without leaving the conversation.

## High-value autonomous workflows

### Workflow A · Assistance-to-enrollment
1. Opportunity Radar finds a candidate program.
2. Official Program Verifier confirms requirements and source hash.
3. Eligibility Engine evaluates only supported facts.
4. Maps Agent locates enrollment/support offices.
5. People Agent resolves caregiver if patient requests family involvement.
6. Gmail Agent drafts/sends inquiry after authorization.
7. Gmail push detects reply without polling.
8. Application Agent updates requirements/status.
9. Calendar Agent schedules appointment after patient confirms slot.
10. Tasks Agent creates required-document/preparation tasks.
11. HealthIA posts one consolidated chat update with receipts.

### Workflow B · Appointment negotiation
1. Patient: `Consígueme una cita de neurología la semana que viene.`
2. HealthIA identifies location + preferred travel radius + insurance constraints if available.
3. Maps/verified provider directory identifies candidate centers.
4. Calendar Free/Busy identifies feasible patient windows.
5. Gmail sends a narrowly authorized availability request.
6. Inbox push receives replies.
7. HealthIA ranks offered slots against patient availability/travel.
8. Patient chooses.
9. Calendar event is created and receipt stored.
10. Tasks/Drive prepare documents.

### Workflow C · Approval/rejection monitoring
1. Application was externally submitted and has a real submission receipt.
2. Gmail watch monitors the relevant thread/labels.
3. Reply arrives.
4. HealthIA retrieves only the new relevant message/history.
5. Classifier extracts status and cites the original email.
6. `approved` -> update mission + Calendar/Tasks if next steps exist.
7. `missing_documents` -> update packet + ask patient for exact missing item.
8. `rejected` -> explain stated reason, preserve original wording/source, and optionally search appeal/alternative programs.

### Workflow D · Personalized education after a result
1. New result is parsed and stored with provenance.
2. HealthIA identifies what the patient asked to understand.
3. Gemini creates a plain-language explanation grounded in that result and the longitudinal record.
4. YouTube Agent can offer trusted public videos.
5. Education Studio can generate a private Veo visual explanation when useful.
6. The patient can save/export the asset; no patient-specific media is published by default.

## Permission model

Use OAuth scopes incrementally. Never request all Google scopes at login.

Suggested grant bundles:
- `maps_location`: location/search only.
- `calendar_read`: read/free-busy.
- `calendar_write`: create/update events.
- `gmail_read_relevant`: read/watch mailbox subset needed for active missions.
- `gmail_send`: send mail.
- `contacts_read`: People contacts read.
- `drive_export`: create/update HealthIA export files.
- `tasks_write`: create/update HealthIA-linked tasks.
- `youtube_search`: public education discovery.
- `youtube_upload`: separate high-friction permission; not needed for private patient-specific education.

Each mission stores the exact grant IDs/scopes used.

## Mutation policy

### Can run without a new confirmation when previously authorized
- read nearby places using already granted location/search scope;
- read Calendar free/busy;
- read the specific Gmail thread already attached to an active mission;
- retrieve previously authorized contacts;
- search public YouTube education;
- build draft emails/forms/events/tasks without executing them.

### Requires explicit patient authorization by default
- send/reply email;
- create/update/cancel Calendar event;
- share patient information with a family member/provider/program;
- create/update Drive exports containing patient data;
- submit an external application;
- upload/publish video;
- disclose a new clinical fact to an external recipient.

## Receipt contract

All side effects use a shared `GoogleActionReceipt` shape:

```json
{
  "id": "receipt_...",
  "patient_id": "patient_...",
  "mission_id": "mission_...",
  "provider": "google",
  "service": "gmail|calendar|maps|people|drive|tasks|youtube|veo",
  "action": "...",
  "resource_id": "provider-native-id",
  "status": "completed|blocked|failed|pending",
  "authorization_id": "authz_...",
  "idempotency_key": "...",
  "occurred_at": "RFC3339",
  "safe_summary": "patient-visible execution summary",
  "evidence_ids": []
}
```

Never store chain-of-thought in receipts.

## Cost strategy

- Prefer read APIs and deterministic ranking before Gemini.
- Use Gmail push notifications rather than inbox polling.
- Use field masks in Maps/Places and request only needed fields.
- Cache stable Place details by Place ID subject to Google Maps policies/terms.
- Search YouTube only on explicit education requests or bounded missions.
- Veo is generated only on explicit education requests; never as background decoration.
- Generate one patient-facing synthesis after tools complete instead of one LLM call per connector.

## Judge-visible demonstration

One strong end-to-end demo should prove multiple products through a single mission rather than showing disconnected buttons:

> Patient: `My son has autism. Find help near us and help me get an appointment.`

Expected visible trace:
1. HealthIA separates son's condition from patient's health.
2. Opportunity source is verified.
3. Maps shows nearby relevant centers/offices.
4. Patient selects a center.
5. Gmail draft appears with exactly what will be shared.
6. Patient authorizes send.
7. Gmail receipt appears.
8. Simulated/test or live reply is received via event-driven mailbox update.
9. HealthIA extracts offered appointment slots.
10. Calendar availability is checked.
11. Patient confirms one slot.
12. Calendar event + Tasks are created.
13. HealthIA offers a private plain-language education asset.
14. Discoveries/Mission receipt view shows the whole causal chain.

The winning story is not `we integrated eight APIs`; it is `HealthIA completed one real patient mission across eight systems without losing safety, context, consent, or proof.`

## Implementation sequence

P0 — shared Google connector boundary + OAuth grant registry + action receipt + idempotency.

P1 — Maps/Places read-only + Calendar free/busy + Gmail draft/send + Gmail push processing.

P2 — People contact resolution + Calendar write + Tasks synchronization.

P3 — Drive export/application-document linkage.

P4 — YouTube trusted education search + Gemini/Veo private Education Studio.

P5 — Gemini Live voice control through the same orchestrator.

## Non-goals until separately proven

- No autonomous medical diagnosis or prescription changes through Google tools.
- No sending messages to contacts inferred only from names.
- No claiming an appointment is booked until a provider reply or booking receipt exists.
- No claiming an application is approved/rejected from a vague email.
- No publishing patient-specific clinical videos to YouTube by default.
- No global OAuth consent request for every service at first login.
- No permanent polling loops.
