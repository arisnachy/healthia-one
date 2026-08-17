# HealthIA ONE — Hackathon Feature Freeze

Status: **ACTIVE once this proof-polish branch is merged and all gates are green.**

HealthIA ONE is now in evidence-first competition mode. New product features are frozen because the marginal judging value of adding capabilities is lower than the regression and storytelling risk.

## Allowed changes

- verified bug fixes;
- security fixes and fail-closed hardening;
- exact-head cloud proof;
- test coverage;
- demo clarity and timing;
- judge-facing documentation;
- Devpost consistency;
- accessibility or reliability fixes that do not expand scope.

## Not allowed without a verified judge gap

- new agents merely to increase agent count;
- new clinical autonomy;
- new connector families;
- new patient workflows unrelated to a demonstrated judging weakness;
- architectural rewrites;
- broad experimental Guardian behavior;
- claims without a durable proof artifact.

## Competition invariant

Every new change must answer at least one of these questions:

1. Does it make proven autonomous utility easier for a judge to see?
2. Does it strengthen architectural discipline, safety, state, failure handling or evidence?
3. Does it strengthen the live demo, reproducibility or visible Google Cloud proof?

If the answer is **no** to all three, the change waits until after the hackathon.

## Current judge story

```text
Sense
  → Understand
  → Decide
  → Authorize
  → ONE SAFETY
  → one-time HealthActionTicket
  → real connector
  → durable receipt
  → Patient Twin continues
```

For external work, HealthIA preserves the stricter invariant:

```text
authorization != execution ticket != connector execution != completion evidence
```

The model may reason. The human owns sensitive authority. ONE SAFETY gates one exact execution attempt. The real connector acts. Only durable evidence can close the loop.
