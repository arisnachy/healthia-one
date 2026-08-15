from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from healthia_one.config import Settings
from healthia_one.models import Appointment, ClinicalDocument, HealthResult, ResultItem
from healthia_one.service import HealthIAService


@pytest.mark.asyncio
async def test_runtime_proactive_off_blocks_state_guardians_even_when_patient_consent_is_on() -> None:
    service = HealthIAService(
        Settings(
            store_backend="memory",
            llm_backend="mock",
            proactive_enabled=False,
        )
    )
    initial = await service.snapshot()
    initial_message_count = len(initial.messages)

    appointment = Appointment(
        title="Near-term appointment",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=24),
        required_documents=["Recent results"],
    )
    await service.add_appointment(appointment)

    result = HealthResult(
        filename="partial-lab.json",
        panel="Laboratory",
        status="parsed",
        explained=True,
        items=[ResultItem(name="Sodium", value=139, unit="mmol/L")],
    )
    document = ClinicalDocument(
        title="Partial lab",
        filename="partial-lab.json",
        mime_type="application/json",
        status="parsed",
        related_result_id=result.id,
    )
    await service.add_result_evidence(result, document)

    saved = await service.snapshot()
    assert saved.consent.proactive_enabled is True
    assert service.settings.proactive_enabled is False
    assert len(saved.messages) == initial_message_count
    assert not [mission for mission in saved.missions if mission.mission_type.startswith("appointment_guardian")]
    assert not [mission for mission in saved.missions if mission.mission_type.startswith("result_guardian")]
    assert not [
        event
        for event in saved.audit_events
        if event.action == "autopilot_event_intent"
        and event.details.get("event", {}).get("payload", {}).get("source") == "guardian_context"
    ]
