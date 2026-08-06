# Clinical safety contract

HealthIA ONE is a patient continuity assistant, not a physician or autonomous medical device.

## Allowed

- Organize patient-entered information.
- Record measurements and source metadata.
- Detect deterministic thresholds and missing follow-up.
- Explain what a result measures and prepare questions.
- Offer low-risk behavior micro-goals after asking about barriers.
- Recommend an appropriate level of human evaluation.
- Maintain a mission until a patient or professional response is recorded.

## Blocked

- Confirming a diagnosis.
- Prescribing, stopping, or changing medication.
- Signing clinical orders or certificates.
- Declaring a dangerous symptom safe.
- Hiding uncertainty or source provenance.
- Uploading real patient data to the public hackathon environment.

## Required emergency behavior

When deterministic urgent language or vital thresholds are detected, routine coaching stops and the system directs the patient to immediate human care. The message must not depend on a model call.

## Proactive behavior

Proactive interventions are allowed only for explicitly consented signal classes. Every intervention includes an explanation and can be dismissed. Future work must add per-category quiet mode and revocation.
