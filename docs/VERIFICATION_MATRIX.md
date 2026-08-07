# HealthIA ONE verification matrix

This document separates what is proven automatically from what still requires live evidence. It is intentionally stricter than a feature checklist.

## Automated gates

The main verification workflow proves the following in a clean hosted runner:

| Area | Evidence | Current automated gate |
|---|---|---|
| Python behavior | Unit and integration tests | `pytest` |
| Whole backend | Fourteen API and state workflows | `python scripts/full_system_check.py` |
| Real browser behavior | Chromium with the actual HTML, CSS and JavaScript | `python scripts/browser_smoke.py` |
| Adaptive clinical intake | Two different five-question blocks and exactly two fake-model calls | Browser smoke + dynamic intake tests |
| Demand-driven specialists | Only selected deterministic tools execute | Clinical tool tests |
| Cost boundary | Local mode blocks Google calls and guarded mode counts them | Cost-guard tests |
| Safety | Urgent text bypasses routine interview | System check + safety tests |
| Mission closure | Interview advances to professional review with closure evidence | System check |
| Patient data workflows | Measurements, results, documents, treatment, family, appointments and goals | System check |
| Device protocol | Six-digit pairing, bearer token and synthetic Health Connect sync | System check |
| Patient control | Consent, quiet hours, snooze and mute | System check |
| Auditability | Timeline, audit trail and safe export | System check |
| Frontend quality | One visible identity, collapsed icon rail, no hidden first response and no pending-message race | Browser smoke |
| Windows launchers | PowerShell parse gate | CI |
| Release package | Manifest, expected contents and tests rerun from extracted ZIP | CI |
| Hackathon evidence discipline | JUDGE Ω scorecard validation | CI |

Browser evidence is uploaded as the `HealthIA-browser-smoke` artifact. The release candidate is uploaded separately as `HealthIA-ONE-release-candidate`.

## Zero-spend versus live proof

The hosted browser test uses a fake Gemini transport so it can verify orchestration without spending credits. It proves the product contract, not access to the live provider.

The following requires a short, controlled live test:

1. Start HealthIA with guarded Gemini and a small request ceiling.
2. Submit one clinical complaint.
3. Confirm `question_source=gemini_dynamic`, five adaptive questions, a JUDGE Ω approval and one consumed request.
4. Capture the browser and the corresponding structured server log.

A normal two-block interview is designed to use no more than two Gemini requests.

## Remaining hard gates before submission

These items must not be represented as completed until their evidence exists:

| Gate | Required proof |
|---|---|
| Google ADK is the visible runtime | One trace showing ADK selecting the same tools used by the patient workflow |
| Durable Google Cloud execution | Cloud Scheduler, Pub/Sub or Cloud Tasks invoking a Cloud Run worker with retry evidence |
| Persistent cloud state | Firestore write and read connected to the same mission trace |
| Real cloud model call | Correlated Cloud Run or Vertex/Gemini log with secrets hidden |
| Physical Android integration | Health Connect permission screen, real device pairing and one authorized record |
| Apple Health integration | Native iOS HealthKit bridge; currently not implemented |
| Multi-user isolation | Authenticated identities and tests proving cross-patient data separation |
| Final submission package | Final architecture diagram, approximately four-minute demo, write-up and evidence index |

## Required demo path

The winning demonstration should prove one coherent mission rather than many disconnected screens:

1. Patient or authorized device provides a health event.
2. HealthIA detects the intent or trigger.
3. The agent requests only the missing information.
4. Only relevant specialists execute tools.
5. JUDGE Ω validates the plan and evidence.
6. HealthIA performs a concrete next action.
7. New evidence updates the longitudinal record.
8. The mission reaches a visible closure condition or professional-review state.
9. The same trace is visible in Google Cloud logs and persistent state.

## Local commands

```powershell
.\START-HEALTHIA.cmd
```

Choose `L` for zero-spend testing or `G` for guarded Gemini.

Comprehensive backend verification:

```powershell
.\.venv\Scripts\python.exe scripts\full_system_check.py
```

Browser verification after installing Chromium once:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts\browser_smoke.py
```
