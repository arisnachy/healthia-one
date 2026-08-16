from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from healthia_one.care_continuity_job import run_care_continuity_once
from healthia_one.config import Settings
from healthia_one.models import PatientState, VitalRecord


def _state(patient_id: str, *, due: bool) -> PatientState:
    state = PatientState()
    state.profile.id = patient_id
    state.profile.care_plan.blood_pressure_due_days = 3
    state.consent.proactive_enabled = True
    state.consent.signal_types.append("bp_followup")
    state.vitals.append(
        VitalRecord(
            measured_at=datetime.now(timezone.utc) - timedelta(days=5 if due else 1),
            systolic=128,
            diastolic=80,
        )
    )
    return state


@pytest.mark.asyncio
async def test_runtime_off_never_scans_or_reconciles() -> None:
    called = False

    def loader(_project):
        nonlocal called
        called = True
        return [_state("patient_due", due=True)]

    result = await run_care_continuity_once(
        Settings(store_backend="firestore", proactive_enabled=False),
        states_loader=loader,
    )
    assert result["status"] == "runtime_disabled"
    assert result["model_calls"] == 0
    assert result["clinical_reasoning_network_calls"] == 0
    assert called is False


@pytest.mark.asyncio
async def test_only_due_opted_in_bp_patient_is_reconciled_and_summary_is_count_only() -> None:
    due = _state("patient_due", due=True)
    not_due = _state("patient_recent", due=False)
    no_consent = _state("patient_no_consent", due=True)
    no_consent.consent.signal_types.clear()
    reconciled: list[str] = []

    def loader(_project):
        return [due, not_due, no_consent]

    async def reconcile(_settings, patient_id: str):
        reconciled.append(patient_id)
        return {"patient_id": patient_id, "status": "reconciled"}

    result = await run_care_continuity_once(
        Settings(store_backend="firestore", proactive_enabled=True),
        states_loader=loader,
        reconciler=reconcile,
    )
    assert reconciled == ["patient_due"]
    assert result == {
        "mode": "care_continuity",
        "status": "ok",
        "patient_states_scanned": 3,
        "patients_due": 1,
        "patients_reconciled": 1,
        "model_calls": 0,
        "clinical_reasoning_network_calls": 0,
        "scope": "explicitly_opted_in_blood_pressure_followup_only",
    }
    assert "patient_due" not in str(result)


@pytest.mark.asyncio
async def test_production_job_refuses_non_firestore_store() -> None:
    with pytest.raises(RuntimeError, match="requires Firestore"):
        await run_care_continuity_once(
            Settings(store_backend="memory", proactive_enabled=True),
            states_loader=lambda _project: [],
        )
