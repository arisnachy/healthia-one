# HealthIA ONE — Health data connection model

## Core rule

HealthIA must never ask a patient to type a Google, Samsung, Apple, Fitbit, Garmin or Withings password into HealthIA.

A connection uses one of three patterns:

1. **Operating-system health permission** — Health Connect on Android or HealthKit on iOS.
2. **Provider-hosted OAuth** — the patient signs in on the provider's own authorization page and approves scopes.
3. **Institutional authorization** — SMART on FHIR or another standards-based flow controlled by the hospital, insurer or records provider.

The HealthIA pairing code is separate. It proves that a specific companion app is allowed to send authorized records to a specific HealthIA backend. It does not replace the phone's health-data permission and it is not a Google/Samsung/Apple account login.

## Android and Google Health Connect

```text
watch / scale / health app
          ↓ writes authorized records
Health Connect on the Android phone
          ↓ user grants HealthIA Bridge selected read permissions
HealthIA Bridge
          ↓ eight-digit temporary backend pairing + device token
HealthIA ONE
```

The patient does not provide a Google password to HealthIA. Health Connect presents the operating-system permission screen and the patient chooses each data type.

The eight-digit temporary code solves a different problem: it securely pairs HealthIA Bridge with the backend that will receive the records.

## Samsung Health and Galaxy Watch

Preferred hackathon route:

```text
Galaxy Watch / Galaxy Ring / Samsung accessory
          ↓
Samsung Health on the phone
          ↓ user enables Samsung Health ↔ Health Connect sharing
Health Connect
          ↓ user grants HealthIA Bridge access
HealthIA ONE
```

A Samsung account may be used by Samsung Health for Samsung's own cloud synchronization. Those credentials stay inside Samsung Health and Samsung's authorization flow. HealthIA does not receive them.

The current Android bridge can consume Samsung-originated records after Samsung Health has synchronized them into Health Connect. A direct Samsung Health Data SDK adapter is optional for Samsung-specific data not available through Health Connect. Public distribution of that direct adapter requires Samsung partner registration and an approved package/signature.

## Apple Health and Apple Watch

A browser cannot directly read Apple Health. HealthIA needs an iOS companion app:

```text
Apple Watch / iPhone health source
          ↓
HealthKit store on the iPhone
          ↓ fine-grained system authorization
HealthIA iOS Bridge
          ↓ paired encrypted upload
HealthIA ONE
```

The patient grants individual HealthKit permissions on the iPhone. HealthIA never receives the Apple ID password.

An iOS bridge must include the HealthKit capability, purpose descriptions, availability checks, per-type authorization, provenance and a safe background-delivery strategy.

## Fitbit, Garmin, Withings and similar cloud providers

These generally use provider-hosted authorization:

```text
HealthIA → provider authorization page → patient approves scopes → provider returns token → HealthIA imports authorized data
```

The patient may sign in to the provider, but the sign-in form belongs to that provider. HealthIA receives a scoped token, not the password. Tokens must be encrypted, revocable, auditable and limited to the minimum scopes.

## Hospitals, laboratories and insurers

Use SMART on FHIR, OAuth or another standards-based institutional flow. The patient or authorized organization selects which records HealthIA may import. HealthIA must preserve source, timestamp, patient identity, consent and provenance.

## What is implemented today

- Android Health Connect companion source.
- Eight-digit backend pairing.
- Device-bound bearer token.
- Per-data-type Android permissions.
- Manual and supported background synchronization.
- Provenance and idempotent external record IDs.
- Synthetic device path for demonstrations without hardware.

Samsung Health and Galaxy devices are a conditional Health Connect route: HealthIA can consume their records only when Samsung Health writes them into Health Connect and the patient grants the corresponding permission. This path is not labeled hardware-verified until a physical-device evidence run is captured.

## What remains planned

- Native iOS HealthKit bridge.
- Direct Samsung Health Data SDK adapter for Samsung-specific data.
- Fitbit, Garmin and Withings OAuth adapters.
- SMART on FHIR institutional adapter.
- Production token encryption, account isolation and revocation workflows.
- Real-device validation matrix across phones, watches and data types.
