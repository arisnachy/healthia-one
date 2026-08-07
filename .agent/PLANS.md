# HealthIA ONE ExecPlans

An ExecPlan is a living implementation document for work that crosses several files, has multiple milestones, changes architecture or requires repeated verification. It must be usable by a new Codex session with only the repository and the plan.

## Required behavior

- Read the complete plan before acting.
- Continue from the recorded state; do not redo completed milestones.
- Keep the plan updated after every meaningful milestone, discovery, failed approach or changed decision.
- Resolve ordinary implementation ambiguities from repository evidence instead of repeatedly asking the user.
- Record commands and results precisely.
- Distinguish automated verification, browser verification, live external verification and unverified claims.
- Do not mark a milestone complete merely because code was written.

## ExecPlan template

```markdown
# <Outcome-oriented title>

## Mission
Describe the patient or product outcome and why it matters to the hackathon.

## VICTORY-GATE
List observable acceptance criteria, required tests, required review and any external evidence needed.

## Current repository state
Record branch, relevant recent commits, existing implementation, known failures and constraints.

## Safety, privacy and spending invariants
List clinical boundaries, data restrictions, authorization requirements and cost controls that must remain true.

## Code-path map
Identify UI/API entry points, state transitions, services, contracts, storage, tests and documentation involved.

## Milestones
- [ ] Baseline reproduced and evidence captured.
- [ ] Canonical design selected.
- [ ] Implementation completed.
- [ ] Focused regression tests pass.
- [ ] Integration and smoke checks pass.
- [ ] Browser or runtime behavior verified where possible.
- [ ] Clinical Safety review completed when applicable.
- [ ] Judge Omega review completed.
- [ ] Critical and high-impact findings repaired.
- [ ] Final diff and documentation reviewed.

## Progress log
Use dated entries with completed work, commands, results and next action.

## Decisions
Record important choices, alternatives rejected and supporting evidence.

## Failures and recovery
Record exact failures, root-cause hypothesis, attempted corrections and the route that worked.

## Verification evidence
List every command, output summary, screenshot or external test. State what remains unverified.

## Judge Omega findings
Track finding, severity, repair and re-verification.

## Final state
Summarize delivered behavior, commits or PR, known limitations and next highest-value blocker.
```

Store active plans under `.agent/execplans/` with descriptive kebab-case names. Do not commit secrets, private patient information, raw credentials or private chain-of-thought to a plan.