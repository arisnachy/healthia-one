# All Things Agentic Hackathon — Bonus Points Evidence

This document isolates optional bonus evidence from the frozen HealthIA ONE judging runtime. It does not change the final ONE SAFETY candidate or its claims.

## Bonus status

| Bonus path | Status | Evidence |
|---|---|---|
| Public build content | **PUBLISHED** | Public long-form build article: https://github.com/arisnachy/healthia-one/issues/93 |
| Social media post | **PUBLISHED — X** | https://x.com/i/status/2089481967821545835 |
| Google AI model integration | **LIVE PROVEN — VEO** | HealthIA Explain / Vertex AI Veo 3.1 Fast lineage: https://github.com/arisnachy/healthia-one/pull/43 |

## 1. Public build content

Public article:

**How we built HealthIA ONE: durable health agents, ONE SAFETY, and real Google AI**

https://github.com/arisnachy/healthia-one/issues/93

The article is public and contains the required declaration:

> **This piece of content was created for the purposes of entering the All Things Agentic Hackathon 2026.**

It covers HealthIA ONE architecture, durable missions, evidence-first design, human authority boundaries, ONE SAFETY, real Google connectors, Cloud observability and the HealthIA Explain Veo integration.

## 2. Social media post — published on X

Public X post:

https://x.com/i/status/2089481967821545835

The prepared/published copy includes the required hashtag `#AllThingsAgenticHackathon` and points to the HealthIA ONE judging package.

Canonical final demo URL:

https://youtu.be/v7SJUkzzRxw

Publication was confirmed by the project owner with the public status URL on 2026-08-17. The repository records this precisely as owner-confirmed publication rather than claiming an independent third-party content fetch of the X body.

## 3. Google AI bonus — Veo

HealthIA has an implemented and successfully exercised Google AI video path. There is no need to add Gemma solely for bonus eligibility.

### Implemented model

- Provider: **Vertex AI Veo**
- Model: **Veo 3.1 Fast**
- Model ID: `veo-3.1-fast-generate-001`
- Feature: **HealthIA Explain** patient-education media
- LIVE sample: **8 seconds, 720p, 16:9, one synthetic clip**
- Storage: private Google Cloud Storage evidence path
- Clinical privacy boundary: Veo receives a prevalidated generic educational prompt, **not patient data / PHI**
- Person generation in the controlled proof: `disallow`

### Implementation evidence

PR #43 preserves the isolated HealthIA Explain implementation and proof harness:

https://github.com/arisnachy/healthia-one/pull/43

Relevant source/proof paths include:

- `healthia_one/education_video_google.py`
- `.github/workflows/healthia-explain-live-veo-sample.yml`
- `.github/healthia-explain-live-veo-trigger.txt`
- `.github/workflows/final-devpost-comprehensive-demo.yml`

The integration uses a mission-scoped Google grant, one-time explicit authorization for the Veo action, `predictLongRunning`, `fetchPredictOperation`, private GCS output, MP4 validation and a proof manifest.

### LIVE proof contract

```json
{
  "status": "LIVE_PASS",
  "provider": "Vertex AI Veo",
  "model": "veo-3.1-fast-generate-001",
  "duration_seconds": 8,
  "resolution": "720p",
  "sample_count": 1,
  "synthetic_only": true,
  "patient_data_sent": false,
  "person_generation": "disallow"
}
```

The workflow validates the generated MP4 and records SHA-256 hashes for the output and the generic prompt.

## 4. Why Veo remains isolated from the frozen final runtime

The current ONE SAFETY judging build is feature-frozen. The Veo integration was implemented and LIVE-tested in its HealthIA Explain lineage, but it remains separate rather than being rebased over the final ONE SAFETY candidate.

This preserves two truths:

1. the final judging runtime stays reproducible and unchanged; and
2. the Google AI bonus has concrete implementation plus LIVE Vertex AI evidence.

Describe Veo as an **implemented and LIVE-proven HealthIA ONE bonus integration preserved in its own evidence lineage**, not as the exact frozen ONE SAFETY runtime.

## 5. Judge-facing bonus checklist

- [x] Public build content exists.
- [x] Public build content includes the required hackathon-purpose declaration.
- [x] Public build content links to project/demo evidence.
- [x] Social post was published on X.
- [x] Social post uses `#AllThingsAgenticHackathon` in the prepared/published copy.
- [x] Public X status URL is recorded in the evidence manifest.
- [x] Google AI bonus uses Veo; no unnecessary Gemma integration added.
- [x] Veo model/version is named precisely.
- [x] Veo has an implementation path, not a slide-only claim.
- [x] Veo has a controlled LIVE Vertex AI generation proof.
- [x] Veo proof is synthetic-only and sends no patient data.
- [x] Veo output is validated and hashable.
- [x] Final ONE SAFETY runtime is not rewritten to obtain bonus points.

## Canonical links

- Final judge entry point: https://github.com/arisnachy/healthia-one/blob/main/JUDGES_START_HERE.md
- Official YouTube demo: https://youtu.be/v7SJUkzzRxw
- Public build article: https://github.com/arisnachy/healthia-one/issues/93
- Public X post: https://x.com/i/status/2089481967821545835
- Veo implementation / LIVE proof lineage: https://github.com/arisnachy/healthia-one/pull/43
- Repository: https://github.com/arisnachy/healthia-one
