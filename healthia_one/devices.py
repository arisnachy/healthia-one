from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from healthia_one.guardian_context import assess_guardian_batch, guardian_pattern_summary
from healthia_one.integrations import health_data_provider_catalog
from healthia_one.safety import assess_vital
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


HEALTH_CONNECT_METRICS = tuple(item for item in DeviceMetric if item != DeviceMetric.CHOLESTEROL)


def device_source(record: DeviceObservation) -> SourceRef:
    return SourceRef(
        source_type="health_connect",
        source_id=record.source_package or record.source_name or "health_connect",
        captured_at=record.observed_at,
        # Pairing authenticates the bridge transport, not the clinical accuracy
        # of a sensor or the client-supplied Health Connect origin metadata.
        verified=False,
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
    initial_vital_count = len(state.vitals)
    prior_device_observations = list(state.device_observations)
    accepted_records: list[DeviceObservation] = []
    transport_identity_verified = any(
        bool(item.metadata.get("paired_connection_id") and item.metadata.get("paired_device_id"))
        for item in batch.records
    )
    for record in sorted(batch.records, key=lambda item: item.observed_at):
        scoped_external_id = f"{batch.device_id}:{record.external_id}"
        if scoped_external_id in existing or record.external_id in existing:
            duplicates += 1
            continue
        section = apply_observation(state, record)
        state.device_observations.append(record)
        state.synced_external_ids.append(scoped_external_id)
        accepted_records.append(record)
        existing.add(scoped_external_id)
        accepted += 1
        if section:
            sections.add(section)
    state.device_observations.sort(key=lambda item: item.observed_at)
    paired_connection_id = next(
        (str(item.metadata.get("paired_connection_id") or "") for item in batch.records if item.metadata),
        "",
    )
    connection = next(
        (
            item
            for item in state.device_connections
            if item.provider == "health_connect"
            and (
                (paired_connection_id and item.id == paired_connection_id)
                or (not paired_connection_id and item.device_id == batch.device_id)
            )
        ),
        None,
    )
    if connection is None:
        from healthia_one.models import DeviceConnection

        connection_payload = dict(
            provider="health_connect",
            device_id=batch.device_id,
            display_name="Android Health Connect",
            status="connected",
            background_read=batch.background_read,
            last_sync_at=batch.synced_at,
            permissions=[item.value for item in batch.granted_metrics],
        )
        if paired_connection_id:
            connection_payload["id"] = paired_connection_id
        connection = DeviceConnection(**connection_payload)
        state.device_connections.append(connection)
    else:
        connection.status = "connected"
        connection.background_read = batch.background_read
        connection.last_sync_at = batch.synced_at
        connection.last_error = ""
        connection.permissions = [item.value for item in batch.granted_metrics]
    state.updated_at = datetime.now(timezone.utc)

    # The deterministic safety layer is evaluated first and remains authoritative.
    # Guardian may add context, but can never suppress a priority/urgent safety alert.
    safety_alerts = []
    for vital in state.vitals[initial_vital_count:]:
        decision = assess_vital(vital)
        if decision.level.value not in {"priority", "urgent"}:
            continue
        safety_alerts.append(
            {
                "risk_level": decision.level.value,
                "message": decision.message,
                "must_stop_normal_flow": decision.must_stop_normal_flow,
                "evidence_id": vital.id,
                "requires_human_review": True,
            }
        )

    guardian_assessments = assess_guardian_batch(
        state,
        accepted_records,
        history=prior_device_observations,
    )

    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "sections": sorted(sections),
        "last_sync_at": batch.synced_at,
        "granted_metrics": [item.value for item in batch.granted_metrics],
        "transport_identity_verified": transport_identity_verified,
        "clinical_source_verified": False,
        "safety_alerts": safety_alerts,
        "guardian_assessments": [item.model_dump(mode="json") for item in guardian_assessments],
        "guardian_summary": guardian_pattern_summary(guardian_assessments),
    }


def device_summary(state: PatientState) -> dict[str, Any]:
    latest_by_metric: dict[str, dict[str, Any]] = {}
    for record in state.device_observations:
        latest_by_metric[str(record.metric)] = record.model_dump(mode="json")
    return {
        "connections": [item.model_dump(mode="json") for item in state.device_connections],
        "record_count": len(state.device_observations),
        "latest_by_metric": latest_by_metric,
        "supported_metrics": [item.value for item in HEALTH_CONNECT_METRICS],
        "provider_catalog": health_data_provider_catalog(),
        "truth_boundary": (
            "Health Connect is a consent-based synchronization layer. Availability and freshness depend on the "
            "device or source app. The bridge identity can be authenticated, but the sensor is not clinically "
            "certified by HealthIA. HealthIA does not infer that a missing metric was measured."
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
