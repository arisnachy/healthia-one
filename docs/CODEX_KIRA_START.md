# Start KIRA Ω inside Codex

Open this repository in Codex from the repository root. Codex will automatically load `AGENTS.md`, the project subagents under `.codex/agents/` and the `kira-healthia` skill under `.agents/skills/`.

Use the following mission to begin or resume hackathon work:

```text
Activate KIRA Ω for HealthIA ONE and invoke $kira-healthia.

Continue from the current repository state; do not repeat work already present in recent commits. First inspect main, the active branch, README, architecture, demo script, tests, current Judge Omega evidence and the real end-to-end patient flow.

Run a focused baseline and python scripts/judge_omega.py. Create or update an ExecPlan under .agent/execplans/ that records the current evidence, the three highest-impact blockers to winning the hackathon and a VICTORY-GATE.

Use subagents only on demand. Delegate read-heavy mapping to forja_explorer, patient-risk review to clinical_safety and final adversarial review to judge_omega. Use only one write-capable worker at a time: forja_worker. KIRA Ω remains responsible for architecture, integration and final verification.

Prioritize the strongest complete demonstration rather than feature quantity:
1. a patient writes a natural health concern;
2. HealthIA interprets the intent semantically;
3. it generates dynamic context-specific questions in blocks of no more than five without repeating answered information;
4. deterministic urgent-safety logic remains active even with external AI disabled;
5. the information becomes useful longitudinal context, documents, treatment continuity, family history, device context or follow-up as appropriate;
6. the patient receives clear, safe, honest next actions;
7. the complete flow is visually coherent and reproducible for judges.

Preserve zero-spend local mode, explicit guarded Google AI activation, hard request limits, synthetic demo data, patient privacy and the clinical truth boundary. Do not expose internal agent names in the patient interface. Do not claim live cloud, device, browser or model verification unless it actually ran.

Implement the highest-value blocker, add regression tests, run the applicable full verification gate, activate Judge Omega, repair every critical and credible high-impact finding, then continue to the next blocker while the current execution has a legitimate path forward.

Work on a feature branch. Keep commits factual and coherent. Open a pull request only when the diff has been reviewed and required checks pass. End with exact evidence, the PR or commit, real limitations and the next highest-value blocker.
```

## Useful Codex commands

```text
/skills
$kira-healthia
/agent
/review
```

For a quick verification that repository instructions loaded, ask Codex:

```text
Summarize the HealthIA ONE VICTORY-GATE, the allowed subagents and the rule governing write-capable agents before making any changes.
```

Expected behavior: Codex identifies KIRA Ω as the primary coordinator, keeps specialist agents on demand, permits only one writer at a time and refuses to claim completion without test and review evidence.