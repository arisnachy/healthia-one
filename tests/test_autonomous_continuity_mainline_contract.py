from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

import healthia_one.autopilot_worker as worker_module
import healthia_one.store as store_module
from healthia_one.autonomous_continuity import DURABLE_BOUNDARIES, JUDGE_TRIGGER, OPERATIONAL_METRIC, judge_proof
from healthia_one.autopilot_worker import _network_policy, care_continuity_due
from healthia_one.bp_followup_guardian import CONSENT_SIGNAL, MISSION_TYPE
from healthia_one.models import PatientConsent, PatientState, VitalRecord
from healthia_one.store import MemoryStore


def _due_state() -> PatientState:
    state = PatientState()
    state.profile.care_plan.blood_pressure_due_days = 3
    if CONSENT_SIGNAL not in state.consent.signal_types:
        state.consent.signal_types.append(CONSENT_SIGNAL)
    state.vitals.append(
        VitalRecord(
            measured_at=datetime.now(timezone.utc) - timedelta(days=5),
            systolic=138,
            diastolic=86,
        )
    )
    return state


class _Event:
    event_type = "patient_state_changed"
    payload = {"source": "guardian_context", "mission_id": "mission_bp"}


class _Permissions:
    scientific_enabled = True
    resource_enabled = True


def test_judge_metric_is_exactly_five_durable_boundaries() -> None:
    proof = judge_proof()
    assert JUDGE_TRIGGER == "HealthIA noticed the follow-up was overdue. Nobody prompted it."
    assert OPERATIONAL_METRIC == "One unattended health mission crossed 5 durable boundaries without another chat prompt."
    assert len(DURABLE_BOUNDARIES) == 5
    assert proof["boundary_count"] == 5
    assert proof["model_calls_for_trigger"] == 0


def test_mainline_import_surface_excludes_broad_guardian_domains() -> None:
    source = inspect.getsource(worker_module) + "\n" + inspect.getsource(store_module)
    for forbidden in (
        "appointment_guardian",
        "medication_followup_guardian",
        "postvisit_guardian",
        "result_guardian",
        "geofence",
        "semantic_location",
    ):
        assert forbidden not in source
    assert "bp_followup_guardian" in source


def test_guardian_delivery_forces_zero_scientific_and_paid_network_policy() -> None:
    assert _network_policy(_Event(), _Permissions()) == (False, False)


def test_global_runtime_gate_controls_daily_due_detection() -> None:
    state = _due_state()
    assert care_continuity_due(state, runtime_enabled=True) is True
    assert care_continuity_due(state, runtime_enabled=False) is False


@pytest.mark.asyncio
async def test_store_kill_switch_blocks_new_autonomous_bp_mission() -> None:
    state = _due_state()
    store = MemoryStore(state, autonomous_enabled=False)
    loaded = await store.load()
    await store.save(loaded)
    final = await store.load()
    assert not [mission for mission in final.missions if mission.mission_type == MISSION_TYPE]
    assert not [
        event for event in final.audit_events
        if event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("guardian_domain") == "blood_pressure_followup"
    ]


def test_guardian_reply_consent_is_nested_under_email_and_auto_send() -> None:
    replies_only = PatientConsent(signal_types=["guardian_email_replies"])
    assert "guardian_email_replies" not in replies_only.signal_types
    email_and_reply = PatientConsent(signal_types=["guardian_email", "guardian_email_replies"])
    assert email_and_reply.signal_types == ["guardian_email"]
    full = PatientConsent(signal_types=["guardian_email", "guardian_email_auto_send", "guardian_email_replies"])
    assert "guardian_email_replies" in full.signal_types
