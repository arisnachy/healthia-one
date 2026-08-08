from __future__ import annotations

from datetime import date, datetime, timezone

from healthia_one.continuity import build_timeline
from healthia_one.models import HealthResult, PatientState
from healthia_one.twin_runtime import record_result_in_state


def test_timeline_orders_result_by_exam_date_not_upload_date() -> None:
    state = PatientState()
    result = HealthResult(
        filename="ct.png",
        uploaded_at=datetime(2026, 8, 7, 15, 0, tzinfo=timezone.utc),
        panel="Tomografía de tórax",
        artifact_type="ct_image",
        exam_date=date(2026, 8, 1),
        anatomical_region="Right lung",
        verification_status="ai_observed_unverified",
        ai_observations=["Hallazgo visual no verificado"],
        source={"source_type": "AI_extraction", "source_id": "test", "verified": False},
    )
    state.results.append(result)
    event = record_result_in_state(state, result)
    timeline = build_timeline(state)
    row = next(item for item in timeline if item["id"] == event.id)
    assert row["occurred_at"].startswith("2026-08-01")
    assert row["recorded_at"].startswith("2026-08-07")
    assert row["certainty"] == "ai_extraction"
    assert row["verification_status"] == "unverified"
    assert sum(1 for item in timeline if item["type"] == "result") == 1


def test_open_loop_and_anatomical_link_do_not_emit_chat_messages() -> None:
    state = PatientState()
    result = HealthResult(
        filename="xray.png",
        panel="Radiografía de tórax",
        status="parsed",
        artifact_type="xray_image",
        anatomical_region="Right lower lung",
        ai_observations=["Opacidad no verificada"],
        verification_status="ai_observed_unverified",
        source={"source_type": "AI_extraction", "source_id": "test", "verified": False},
    )
    record_result_in_state(state, result)
    assert state.anatomical_links
    assert state.open_clinical_loops
    assert state.messages == []
