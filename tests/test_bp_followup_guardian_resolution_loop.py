from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from healthia_one.autopilot_worker import care_continuity_due
from healthia_one.bp_followup_guardian import CONSENT_SIGNAL, MISSION_TYPE, bp_followup_due, reconcile_bp_followup_guardian
from healthia_one.config import Settings
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import plan_guardian_notification
from healthia_one.models import (
    DeviceMetric,
    DeviceObservation,
    HealthConnectSyncBatch,
    MissionStatus,
    PatientState,
    RiskLevel,
    VitalRecord,
)
from healthia_one.service import HealthIAService
from healthia_one.store import MemoryStore


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _authorized_state() -> PatientState:
    state = PatientState()
    if CONSENT_SIGNAL not in state.consent.signal_types:
        state.consent.signal_types.append(CONSENT_SIGNAL)
    state.profile.care_plan.blood_pressure_due_days = 3
    return state


def _old_bp() -> VitalRecord:
    return VitalRecord(
        measured_at=NOW - timedelta(days=5),
        systolic=138,
        diastolic=86,
        pulse=74,
    )


def _mission(state: PatientState):
    return next(item for item in state.missions if item.mission_type == MISSION_TYPE)


def test_bp_followup_requires_separate_explicit_consent_signal() -> None:
    state = PatientState()
    state.vitals.append(_old_bp())

    assert "vitals" in state.consent.signal_types
    assert CONSENT_SIGNAL not in state.consent.signal_types
    assert bp_followup_due(state, now=NOW) is False
    report = reconcile_bp_followup_guardian(state, now=NOW)
    assert not report["created"]
    assert not state.missions


def test_overdue_established_bp_stream_opens_durable_measurement_mission() -> None:
    state = _authorized_state()
    old = _old_bp()
    state.vitals.append(old)

    report = reconcile_bp_followup_guardian(state, now=NOW)

    mission = _mission(state)
    assert report["created"]
    assert mission.status == MissionStatus.WAITING_PATIENT
    assert mission.evidence_ids == [old.id]
    assert "new blood-pressure measurement" in mission.next_action
    assert any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("guardian_domain") == "blood_pressure_followup"
        for event in state.audit_events
    )


def test_safe_new_manual_bp_closes_measurement_capture_without_claiming_control() -> None:
    state = _authorized_state()
    old = _old_bp()
    state.vitals.append(old)
    reconcile_bp_followup_guardian(state, now=NOW)
    mission = _mission(state)

    new = VitalRecord(
        measured_at=NOW + timedelta(minutes=5),
        systolic=132,
        diastolic=82,
        pulse=72,
    )
    state.vitals.append(new)
    report = reconcile_bp_followup_guardian(state, now=NOW + timedelta(minutes=5))

    assert report["completed"]
    assert mission.status == MissionStatus.COMPLETED
    assert new.id in mission.evidence_ids
    assert "new_bp_measurement_present" in mission.closure_evidence
    receipt_id = next(item for item in mission.closure_evidence if item.startswith("audit_"))
    receipt = next(item for item in state.audit_events if item.id == receipt_id)
    assert receipt.details["resolution"] == "new_bp_measurement_present"
    assert receipt.details["clinical_control_claimed"] is False
    assert receipt.details["treatment_changed"] is False


def test_priority_bp_never_closes_mission_and_hands_off_to_human() -> None:
    state = _authorized_state()
    state.vitals.append(_old_bp())
    reconcile_bp_followup_guardian(state, now=NOW)
    mission = _mission(state)

    high = VitalRecord(
        measured_at=NOW + timedelta(minutes=5),
        systolic=170,
        diastolic=105,
    )
    state.vitals.append(high)
    report = reconcile_bp_followup_guardian(state, now=NOW + timedelta(minutes=5))

    assert report["safety_handoff"]
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert mission.risk_level == RiskLevel.PRIORITY
    assert high.id in mission.evidence_ids
    assert "human clinical review" in mission.next_action
    assert not any(item == "new_bp_measurement_present" for item in mission.closure_evidence)
    assert any(
        message.metadata.get("bp_followup_safety_handoff")
        and message.metadata.get("evidence_id") == high.id
        for message in state.messages
    )


def test_later_normal_reading_cannot_auto_release_prior_safety_handoff() -> None:
    state = _authorized_state()
    state.vitals.append(_old_bp())
    reconcile_bp_followup_guardian(state, now=NOW)
    mission = _mission(state)
    high = VitalRecord(measured_at=NOW + timedelta(minutes=5), systolic=170, diastolic=105)
    state.vitals.append(high)
    reconcile_bp_followup_guardian(state, now=NOW + timedelta(minutes=5))
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL

    normal = VitalRecord(measured_at=NOW + timedelta(minutes=10), systolic=128, diastolic=80)
    state.vitals.append(normal)
    report = reconcile_bp_followup_guardian(state, now=NOW + timedelta(minutes=10))

    assert report["safety_handoff"]
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert normal.id in mission.evidence_ids
    assert report["safety_handoff"][0]["human_release_required"] is True
    assert not any(item == "new_bp_measurement_present" for item in mission.closure_evidence)


def test_daily_care_scheduler_recognizes_explicit_bp_followup_and_global_kill_switch() -> None:
    state = _authorized_state()
    state.vitals.append(_old_bp())

    assert bp_followup_due(state, now=NOW) is True
    assert care_continuity_due(state, runtime_enabled=True) is True
    assert care_continuity_due(state, runtime_enabled=False) is False


def test_bp_guardian_email_copy_preserves_clinical_truth_boundary() -> None:
    state = _authorized_state()
    state.profile.email = "ana@example.com"
    state.consent.signal_types.extend(["guardian_email", "guardian_email_auto_send"])
    due = GuardianAssessment(
        observation_id="bp_old",
        metric="blood_pressure_followup",
        classification="bp_followup_due",
        summary="BP due",
        notify_patient=True,
    )
    resolved = due.model_copy(
        update={"classification": "bp_followup_measurement_resolved", "summary": "BP captured"}
    )
    safety = due.model_copy(
        update={"classification": "bp_followup_safety_handoff", "summary": "Safety handoff"}
    )

    due_plan = plan_guardian_notification(state, due, mission_id="mission_bp")
    resolved_plan = plan_guardian_notification(state, resolved, mission_id="mission_bp")
    safety_plan = plan_guardian_notification(state, safety, mission_id="mission_bp")

    assert due_plan.email is not None and resolved_plan.email is not None and safety_plan.email is not None
    assert due_plan.email.delivery_mode == "eligible_auto_send"
    assert "not a diagnosis" in due_plan.email.body
    assert "does not mean HealthIA declared your blood pressure controlled" in resolved_plan.email.body
    assert "remains open" in safety_plan.email.body
    assert safety_plan.email.changes_treatment is False
    assert safety_plan.email.diagnostic_claim is False


@pytest.mark.asyncio
async def test_service_manual_vital_path_opens_then_closes_bp_followup_mission() -> None:
    state = _authorized_state()
    service = HealthIAService(
        Settings(store_backend="memory", llm_backend="mock", proactive_enabled=True)
    )
    service.store = MemoryStore(state, autonomous_enabled=True)

    old = VitalRecord(
        measured_at=datetime.now(timezone.utc) - timedelta(days=5),
        systolic=140,
        diastolic=88,
    )
    await service.add_vital(old)
    after_old = await service.snapshot()
    mission = _mission(after_old)
    assert mission.status == MissionStatus.WAITING_PATIENT

    new = VitalRecord(systolic=134, diastolic=84)
    await service.add_vital(new)
    final = await service.snapshot()
    mission = _mission(final)
    assert mission.status == MissionStatus.COMPLETED
    assert new.id in mission.evidence_ids
    assert any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("bp_followup_event") == "resolved"
        and event.details.get("status") == "emitted"
        for event in final.audit_events
    )


@pytest.mark.asyncio
async def test_health_connect_bp_can_satisfy_open_followup_mission() -> None:
    state = _authorized_state()
    service = HealthIAService(
        Settings(store_backend="memory", llm_backend="mock", proactive_enabled=True)
    )
    service.store = MemoryStore(state, autonomous_enabled=True)
    old = VitalRecord(
        measured_at=datetime.now(timezone.utc) - timedelta(days=5),
        systolic=142,
        diastolic=90,
    )
    await service.add_vital(old)
    opened = await service.snapshot()
    mission = _mission(opened)
    assert mission.status == MissionStatus.WAITING_PATIENT

    observed_at = datetime.now(timezone.utc)
    record = DeviceObservation(
        external_id="bp-followup-1",
        metric=DeviceMetric.BLOOD_PRESSURE,
        observed_at=observed_at,
        value=130,
        secondary_value=82,
        unit="mmHg",
        source_name="Synthetic Health Connect cuff",
    )
    batch = HealthConnectSyncBatch(
        device_id="bp-device",
        source_package="com.healthia.test",
        background_read=True,
        granted_metrics=[DeviceMetric.BLOOD_PRESSURE],
        records=[record],
    )
    await service.ingest_health_connect(batch)

    final = await service.snapshot()
    mission = _mission(final)
    assert mission.status == MissionStatus.COMPLETED
    captured = next(
        vital
        for vital in final.vitals
        if vital.systolic == 130 and vital.diastolic == 82 and vital.measured_at == observed_at
    )
    assert captured.id in mission.evidence_ids


@pytest.mark.asyncio
async def test_runtime_off_blocks_bp_guardian_even_with_specific_patient_opt_in() -> None:
    state = _authorized_state()
    service = HealthIAService(
        Settings(store_backend="memory", llm_backend="mock", proactive_enabled=False)
    )
    service.store = MemoryStore(state, autonomous_enabled=False)
    old = VitalRecord(
        measured_at=datetime.now(timezone.utc) - timedelta(days=5),
        systolic=140,
        diastolic=88,
    )

    await service.add_vital(old)
    saved = await service.snapshot()

    assert CONSENT_SIGNAL in saved.consent.signal_types
    assert not [item for item in saved.missions if item.mission_type == MISSION_TYPE]
    assert not any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("guardian_domain") == "blood_pressure_followup"
        for event in saved.audit_events
    )
