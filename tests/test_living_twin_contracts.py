from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from healthia_one.models import (
    AnatomyState,
    ClinicalEventEdge,
    HealthObligation,
    LivingTwinEvent,
    MedicationExpectation,
    OrganSystemState,
    PatientBaseline,
    PatientState,
    TwinDeviation,
    TwinTrajectory,
)
from healthia_one.store import JsonStore
from healthia_one.twin import LIVING_TWIN_EVENT_SEQUENCE, advance_twin_version, clinical_twin_summary


NOW = datetime(2026, 8, 17, tzinfo=timezone.utc)


def test_legacy_patient_state_loads_with_versioned_twin_defaults() -> None:
    state = PatientState.model_validate({"profile": {"id": "patient_legacy"}})

    assert state.twin_schema_version == "1.0"
    assert state.twin_version == 1
    assert state.organ_system_states == []
    assert state.clinical_event_edges == []
    assert PatientState.model_validate_json(state.model_dump_json()).profile.id == "patient_legacy"


def test_living_twin_projection_exposes_canonical_manifest_contracts() -> None:
    state = PatientState.model_validate({"profile": {"id": "patient_demo"}})
    state.twin_version = 2
    state.twin_parent_version = 1
    state.twin_source_event_ids = ["event_device_bundle_1"]
    state.organ_system_states.append(
        OrganSystemState(
            system="cardiovascular",
            status="watch",
            trajectory="uncertain",
            confidence=0.72,
            evidence_ids=["device_bp_1"],
        )
    )
    state.anatomy_states.append(
        AnatomyState(
            body_structure="gallbladder",
            status="removed",
            modification="laparoscopic cholecystectomy",
            effective_at=NOW,
            evidence_ids=["procedure_1"],
        )
    )
    state.medication_expectations.append(
        MedicationExpectation(
            medication_id="med_atorvastatin",
            expected_outcome="LDL reduction under professional monitoring",
            monitoring_metric="LDL",
            evidence_ids=["med_atorvastatin"],
        )
    )
    state.baselines.append(
        PatientBaseline(
            metric="systolic_bp",
            value=126,
            unit="mmHg",
            window_start=NOW,
            window_end=NOW,
            sample_count=8,
            confidence=0.9,
            source_event_ids=["device_bp_history"],
        )
    )
    state.deviations.append(
        TwinDeviation(
            metric="systolic_bp",
            observed_value=142,
            baseline_value=126,
            unit="mmHg",
            direction="higher",
            confidence=0.7,
            evidence_ids=["device_bp_1"],
        )
    )
    state.trajectories.append(
        TwinTrajectory(
            metric="systolic_bp",
            direction="worsening",
            slope=2.1,
            unit="mmHg/day",
            window_start=NOW,
            window_end=NOW,
            confidence=0.62,
            evidence_ids=["device_bp_history", "device_bp_1"],
        )
    )
    state.obligations.append(
        HealthObligation(
            reason="confirm a potentially meaningful personal-baseline deviation",
            required_action="obtain a canonical repeat blood-pressure measurement",
            evidence_ids=["device_bp_1"],
            closure_condition="verified repeat measurement persisted",
        )
    )
    state.clinical_event_edges.append(
        ClinicalEventEdge(
            source_event_id="event_device_bundle_1",
            target_entity_id=state.obligations[0].id,
            relation="creates_obligation",
            evidence_ids=["device_bp_1"],
        )
    )

    twin = clinical_twin_summary(state)

    assert twin["version"] == 2
    assert twin["parent_version"] == 1
    assert twin["anatomy_state"][0]["status"] == "removed"
    assert twin["medication_expectations"][0]["professional_review_required"] is True
    assert twin["baselines"][0]["metric"] == "systolic_bp"
    assert twin["trajectory"][0]["direction"] == "worsening"
    assert twin["deviations"][0]["confidence"] == 0.7
    assert twin["clinical_event_edges"][0]["causal_claim"] is False
    assert twin["obligations"][0]["status"] == "open"
    assert twin["patient_namespace"] == "patient_demo"
    assert twin["identity_context"] == {
        "patient_id": "patient_demo",
        "locale": "es-DO",
        "timezone": "America/Santo_Domingo",
    }
    assert "device_bp_1" in twin["evidence_refs"]
    assert "email" not in twin["identity_context"]


def test_clinical_event_graph_cannot_encode_a_causal_claim() -> None:
    with pytest.raises(ValidationError):
        ClinicalEventEdge(
            source_event_id="event_1",
            target_entity_id="condition_1",
            relation="updates",
            causal_claim=True,
        )


def test_living_twin_event_is_bounded_to_public_sanitized_catalog() -> None:
    event = LivingTwinEvent(
        event_type="policy_checked",
        patient_namespace="synthetic_session_1",
        correlation_id="correlation_1",
        actor="ONE_SAFETY",
        policy_decision="human_required",
        status="blocked",
        evidence_ids=["consent_scope_1"],
    )
    assert event.schema_version == "1.0"

    with pytest.raises(ValidationError):
        LivingTwinEvent(
            event_type="model_chain_of_thought",
            patient_namespace="synthetic_session_1",
            correlation_id="correlation_1",
            actor="ONE_TWIN",
            status="completed",
        )

    with pytest.raises(ValidationError):
        LivingTwinEvent(
            event_type="policy_checked",
            patient_namespace="synthetic_session_1",
            correlation_id="correlation_1",
            actor="ONE_SAFETY",
            status="completed",
            chain_of_thought="must never be accepted",
        )


def test_baseline_rejects_reversed_time_window() -> None:
    with pytest.raises(ValidationError):
        PatientBaseline(
            metric="steps",
            value=5000,
            window_start=datetime(2026, 8, 18, tzinfo=timezone.utc),
            window_end=NOW,
            sample_count=3,
        )


def test_twin_version_advances_once_and_rejects_cross_patient_event() -> None:
    state = PatientState.model_validate({"profile": {"id": "synthetic_patient_1"}})
    event = LivingTwinEvent(
        id="twin_event_1",
        event_type="observation_normalized",
        patient_namespace="synthetic_patient_1",
        correlation_id="correlation_1",
        actor="ONE_SENSE",
        policy_decision="allowed",
        status="completed",
        source_event_ids=["health_connect_bundle_1"],
    )

    first = advance_twin_version(state, event, changed_fields=["observations", "baseline"])
    duplicate = advance_twin_version(state, event, changed_fields=["observations"])

    assert first == {
        "advanced": True,
        "previous_version": 1,
        "version": 2,
        "source_event_id": "twin_event_1",
        "changed_fields": ["observations", "baseline"],
    }
    assert duplicate["advanced"] is False
    assert state.twin_version == 2
    assert len(state.living_twin_events) == 1

    cross_patient = event.model_copy(update={"id": "twin_event_2", "patient_namespace": "other_patient"})
    with pytest.raises(PermissionError):
        advance_twin_version(state, cross_patient, changed_fields=["observations"])


def test_public_living_event_catalog_has_exact_manifest_order() -> None:
    assert LIVING_TWIN_EVENT_SEQUENCE == (
        "event_received",
        "policy_checked",
        "observation_normalized",
        "twin_versioned",
        "baseline_compared",
        "signals_correlated",
        "deviation_detected",
        "guardian_investigation_opened",
        "mission_opened",
        "human_boundary",
        "bounded_action_executed",
        "receipt_recorded",
        "mission_verified",
        "twin_updated_from_verified_outcome",
    )


@pytest.mark.asyncio
async def test_json_store_round_trip_preserves_twin_version_and_events(tmp_path) -> None:
    store = JsonStore(tmp_path / "state.json", autonomous_enabled=False)
    state = PatientState()
    event = LivingTwinEvent(
        id="twin_event_roundtrip",
        event_type="observation_normalized",
        patient_namespace="patient_demo",
        correlation_id="correlation_roundtrip",
        actor="ONE_SENSE",
        policy_decision="allowed",
        status="completed",
    )
    advance_twin_version(state, event, changed_fields=["observations"])

    await store.save(state)
    restored = await store.load()

    assert restored.twin_version == 2
    assert restored.twin_parent_version == 1
    assert restored.twin_source_event_ids == ["twin_event_roundtrip"]
    assert restored.living_twin_events[0].id == "twin_event_roundtrip"
