from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from healthia_one.autopilot_worker import care_continuity_due, reconcile_care_patient
from healthia_one.config import Settings
from healthia_one.models import PatientState


async def run_care_continuity_once(
    settings_value: Settings | None = None,
    *,
    states_loader: Callable[[str | None], Sequence[PatientState]] | None = None,
    reconciler: Callable[[Settings, str], Awaitable[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Run one bounded, zero-model daily BP continuity sweep.

    This is the production entrypoint used by the private Cloud Run Job. It is
    deliberately narrower than the experimental Guardian lineage: only patients
    who explicitly opted into BP follow-up can become due, and the global
    proactive kill switch must be ON. The returned summary contains counts only,
    never patient identifiers.
    """
    settings_value = settings_value or Settings()
    if not settings_value.proactive_enabled:
        return {
            "mode": "care_continuity",
            "status": "runtime_disabled",
            "patient_states_scanned": 0,
            "patients_due": 0,
            "patients_reconciled": 0,
            "model_calls": 0,
            "clinical_reasoning_network_calls": 0,
        }
    if settings_value.store_backend != "firestore":
        raise RuntimeError("Production care-continuity job requires Firestore persistence")

    if states_loader is None:
        from healthia_one.autopilot_scheduler import load_firestore_patient_states

        states_loader = load_firestore_patient_states
    if reconciler is None:
        reconciler = reconcile_care_patient

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
    states = await asyncio.to_thread(states_loader, project)
    due_ids = [
        state.profile.id
        for state in states
        if care_continuity_due(state, runtime_enabled=True)
    ]
    reconciled = 0
    for patient_id in due_ids:
        report = await reconciler(settings_value, patient_id)
        if report.get("status") == "reconciled":
            reconciled += 1

    return {
        "mode": "care_continuity",
        "status": "ok",
        "patient_states_scanned": len(states),
        "patients_due": len(due_ids),
        "patients_reconciled": reconciled,
        "model_calls": 0,
        "clinical_reasoning_network_calls": 0,
        "scope": "explicitly_opted_in_blood_pressure_followup_only",
    }


async def _main() -> None:
    # Count-only JSON is intentional: Cloud Run logs must not expose patient ids.
    print(json.dumps(await run_care_continuity_once(), sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
