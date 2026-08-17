# All Things Agentic Hackathon — Bonus Points Evidence

This document isolates the optional bonus evidence from the frozen HealthIA ONE judging runtime. It does not change the final ONE SAFETY candidate or its claims.

## Bonus status

| Bonus path | Status | Evidence |
|---|---|---|
| Public build content | **PUBLISHED** | Public long-form build article: https://github.com/arisnachy/healthia-one/issues/93 |
| Social media post | **PUBLISHED — X** | Public post URL supplied after publication: https://x.com/i/status/2089481967821545835 |
| Google AI model integration | **LIVE PROVEN — VEO** | HealthIA Explain / Vertex AI Veo 3.1 Fast implementation and LIVE proof lineage: https://github.com/arisnachy/healthia-one/pull/43 |

## 1. Public build content

Public article:

**How we built HealthIA ONE: durable health agents, ONE SAFETY, and real Google AI**

https://github.com/arisnachy/healthia-one/issues/93

The article is public because `arisnachy/healthia-one` is a public repository and the issue is publicly accessible. It covers the project architecture, durable missions, evidence-first design, human authority boundaries, ONE SAFETY, real Google connectors, observability, and HealthIA Explain with Veo.

It contains the required declaration:

> **This piece of content was created for the purposes of entering the All Things Agentic Hackathon 2026.**

Do not mark a private, draft, or unlisted copy as the bonus artifact. Use the public URL above.

## 2. Social media post — published on X

Public X post:

https://x.com/i/status/2089481967821545835

The published copy is the prepared X version and includes the required hashtag:

> HealthIA ONE turns health chat into durable, consent-aware missions: Gemini + ADK, ONE SAFETY, real Google actions/receipts, Cloud Trace, and a live Vertex AI Veo 3.1 Fast education path.
>
> Demo: https://youtu.be/dOIhP22SxZ8
>
> #AllThingsAgenticHackathon

Publication was confirmed by the project owner with the public status URL on 2026-08-17. X did not expose the status body to this session's independent web fetch/index at the time the evidence file was updated, so the repository records the publication source precisely as **owner-confirmed public URL** rather than claiming an independent third-party content fetch.

## 3. Google AI bonus — Veo, no Gemma required

HealthIA already has a successfully exercised Google AI video path. There is no need to add Gemma solely for bonus eligibility.

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

PR #43 contains the isolated HealthIA Explain implementation and proof harness:

https://github.com/arisnachy/healthia-one/pull/43

Relevant source/proof paths in that lineage include:

- `healthia_one/education_video_google.py`
- `.github/workflows/healthia-explain-live-veo-sample.yml`
- `.github/healthia-explain-live-veo-trigger.txt`
- `.github/workflows/final-devpost-comprehensive-demo.yml`

The integration uses a mission-scoped Google grant, a one-time explicit authorization for the Veo action, `predictLongRunning`, `fetchPredictOperation`, private GCS output, MP4 validation, and a proof manifest.

### LIVE proof contract

The controlled LIVE workflow records a manifest with:

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

The workflow also validates that the downloaded output is a real-looking MP4 and records SHA-256 hashes for both the generated video and the generic prompt.

## 4. Why Veo is isolated from the frozen final runtime

The current ONE SAFETY judging build is feature-frozen. The Veo integration was already implemented and LIVE-tested in the HealthIA Explain lineage, but it is intentionally preserved separately rather than rebasing a large experimental feature branch over the final ONE SAFETY candidate.

This protects both truths:

1. the final judging runtime remains reproducible and unchanged; and
2. the Google AI bonus has concrete implementation plus LIVE Vertex AI evidence.

Do not describe the Veo branch as the exact final ONE SAFETY runtime. Describe it as an **implemented and LIVE-proven HealthIA ONE bonus integration preserved in its own evidence lineage**.

## 5. Judge-facing bonus checklist

- [x] Public build content exists.
- [x] Public build content includes the required hackathon-purpose declaration.
- [x] Public build content links to project/demo evidence.
- [x] Social post was published on X.
- [x] Social post uses `#AllThingsAgenticHackathon` in the prepared published copy.
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
- Official YouTube demo: https://youtu.be/dOIhP22SxZ8
- Public build article: https://github.com/arisnachy/healthia-one/issues/93
- Public X post: https://x.com/i/status/2089481967821545835
- Veo implementation / LIVE proof lineage: https://github.com/arisnachy/healthia-one/pull/43
- Repository: https://github.com/arisnachy/healthia-one
