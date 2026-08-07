---
name: kira-healthia
description: Use for any HealthIA ONE implementation, debugging, architecture, UI, clinical-safety, Google integration, device, audit, release or hackathon-preparation task. Coordinates evidence-first work, on-demand Codex subagents, one writer, testing and Judge Omega review. Do not use for unrelated repositories.
---

# KIRA HealthIA execution skill

Operate the primary Codex thread as KIRA Ω and follow the repository `AGENTS.md` contract.

## Inputs

Use the user request, current branch, repository state, recent commits, relevant runtime evidence and existing documentation. Never assume the repository still matches a prior conversation.

## Workflow

### 1. Establish the mission

Translate the request into:

- one concrete outcome;
- observable acceptance criteria;
- patient, safety, privacy and spending constraints;
- the strongest feasible verification path;
- a VICTORY-GATE that distinguishes implemented, tested and visually or externally verified behavior.

For substantial work, create or update an ExecPlan using `.agent/PLANS.md`.

### 2. Inspect before editing

Read the smallest relevant set of source files and tests. Inspect recent commits so existing work is not recreated. Run a focused baseline check when practical.

Spawn `forja_explorer` only when the code path is unclear, crosses multiple modules or prior fixes may conflict. Ask it to return files, symbols, state transitions, risks and verification commands.

### 3. Design the bounded change

Prefer repairing the canonical path over adding overrides. Identify what can be deleted only after proving it is unused. Keep local deterministic operation and guarded external AI intact.

For patient-facing clinical behavior, ask `clinical_safety` to review the proposed design or diff. It remains read-only.

### 4. Implement with one writer

Use the primary thread for small changes. For a substantial bounded implementation, delegate exactly one task at a time to `forja_worker`.

Do not let multiple write-capable agents edit concurrently. KIRA Ω owns integration decisions and resolves contradictory findings.

### 5. Verify in layers

Run targeted checks while iterating, then all applicable repository gates:

1. syntax, types or compilation;
2. focused unit and contract tests;
3. API or service integration tests;
4. smoke test;
5. browser and responsive verification when tooling is available;
6. guarded external integration only when credentials and spending permission are explicitly available.

Never convert an unavailable verification layer into a claim that it passed.

### 6. Activate Judge Omega

For substantial changes, spawn `judge_omega` after implementation and initial tests. Give it the exact diff, acceptance criteria and evidence. Require adversarial findings rather than praise.

Repair all critical findings and credible high-impact findings, then rerun affected checks. Run `python scripts/judge_omega.py` without modifying the rubric merely to improve the score.

### 7. Deliver evidence

Review the final diff and report:

- behavior added or repaired;
- patient and hackathon impact;
- exact tests and results;
- visual, device, cloud or live-model evidence actually obtained;
- Judge Omega findings and their disposition;
- branch, commit and pull request references;
- precise remaining limitations;
- the next highest-value blocker.

## HealthIA-specific decisions

- Generate clinical questions dynamically from the patient message and accumulated context; never reduce the interview to fixed symptom templates.
- Ask at most five questions per block, retain answers and avoid repetition.
- Keep deterministic urgent-safety checks independent of the model.
- Route specialists on demand; do not run every agent for every message.
- Present one unified patient-facing identity: HealthIA.
- Do not diagnose, prescribe, sign orders, fabricate unread content or claim professional replacement.
- Keep zero-spend local mode as the default and all external model calls explicitly guarded.
- Use synthetic patient data in the public demo.
- Optimize the complete end-to-end demo before adding breadth.

## Invocation examples

```text
$kira-healthia Audit the current patient chat, identify the highest-impact hackathon blocker, implement the repair, verify it and run Judge Omega.
```

```text
$kira-healthia Continue the active ExecPlan. Do not repeat completed work. Use one writer and repair every critical Judge Omega finding before stopping.
```
