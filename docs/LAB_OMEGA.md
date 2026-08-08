# LAB Ω — HealthIA ONE functional laboratory

LAB Ω is the verification environment for UI, patient workflows, language behavior and future chat innovation. It is intentionally separate from the previously frozen hackathon candidate so experimental work cannot erase a known-good recovery point.

## Mission

Every patient-visible capability must have a verifiable contract. A window does not count as functional because it renders; LAB Ω must exercise the action behind it and, where possible, read the resulting durable state back from the API.

## Current automated browser matrix

`scripts/lab_omega.py` launches the real FastAPI app locally with authentication enabled, MemoryStore isolation, zero Google AI spend and real Chromium.

It currently proves:

| Area | Contract |
| --- | --- |
| Login EN | `en-US` browser renders the English login and polished continuity gateway |
| Login ES | `es-DO` browser automatically renders the Spanish login |
| Registration | A synthetic patient is created through the real registration UI and redirected into the authenticated app |
| Registered views | Every current `[data-open]` destination must have a matching visible `#view-*` window |
| Left rail | collapse and restore both work |
| Context rail | collapse and restore both work |
| Blood pressure | form opens, saves, and the exact value is read back from `/api/bootstrap` |
| Weight | form opens, saves, and the exact value is read back from durable patient state |
| Activity | form opens, saves, and the exact value is read back from durable patient state |
| Structured result | a real JSON file is uploaded, parsed, explained in English under `en-US`, persisted and linked to an original document |
| Input language | English input emits `Accept-Language: en`; Spanish input overrides the English OS locale and emits `Accept-Language: es` |
| Account | account dialog exposes authenticated identity and opens each registered account sub-view |
| Logout | session closes and the browser returns to the real login |
| Browser integrity | zero page errors and zero console errors |
| Evidence | screenshots, JSON report and a real-time Chromium WebM are stored under `dist/lab-omega/` |

The existing `scripts/browser_smoke.py` remains an independent clinical conversation proof. LAB Ω does not replace it.

## Language contract

HealthIA is **English-first for hackathon presentation** but patient-language adaptive:

1. The visible shell defaults to English.
2. The browser/OS locale selects English or Spanish automatically.
3. The current patient's input language can override the OS language for the response.
4. `Accept-Language` is bound to the authenticated request context.
5. Google ADK clinical questions receive an explicit patient-visible response locale.
6. Gemini clinical synthesis and generic patient responses receive the same language instruction.
7. Deterministic urgent-safety language recognizes both English and Spanish before any model call.
8. Structured result explanations follow the request language.

Low-confidence content such as a numeric measurement falls back to the OS/request locale instead of guessing.

## Demo contract

`scripts/record_submission_demo.py` is the only final judge recorder. Its next live Cloud run must satisfy all of these:

- `locale="en-US"`;
- English patient account and English clinical complaint;
- English Gemini + ADK question blocks and final orientation;
- English Taskmaster result request;
- no static title-card sequence: captions are overlays on the live app;
- every recorded operation is an actual interaction against the private Cloud Run deployment;
- live Gemini 3.5 Flash, Google ADK, Firestore and GCS readiness;
- multimodal original evidence + clinical twin + completed mission;
- logout/login continuity;
- zero page/console errors;
- continuous approximately four-minute WebM.

The older passing demo remains historical evidence. It is not the target final presentation after this multilingual/UI mission.

## FORJA innovation gate

New chat ideas are welcome only when they use real existing state or add a tested capability. LAB Ω rejects decorative “agent theater.” Current high-value candidates:

1. **Mission ribbon in chat** — show the current durable mission and its next verifiable action directly above the composer.
2. **Evidence drawer** — one click from a HealthIA response to the exact persisted result/document/timeline evidence behind it.
3. **Contextual action bar** — actions such as upload result, record blood pressure or open the linked original appear only when the current conversation makes them relevant.
4. **Language-aware quick actions** — suggested actions use the current UI language but the response still follows the patient's actual input language.
5. **Continuation prompts** — after a result, measurement or relogin, surface the existing unresolved mission rather than starting a new generic conversation.

Each candidate must pass three questions before implementation: does it use real data, does it change what the patient can actually accomplish, and can LAB Ω prove the outcome?

## Next expansion

After the base LAB is green, extend the matrix to every injected secondary module (profile, privacy, devices, family, documents, treatment, appointments, providers and cost controls), then add a gated **live-Cloud LAB** for output-quality checks that require Gemini/ADK rather than deterministic local mode.
