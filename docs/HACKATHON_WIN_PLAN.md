# HealthIA ONE — Hackathon Victory Plan

## Final competitive position

HealthIA ONE enters **The Taskmaster** with one memorable thesis:

> **HealthIA does not finish when the model talks. It finishes when the evidence-backed patient task actually exists, remains auditable, and is available for the next conversation.**

The product is no longer in feature-discovery mode. The remaining work is submission hardening: make the latest green product, its real Google ADK/Gemini execution, and its durable Taskmaster loop unmistakable to a judge in one live English demonstration.

## Proven product foundation

- Demand-driven Google ADK clinical runtime with real function-tool execution.
- Gemini 3.5 Flash through Vertex AI/service identity in the proof deployment.
- Deterministic safety boundary before routine model behavior.
- Human-first adaptive clinical conversation: five-question contract preserved internally, one useful question shown at a time.
- Free-text answers, optional suggestions, “I don’t know,” and prior-answer memory.
- Chat-driven Health OS navigation/actions through a deterministic allowlist rather than arbitrary model DOM control.
- Evidence-first multimodal result ingestion: original bytes stored before model interpretation.
- Patient-scoped Firestore state and private GCS original evidence.
- Clinical-twin provenance back to result/document evidence.
- Closed-loop `result_explanation` mission that reaches `COMPLETED` only when persisted evidence exists.
- Authenticated patient isolation and cross-patient document denial.
- Logout/login and genuine Cloud Run cross-revision continuity proof.
- CI, Chromium, LAB OMEGA, JUDGE Ω, release and public-video verification gates.

Canonical evidence: `docs/EVIDENCE.md` and `hackathon/judge_omega_scorecard.json`.

## The winning four-minute story

The final judge video must be a **continuous live application capture**, not screenshots, slides, a generated product mockup, or a montage that hides failures.

### 1. Promise

Show the live HealthIA login/application and state the problem in one sentence: patient context is fragmented and most AI conversations disappear when the chat ends.

### 2. Human conversation + real ADK

Use a synthetic patient complaint in English. Prove that:

- Google ADK/Gemini are ready on the deployed runtime;
- the clinical block contains exactly five adaptive questions under the runtime contract;
- only one question is visible at a time;
- free text and “I don’t know” remain available;
- answered turns stay visible as conversation history;
- a second block, if requested by Gemini, receives prior answers instead of restarting.

Do not present the internal five-question contract as a form.

### 3. Chat as Health OS

From chat, issue a safe workspace command such as “Open my results.” The visible application must navigate because of the assistant’s deterministic `ui_action`, demonstrating that conversation is an operating surface, not merely a text box.

### 4. Evidence-first multimodal task

Upload one synthetic laboratory PDF. Show the real result surface after parsing and explain:

- original evidence is persisted first in private GCS;
- Gemini extracts only readable evidence;
- Firestore commits patient-scoped structured state;
- the clinical twin retains provenance;
- failure is fail-closed rather than fabricated.

### 5. Taskmaster closure

Return to chat and ask HealthIA to explain the newly uploaded result and confirm it was saved. Show the completed mission and correlated evidence. The key sentence is:

> **The mission is not complete because the model answered. It is complete because the persisted result and original document actually exist.**

### 6. Durable continuity + Cloud proof

Log out and back in. Confirm that the result, original document and completed mission remain. Finish on the live application with visible runtime proof for Cloud Run, Gemini/Vertex AI, ADK, Firestore and GCS.

## CINE Ω — temporary audiovisual strike team

CINE Ω exists only for the final hackathon submission package.

- **DIRECTOR** — judge story, pacing and narrative economy.
- **LIVE-CAM** — one-take Playwright capture of the deployed application.
- **NARRATOR** — English explanatory voice track and matching captions.
- **COMPLIANCE** — truth boundary, duration and submission-language checks.
- **CUTLOCK** — rejects static fake scenes, hidden failures, bad duration, console errors or evidence mismatch.
- **JUDGE-EYE** — adversarial review of what a judge can actually understand and remember.

## Hard video gates

A replacement video is rejected unless all are true:

1. It records the exact current candidate deployed to Cloud Run.
2. The application is live and interactive throughout the product demonstration.
3. English is the judge-facing language.
4. The conversational clinical UI shows exactly one question at a time while preserving the five-question backend contract.
5. Google ADK and Gemini readiness are verified from the live runtime.
6. The synthetic multimodal result reaches parsed persisted state with original-document provenance.
7. The Taskmaster result mission reaches `COMPLETED` with correlated result/document evidence.
8. Logout/login restores the durable state.
9. Browser console/page errors are zero.
10. Recording duration remains within the submission limit configured by the workflow.
11. Synthetic data only; no real patient identifiers or clinical records.
12. No unsupported diagnosis, prescription authority, regulatory-clearance or hardware claims.

## What not to add now

- No new feature merely to make the feature list longer.
- No arbitrary Gemini-generated CSS selectors or silent destructive UI actions.
- No fake autonomous swarm story when the proven architecture is intentionally demand-driven.
- No static screenshots masquerading as a live demo.
- No replacement of the preserved passing video until the new exact-candidate recording itself passes.

## Definition of victory

A judge should be able to describe HealthIA after watching once:

> **“It is the health agent that keeps working from conversation to durable evidence, and it only closes the mission when the outcome really exists.”**

That clarity — combined with the already-proven Google Cloud/ADK architecture — is the final competitive objective.
