from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from healthia_one.autopilot_worker import care_continuity_due
from healthia_one.config import Settings
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import plan_guardian_notification
from healthia_one.medication_followup_guardian import (
    CONSENT_SIGNAL,
    FOLLOWUP_DUE_HOURS,
    MISSION_TYPE,
    medication_followup_due,
    reconcile_medication_followup_guardian,
)
from healthia_one.models import (
    MedicationCheckIn,
    MedicationPlan,
    MissionStatus,
    PatientState,
    RiskLevel,
)
from healthia_one.service import HealthIAService
from healthia_one.store import MemoryStore


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _authorized_state(*, active: bool = True, with_stream: bool = True) -> tuple[PatientState, MedicationPlan]:
    state = PatientState()
    if CONSENT_SIGNAL not in state.consent.signal_types:
        state.consent.signal_types.append(CONSENT_SIGNAL)
    plan = MedicationPlan(
        name="Losartán",
        strength="50 mg",
        schedule="cada 24 horas",
        frequency_times_per_day=1,
        active=active,
        verification_status="professional_confirmed",
    )
    state.medication_plans.append(plan)
    if with_stream:
        state.medication_checkins.append(
            MedicationCheckIn(
                medication_id=plan.id,
                recorded_at=NOW - timedelta(hours=FOLLOWUP_DUE_HOURS + 12),
                status="taken",
            )
        )
    return state, plan


def _mission(state: PatientState, medication_id: str):
    return next(
        item
        for item in state.missions
        if item.mission_type == f"{MISSION_TYPE}:{medication_id}"
    )


def _open(state: PatientState, plan: MedicationPlan) -> None:
    report = reconcile_medication_followup_guardian(state, now=NOW)
    assert report["created"]
    assert _mission(state, plan.id).status == MissionStatus.WAITING_PATIENT


def test_medication_followup_requires_separate_explicit_consent_signal() -> None:
    state = PatientState()
    plan = MedicationPlan(name="Losartán", active=True)
    state.medication_plans.append(plan)
    state.medication_checkins.append(
        MedicationCheckIn(
            medication_id=plan.id,
            recorded_at=NOW - timedelta(hours=60),
            status="taken",
        )
    )

    assert "medications" in state.consent.signal_types
    assert CONSENT_SIGNAL not in state.consent.signal_types
    assert medication_followup_due(state, now=NOW) is False
    report = reconcile_medication_followup_guardian(state, now=NOW)
    assert not report["created"]
    assert not state.missions


def test_no_existing_checkin_stream_means_no_autonomous_surveillance() -> None:
    state, plan = _authorized_state(with_stream=False)

    assert medication_followup_due(state, now=NOW) is False
    report = reconcile_medication_followup_guardian(state, now=NOW)

    assert not report["created"]
    assert not [m for m in state.missions if m.mission_type.endswith(plan.id)]


def test_inactive_medication_is_ignored_even_with_old_checkin() -> None:
    state, _ = _authorized_state(active=False)

    assert medication_followup_due(state, now=NOW) is False
    report = reconcile_medication_followup_guardian(state, now=NOW)
    assert not report["created"]


def test_overdue_established_stream_opens_durable_checkin_mission_without_claiming_missed_dose() -> None:
    state, plan = _authorized_state()
    previous = state.medication_checkins[-1]

    report = reconcile_medication_followup_guardian(state, now=NOW)

    mission = _mission(state, plan.id)
    assert report["created"]
    assert mission.status == MissionStatus.WAITING_PATIENT
    assert mission.evidence_ids == [previous.id]
    assert "Do not change or compensate" in mission.next_action
    message = next(item for item in state.messages if item.mission_id == mission.id)
    assert "does not mean HealthIA believes you missed a dose" in message.content
    assert message.metadata["tracking_interval_not_prescription_schedule"] is True
    assert any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("guardian_domain") == "medication_followup"
        and event.details.get("event", {}).get("payload", {}).get("adherence_claimed") is False
        for event in state.audit_events
    )


@pytest.mark.parametrize("status", ["taken", "late", "skipped"])
def test_explicit_checkin_status_closes_capture_only_without_treatment_change(status: str) -> None:
    state, plan = _authorized_state()
    _open(state, plan)
    mission = _mission(state, plan.id)
    checkin = MedicationCheckIn(
        medication_id=plan.id,
        recorded_at=NOW + timedelta(minutes=5),
        status=status,
    )
    state.medication_checkins.append(checkin)

    report = reconcile_medication_followup_guardian(state, now=NOW + timedelta(minutes=5))

    assert report["completed"]
    assert mission.status == MissionStatus.COMPLETED
    assert checkin.id in mission.evidence_ids
    assert "medication_checkin_recorded" in mission.closure_evidence
    receipt = next(
        event
        for event in state.audit_events
        if event.action == "resolve_medication_followup_checkin_mission"
        and event.resource_id == mission.id
    )
    assert receipt.details["reported_status"] == status
    assert receipt.details["dose_instruction_given"] is False
    assert receipt.details["compensation_advice_given"] is False
    assert receipt.details["adherence_claimed"] is False
    assert receipt.details["treatment_changed"] is False
    if status == "skipped":
        message = next(
            item for item in reversed(state.messages)
            if item.metadata.get("medication_followup_resolved")
        )
        assert "not telling you to compensate, double, or change a later dose" in message.content


def test_unknown_checkin_is_evidence_but_keeps_mission_waiting() -> None:
    state, plan = _authorized_state()
    _open(state, plan)
    mission = _mission(state, plan.id)
    checkin = MedicationCheckIn(
        medication_id=plan.id,
        recorded_at=NOW + timedelta(minutes=5),
        status="unknown",
    )
    state.medication_checkins.append(checkin)

    report = reconcile_medication_followup_guardian(state, now=NOW + timedelta(minutes=5))

    assert report["waiting"]
    assert mission.status == MissionStatus.WAITING_PATIENT
    assert checkin.id in mission.evidence_ids
    assert "medication_checkin_recorded" not in mission.closure_evidence


def test_checkin_for_other_medication_cannot_resolve_open_mission() -> None:
    state, plan = _authorized_state()
    other = MedicationPlan(name="Amlodipino", active=True)
    state.medication_plans.append(other)
    _open(state, plan)
    mission = _mission(state, plan.id)
    state.medication_checkins.append(
        MedicationCheckIn(
            medication_id=other.id,
            recorded_at=NOW + timedelta(minutes=5),
            status="taken",
        )
    )

    report = reconcile_medication_followup_guardian(state, now=NOW + timedelta(minutes=5))

    assert mission.status == MissionStatus.WAITING_PATIENT
    assert any(item["mission_id"] == mission.id for item in report["waiting"])


def test_explicit_dose_change_or_medication_error_context_hands_off_without_prescribing() -> None:
    state, plan = _authorized_state()
    _open(state, plan)
    mission = _mission(state, plan.id)
    checkin = MedicationCheckIn(
        medication_id=plan.id,
        recorded_at=NOW + timedelta(minutes=5),
        status="late",
        note="Llegué tarde. ¿Puedo duplicar la dosis ahora?",
    )
    state.medication_checkins.append(checkin)

    report = reconcile_medication_followup_guardian(state, now=NOW + timedelta(minutes=5))

    assert report["review_handoff"]
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert mission.risk_level == RiskLevel.WATCH
    handoff = report["review_handoff"][0]
    assert handoff["reason"] == "dose_change_or_medication_error_context"
    receipt = next(
        event
        for event in state.audit_events
        if event.action == "handoff_medication_followup_to_human"
        and event.resource_id == mission.id
    )
    assert receipt.details["dose_instruction_given"] is False
    assert receipt.details["treatment_changed"] is False


def test_nonurgent_adverse_effect_context_hands_off_for_human_review() -> None:
    state, plan = _authorized_state()
    _open(state, plan)
    mission = _mission(state, plan.id)
    checkin = MedicationCheckIn(
        medication_id=plan.id,
        recorded_at=NOW + timedelta(minutes=5),
        status="taken",
        note="Después de tomarla tuve mareo y creo que puede ser un efecto secundario.",
    )
    state.medication_checkins.append(checkin)

    report = reconcile_medication_followup_guardian(state, now=NOW + timedelta(minutes=5))

    assert report["review_handoff"]
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert mission.risk_level == RiskLevel.WATCH
    assert report["review_handoff"][0]["reason"] == "adverse_effect_context"


def test_urgent_language_has_precedence_and_creates_sticky_safety_handoff() -> None:
    state, plan = _authorized_state()
    _open(state, plan)
    mission = _mission(state, plan.id)
    urgent = MedicationCheckIn(
        medication_id=plan.id,
        recorded_at=NOW + timedelta(minutes=5),
        status="taken",
        note="Después de tomarla tengo dolor fuerte en el pecho.",
    )
    state.medication_checkins.append(urgent)

    report = reconcile_medication_followup_guardian(state, now=NOW + timedelta(minutes=5))

    assert report["review_handoff"]
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert mission.risk_level == RiskLevel.URGENT
    assert report["review_handoff"][0]["reason"] == "urgent_language"

    later = MedicationCheckIn(
        medication_id=plan.id,
        recorded_at=NOW + timedelta(minutes=10),
        status="taken",
        note="Ahora me siento mejor.",
    )
    state.medication_checkins.append(later)
    second = reconcile_medication_followup_guardian(state, now=NOW + timedelta(minutes=10))

    assert second["review_handoff"]
    assert mission.status == MissionStatus.WAITING_PROFESSIONAL
    assert later.id in mission.evidence_ids
    assert second["review_handoff"][0]["human_release_required"] is True
    assert "medication_checkin_recorded" not in mission.closure_evidence


def test_daily_care_scheduler_recognizes_medication_followup_and_global_kill_switch() -> None:
    state, _ = _authorized_state()

    assert medication_followup_due(state, now=NOW) is True
    assert care_continuity_due(state, runtime_enabled=True) is True
    assert care_continuity_due(state, runtime_enabled=False) is False


def test_medication_guardian_email_copy_never_becomes_dose_advice() -> None:
    state, _ = _authorized_state()
    state.profile.email = "ana@example.com"
    state.consent.signal_types.extend(["guardian_email", "guardian_email_auto_send"])
    due = GuardianAssessment(
        observation_id="dose_old",
        metric="medication_followup",
        classification="medication_followup_due",
        summary="Medication check-in due",
        notify_patient=True,
    )
    resolved = due.model_copy(
        update={
            "classification": "medication_followup_checkin_resolved",
            "summary": "Medication check-in captured",
        }
    )
    review = due.model_copy(
        update={
            "classification": "medication_followup_review_handoff",
            "summary": "Medication review handoff",
        }
    )

    due_plan = plan_guardian_notification(state, due, mission_id="mission_med")
    resolved_plan = plan_guardian_notification(state, resolved, mission_id="mission_med")
    review_plan = plan_guardian_notification(state, review, mission_id="mission_med")

    assert due_plan.email is not None and resolved_plan.email is not None and review_plan.email is not None
    assert due_plan.email.delivery_mode == "eligible_auto_send"
    assert "does not mean HealthIA believes you missed a dose" in due_plan.email.body
    assert "not an instruction to take, repeat, double, skip, stop, or change medication" in due_plan.email.body
    assert "does not establish adherence" in resolved_plan.email.body
    assert "did not recommend an extra" in review_plan.email.body
    assert review_plan.email.changes_treatment is False
    assert review_plan.email.diagnostic_claim is False


@pytest.mark.asyncio
async def test_service_checkin_path_opens_then_closes_same_medication_mission() -> None:
    state, plan = _authorized_state(with_stream=False)
    service = HealthIAService(
        Settings(store_backend="memory", llm_backend="mock", proactive_enabled=True)
    )
    service.store = MemoryStore(state, autonomous_enabled=True)
    old = MedicationCheckIn(
        medication_id=plan.id,
        recorded_at=datetime.now(timezone.utc) - timedelta(hours=FOLLOWUP_DUE_HOURS + 12),
        status="taken",
    )

    await service.add_medication_checkin(old)
    opened = await service.snapshot()
    mission = _mission(opened, plan.id)
    assert mission.status == MissionStatus.WAITING_PATIENT

    new = MedicationCheckIn(medication_id=plan.id, status="skipped", note="No la tomé.")
    await service.add_medication_checkin(new)
    final = await service.snapshot()
    mission = _mission(final, plan.id)

    assert mission.status == MissionStatus.COMPLETED
    assert new.id in mission.evidence_ids
    assert any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("medication_followup_event") == "resolved"
        and event.details.get("status") == "emitted"
        for event in final.audit_events
    )


@pytest.mark.asyncio
async def test_runtime_off_blocks_medication_guardian_even_with_specific_patient_opt_in() -> None:
    state, plan = _authorized_state(with_stream=False)
    service = HealthIAService(
        Settings(store_backend="memory", llm_backend="mock", proactive_enabled=False)
    )
    service.store = MemoryStore(state, autonomous_enabled=False)
    old = MedicationCheckIn(
        medication_id=plan.id,
        recorded_at=datetime.now(timezone.utc) - timedelta(hours=FOLLOWUP_DUE_HOURS + 12),
        status="taken",
    )

    await service.add_medication_checkin(old)
    saved = await service.snapshot()

    assert CONSENT_SIGNAL in saved.consent.signal_types
    assert not [item for item in saved.missions if item.mission_type.startswith(f"{MISSION_TYPE}:")]
    assert not any(
        event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("guardian_domain") == "medication_followup"
        for event in saved.audit_events
    )
