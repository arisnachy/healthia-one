from datetime import date, datetime, timedelta, timezone

from healthia_one.devices import device_summary, ingest_health_connect_batch
from healthia_one.models import (
    DeviceMetric,
    DeviceObservation,
    HealthConnectSyncBatch,
    PatientState,
    WeightRecord,
)
from healthia_one.profile import calculate_bmi, normalize_medication_text, pregnancy_summary, profile_summary


def test_bmi_and_adult_nutritional_status() -> None:
    state = PatientState()
    state.profile.birth_date = date(1982, 2, 20)
    state.profile.height_cm = 165
    state.weights = [WeightRecord(weight_kg=80.0)]
    summary = profile_summary(state)
    assert summary["vitals"]["bmi"] == calculate_bmi(80.0, 165)
    assert summary["vitals"]["nutritional_status"] in {"Preobesidad", "Obesidad clase I"}


def test_profile_without_birth_date_does_not_invent_age_or_adult_classification() -> None:
    state = PatientState()
    state.profile.height_cm = 165
    state.weights = [WeightRecord(weight_kg=80.0)]
    summary = profile_summary(state)
    assert summary["age_years"] is None
    assert summary["vitals"]["bmi"] == calculate_bmi(80.0, 165)
    assert summary["vitals"]["nutritional_status"] == "Requiere edad para clasificar"


def test_pregnancy_and_postpartum_calculations_are_contextual() -> None:
    reproductive = PatientState().profile.reproductive_health
    reproductive.applicable = True
    reproductive.pregnancy_status = "pregnant"
    reproductive.last_menstrual_period = date(2026, 6, 1)
    result = pregnancy_summary(reproductive, date(2026, 8, 6))
    assert result["gestational_age_weeks"] == 9
    assert result["estimated_due_date"] == date(2027, 3, 8)
    assert "confirmarse" in result["dating_note"]

    reproductive.pregnancy_status = "postpartum"
    reproductive.delivery_date = date(2026, 7, 20)
    result = pregnancy_summary(reproductive, date(2026, 8, 6))
    assert result["postpartum_day"] == 17
    assert result["postpartum_active"] is True


def test_medication_normalizer_preserves_original_and_requires_confirmation() -> None:
    plan = normalize_medication_text("Losartán 50 mg vía oral cada 24 horas")
    assert plan.original_text.startswith("Losartán")
    assert plan.name == "Losartán"
    assert plan.dose_value == 50
    assert plan.dose_unit == "mg"
    assert plan.route == "oral"
    assert plan.frequency_times_per_day == 1
    assert plan.verification_status == "unverified"


def test_health_connect_batch_is_idempotent_and_updates_longitudinal_state() -> None:
    state = PatientState()
    now = datetime.now(timezone.utc)
    records = [
        DeviceObservation(
            external_id="steps-1",
            metric=DeviceMetric.STEPS,
            observed_at=now,
            value=4321,
            unit="count",
            source_package="com.example.watch",
        ),
        DeviceObservation(
            external_id="bp-1",
            metric=DeviceMetric.BLOOD_PRESSURE,
            observed_at=now + timedelta(seconds=1),
            value=132,
            secondary_value=84,
            unit="mmHg",
            source_package="com.example.cuff",
        ),
        DeviceObservation(
            external_id="height-1",
            metric=DeviceMetric.HEIGHT,
            observed_at=now,
            value=166,
            unit="cm",
        ),
    ]
    batch = HealthConnectSyncBatch(device_id="android-1", background_read=True, records=records)
    first = ingest_health_connect_batch(state, batch)
    second = ingest_health_connect_batch(state, batch)
    assert first["accepted"] == 3
    assert second["accepted"] == 0
    assert second["duplicates"] == 3
    assert state.activity[-1].steps == 4321
    assert state.vitals[-1].systolic == 132
    assert state.vitals[-1].diastolic == 84
    assert state.profile.height_cm == 166


def test_device_summary_requires_real_pairing_for_live_claim() -> None:
    state = PatientState()
    summary = device_summary(state)
    assert summary["provider"] == "Android Health Connect"
    assert summary["connected"] is False
    assert summary["records_received"] == 0
