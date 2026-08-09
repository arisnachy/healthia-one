# Android Health Connect and complete patient profile

## Product contract

HealthIA ONE can receive consented observations from an Android companion app using Health Connect, preserve provenance, deduplicate records, merge them into the longitudinal patient state, and show the result in the patient profile and device dashboard.

This is a synchronization architecture, not a guaranteed medical real-time monitor.

## Supported Health Connect bridge records

- Steps
- Heart rate
- Blood pressure
- Weight
- Height
- Oxygen saturation
- Respiratory rate
- Body temperature
- Blood glucose
- Menstruation period

Cholesterol is displayed in HealthIA's vital/profile matrix when received from structured laboratory results or manual/clinical data. It is not treated as a core watch measurement.

## Data flow

```text
watch / phone / scale / cuff / source app
                    ↓
           Android Health Connect
                    ↓
     HealthIA Android Bridge + WorkManager
                    ↓
POST /api/devices/health-connect/sync
                    ↓
provenance + idempotency + longitudinal merge
                    ↓
profile, timeline, autonomous review, audit
```

Every device record contains an external ID, metric, time, unit, source package, source name, device information, recording method, and optional metadata. Duplicate external IDs are ignored.

The backend validates canonical units, supported ranges, ordered blood-pressure pairs, timezone-aware timestamps and metadata size before longitudinal merge. Pairing authenticates the bridge transport; it does not clinically certify the sensor or attest the source metadata supplied through Health Connect.

The bridge reads only the Health Connect data types actually granted by the patient. Denying one type does not block synchronization of other authorized types. HealthIA records the granted metric names on the connection and the patient can disconnect it from the Devices screen; future uploads with that connection credential are then rejected.

## Freshness boundary

Health Connect can support foreground and authorized background reads, but freshness depends on the source app and device. HealthIA must never display `Sin dato` as a normal measurement or infer that a missing observation was taken.

For closer-to-live Wear OS sensing, a later companion may use Health Services `PassiveMonitoringClient` and `ExerciseClient`. The Android Health Connect bridge is the first load-bearing path because it aggregates records from multiple Android sources with one permission surface.

## Patient profile

The profile now includes:

- general and contact data;
- birth date, sex at birth, gender identity, blood type, height;
- allergies and confirmed conditions;
- smoking, alcohol, drug use, coffee, tea, activity and nutrition notes;
- chronic, transfusion, trauma, surgical, hospitalization, immunization and non-pathological history;
- emergency contact;
- structured medications and reported adherence;
- family genogram;
- reproductive, menstrual, pregnancy and postpartum fields;
- vital snapshot, weight, BMI and contextual nutritional status.

## Medication organization

`POST /api/profile/medications/normalize` converts free text into a proposed structured record while preserving the original text. The output remains `unverified` until the patient confirms it, and it is never a prescription or medication change.

## Pregnancy and postpartum

When pregnancy mode is active, HealthIA can calculate an estimated gestational age and estimated due date from the registered last menstrual period. This is a planning estimate and must be reconciled with professional dating and ultrasound. Postpartum mode identifies the first 42 days / six weeks as the active puerperium window for continuity prompts.

HealthIA must not diagnose pregnancy complications, replace prenatal care, or delay urgent assessment.

## BMI boundary

BMI is calculated from the latest weight and recorded height. Adult, non-pregnant status uses standard WHO adult bands. Children, adolescents, and pregnancy are explicitly routed to age- or pregnancy-specific assessment rather than receiving an adult nutritional label.

## Android build status

`android-health-bridge/` contains source for permissions, foreground sync, periodic WorkManager sync, provenance mapping, and API upload. CI verifies its contracts and permissions statically. A real Android device and actual Health Connect sources are still required before claiming hardware validation.
