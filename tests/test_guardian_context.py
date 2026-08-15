from __future__ import annotations

from datetime import datetime, timedelta, timezone

from healthia_one.devices import ingest_health_connect_batch
from healthia_one.guardian_context import assess_device_context
from healthia_one.models import DeviceMetric, DeviceObservation, HealthConnectSyncBatch, PatientState


def _obs(
    external_id: str,
    *,
    metric: DeviceMetric,
    value: float,
    hours_ago: int,
    metadata: dict | None = None,
    secondary_value: float | None = None,
    unit: str | None = None,
) -> DeviceObservation:
    units = {
        DeviceMetric.HEART_RATE: "bpm",
        DeviceMetric.BLOOD_PRESSURE: "mmHg",
    }
    return DeviceObservation(
        external_id=external_id,
        metric=metric,
        observed_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        value=value,
        secondary_value=secondary_value,
        unit=unit or units[metric],
        source_package="test.health",
        source_name="Test wearable",
        metadata=metadata or {},
    )


def test_guardian_recognizes_exertion_context_without_declaring_safety() -> None:
    state = PatientState()
    record = _obs(
        "hr-gym",
        metric=DeviceMetric.HEART_RATE,
        value=145,
        hours_ago=1,
        metadata={
            "activity_type": "running",
            "exercise_session_active": True,
            "location_context": "gym",
        },
    )

    assessment = assess_device_context(state, record, history=[])

    assert assessment is not None
    assert assessment.classification == "likely_exertion_related"
    assert assessment.notify_patient is False
    assert assessment.can_suppress_safety is False
    assert "not a diagnosis" in assessment.hypothesis.lower()


def test_guardian_detects_repeated_work_context_pattern_without_claiming_causality() -> None:
    now = datetime.now(timezone.utc)
    state = PatientState()
    history = [
        DeviceObservation(
            external_id=f"baseline-{index}",
            metric=DeviceMetric.HEART_RATE,
            observed_at=now - timedelta(days=7 - index),
            value=value,
            unit="bpm",
            metadata={"activity_type": "still", "location_context": "home"},
        )
        for index, value in enumerate((68, 72, 70))
    ]
    history.extend(
        DeviceObservation(
            external_id=f"work-{index}",
            metric=DeviceMetric.HEART_RATE,
            observed_at=(now - timedelta(days=4 - index)).replace(hour=10, minute=0),
            value=value,
            unit="bpm",
            metadata={"activity_type": "still", "location_context": "work"},
        )
        for index, value in enumerate((118, 116, 120))
    )
    current = DeviceObservation(
        external_id="work-current",
        metric=DeviceMetric.HEART_RATE,
        observed_at=(now - timedelta(minutes=5)).replace(hour=10),
        value=132,
        unit="bpm",
        metadata={
            "activity_type": "still",
            "location_context": "work",
            "hrv_rmssd_ms": 24,
            "sleep_minutes": 310,
        },
    )

    assessment = assess_device_context(state, current, history=history)

    assert assessment is not None
    assert assessment.classification == "recurring_context_pattern"
    assert assessment.repeated_pattern is True
    assert assessment.notify_patient is True
    assert assessment.requires_human_review is True
    assert "causality is not established" in assessment.hypothesis.lower()
    assert assessment.context["location_context"] == "work"


def test_guardian_ignores_precise_coordinates_and_keeps_semantic_context_only() -> None:
    state = PatientState()
    record = _obs(
        "hr-private-location",
        metric=DeviceMetric.HEART_RATE,
        value=110,
        hours_ago=1,
        metadata={
            "activity_type": "walking",
            "location_context": "outdoor",
            "latitude": 18.471,
            "longitude": -69.891,
        },
    )

    assessment = assess_device_context(state, record, history=[])

    assert assessment is not None
    assert assessment.context["location_context"] == "outdoor"
    assert assessment.context["precise_location_ignored"] is True
    assert "latitude" not in assessment.context
    assert "longitude" not in assessment.context


def test_deterministic_blood_pressure_safety_remains_authoritative_at_gym() -> None:
    state = PatientState()
    record = _obs(
        "bp-gym",
        metric=DeviceMetric.BLOOD_PRESSURE,
        value=170,
        secondary_value=105,
        hours_ago=1,
        metadata={
            "activity_type": "workout",
            "exercise_session_active": True,
            "location_context": "gym",
        },
    )
    batch = HealthConnectSyncBatch(
        device_id="watch-1",
        granted_metrics=[DeviceMetric.BLOOD_PRESSURE],
        records=[record],
    )

    result = ingest_health_connect_batch(state, batch)

    assert result["safety_alerts"]
    assert result["safety_alerts"][0]["risk_level"] == "priority"
    assert result["guardian_assessments"]
    guardian = result["guardian_assessments"][0]
    assert guardian["classification"] == "blood_pressure_context_review"
    assert guardian["can_suppress_safety"] is False
    assert result["guardian_summary"]["safety_can_be_suppressed"] is False
