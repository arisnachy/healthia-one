from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from healthia_one.models import (
    ActivityRecord,
    DeviceMetric,
    DeviceObservation,
    HealthConnectSyncBatch,
    PatientState,
    SourceRef,
    VitalRecord,
    WeightRecord,
)


def device_source(record: DeviceObservation) -> SourceRef:
    return SourceRef(
        source_type="health_connect",
        source_id=record.source_package or record.source_name or "health_connect",
        captured_at=record.observed_at,
        verified=True,
    )


def apply_observation(state: PatientState, record: DeviceObservation) -> str | None:
    source = device_source(record)
    if record.metric == DeviceMetric.STEPS:
        state.activity.append(
            ActivityRecord(
                measured_at=record.observed_at,
                steps=max(int(record.value), 0),
                active_minutes=max(int(record.metadata.get("active_minutes", 0)), 0),
                note=f"Sincronizado desde {record.source_name}",
                source=source,
            )
        )
        state.activity.sort(key=lambda item: item.measured_at)
        return "activity"
    if record.metric == DeviceMetric.WEIGHT:
        state.weights.append(
            WeightRecord(
                measured_at=record.observed_at,
                weight_kg=record.value,
                note=f"Sincronizado desde {record.source_name}",
                source=source,
            )
        )
        state.weights.sort(key=lambda item: item.measured_at)
        return "weight"
    if record.metric == DeviceMetric.HEIGHT:
        state.profile.height_cm = round(record.value, 1)
        return "profile"

    vital = VitalRecord(measured_at=record.observed_at, source=source)
    if record.metric == DeviceMetric.HEART_RATE:
        vital.pulse = int(record.value)
    elif record.metric == DeviceMetric.BLOOD_PRESSURE:
        vital.systolic = int(record.value)
        vital.diastolic = int(record.secondary_value or 0) or None
    elif record.metric == DeviceMetric.OXYGEN_SATURATION:
        vital.oxygen_saturation = record.value
    elif record.metric == DeviceMetric.RESPIRATORY_RATE:
        vital.respiratory_rate = record.value
    elif record.metric == DeviceMetric.BODY_TEMPERATURE:
        vital.temperature_c = record.value
    elif record.metric == DeviceMetric.BLOOD_GLUCOSE:
        vital.blood_glucose_mg_dl = record.value
    elif record.metric == DeviceMetric.CHOLESTEROL:
        vital.cholesterol_mg_dl = record.value
    elif record.metric == DeviceMetric.MENSTRUATION_PERIOD:
        if state.profile.reproductive_health.applicable:
            state.profile.reproductive_health.last_menstrual_period = record.observed_at.date()
            return "reproductive_health"
        return None
    else:
        return None
    state.vitals.append(vital)
    state.vitals.sort(key=lambda item: item.measured_at)
    return "vitals"


def ingest_health_connect_batch(state: PatientState, batch: HealthConnectSyncBatch) -> dict[str, Any]:
    accepted = 0
    duplicates = 0
    sections: set[str] = set()
    existing = set(state.synced_external_ids)
    for record in sorted(batch.records, key=lambda item: item.observed_at):
        if record.external_id in existing:
            duplicates += 1
            continue
        section = apply_observation(state, record)
        state.device_observations.append(record)
        state.synced_external_ids.append(record.external_id)
        existing.add(record.external_id)
        accepted += 1
        if section:
            sections.add(section)
    state.device_observations.sort(key=lambda item: item.observed_at)
    connection = next(
        (item for item in state.device_connections if item.provider == "health_connect" and item.device_id == batch.device_id),
        None,
    )
    if connection is None:
        from healthia_one.models import DeviceConnection

        connection = DeviceConnection(
            provider="health_connect",
            device_id=batch.device_id,
            display_name="Android Health Connect",
            status="connected",
            background_read=batch.background_read,
            last_sync_at=batch.synced_at,
        )
        state.device_connections.append(connection)
    else:
        connection.status = "connected"
        connection.background_read = batch.background_read
        connection.last_sync_at = batch.synced_at
        connection.last_error = ""
    state.updated_at = datetime.now(timezone.utc)
    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "sections": sorted(sections),
        "last_sync_at": batch.synced_at,
    }


def device_summary(state: PatientState) -> dict[str, Any]:
    latest_by_metric: dict[str, dict[str, Any]] = {}
    for record in state.device_observations:
        latest_by_metric[str(record.metric)] = record.model_dump(mode="json")
    return {
        "connections": [item.model_dump(mode="json") for item in state.device_connections],
        "record_count": len(state.device_observations),
        "latest_by_metric": latest_by_metric,
        "supported_metrics": [item.value for item in DeviceMetric],
        "truth_boundary": (
            "Health Connect is a consent-based synchronization layer. Availability and freshness depend on the "
            "device or source app. HealthIA does not infer that a missing metric was measured."
        ),
    }


def medication_device_cross_checks(state: PatientState) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    active_meds = [item for item in state.medication_plans if item.active]
    latest_vital = state.vitals[-1] if state.vitals else None
    latest_activity = state.activity[-1] if state.activity else None
    if latest_vital and latest_vital.systolic and latest_vital.diastolic and active_meds:
        checks.append(
            {
                "type": "blood_pressure_medication_context",
                "status": "context_available",
                "summary": (
                    f"La presión más reciente ({latest_vital.systolic}/{latest_vital.diastolic}) puede revisarse junto "
                    f"con {len(active_meds)} medicamento(s) activos y las tomas reportadas."
                ),
                "safety": "No cambiar dosis ni suspender tratamiento desde este hallazgo.",
            }
        )
    if latest_activity and latest_activity.steps < state.profile.care_plan.activity_goal_steps:
        checks.append(
            {
                "type": "activity_goal_context",
                "status": "review",
                "summary": (
                    f"El último registro contiene {latest_activity.steps} pasos frente a una meta registrada de "
                    f"{state.profile.care_plan.activity_goal_steps}."
                ),
                "safety": "Preguntar por barreras y síntomas antes de recomendar cambios.",
            }
        )
    return checks
