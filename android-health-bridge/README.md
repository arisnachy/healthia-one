# HealthIA Android Health Bridge

Android companion source for reading authorized records from Health Connect and sending idempotent batches to HealthIA ONE.

## Scope

- Health Connect 1.1.0 stable.
- Steps, heart rate, blood pressure, weight, height, oxygen saturation, respiratory rate, body temperature, blood glucose, and menstruation periods.
- Background reads through Health Connect permission plus WorkManager.
- Provenance: Health Connect metadata, package, device, recording method, and external record ID.
- No silent access: the patient grants each permission and may pause or revoke access.

## Important boundary

Health Connect is a synchronization store, not a guaranteed continuous clinical stream. A metric exists only when a compatible device or source app writes it. Cholesterol is not a core consumer Health Connect record in this bridge; HealthIA receives it from structured laboratory results or a future FHIR/medical-record integration.

## Local development

1. Open this folder in Android Studio.
2. Change `HEALTHIA_BASE_URL` in `app/build.gradle.kts` to your reachable backend. The emulator uses `http://10.0.2.2:8000`.
3. Install on Android 9+; Android 14 includes Health Connect in the framework. Earlier compatible versions may require the Health Connect app.
4. Grant only the data types used by the patient.
5. Press **Sync now** or allow the 15-minute WorkManager schedule.

A real-device run is still required before claiming hardware validation.
