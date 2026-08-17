from __future__ import annotations

from typing import Any

from healthia_one.models import LivingTwinEvent, PatientState


LIVING_TWIN_EVENT_SEQUENCE = (
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


def advance_twin_version(
    state: PatientState,
    event: LivingTwinEvent,
    *,
    changed_fields: list[str],
) -> dict[str, Any]:
    """Advance canonical Twin version exactly once for an accepted state-changing event."""

    if event.patient_namespace != state.profile.id:
        raise PermissionError("Living Twin event namespace does not match PatientState")
    if event.event_type not in {"observation_normalized", "twin_updated_from_verified_outcome"}:
        raise ValueError("event type does not represent a canonical Twin state change")
    if event.status not in {"accepted", "completed"} or event.policy_decision == "blocked":
        raise ValueError("blocked, failed, or pending events cannot advance the Twin")
    if event.id in state.twin_source_event_ids:
        return {
            "advanced": False,
            "previous_version": state.twin_parent_version,
            "version": state.twin_version,
            "source_event_id": event.id,
            "changed_fields": [],
        }

    previous_version = state.twin_version
    state.twin_parent_version = previous_version
    state.twin_version = previous_version + 1
    state.twin_source_event_ids.append(event.id)
    state.living_twin_events.append(event)
    return {
        "advanced": True,
        "previous_version": previous_version,
        "version": state.twin_version,
        "source_event_id": event.id,
        "changed_fields": list(dict.fromkeys(changed_fields)),
    }


def clinical_twin_summary(state: PatientState) -> dict[str, Any]:
    """Build a searchable longitudinal twin from persisted patient evidence.

    The twin is deliberately derived from the canonical record instead of becoming
    a second source of truth. Every node points back to a persisted result or
    device observation so the UI/chat can discuss it without duplicating evidence.
    """

    document_by_result = {
        item.related_result_id: item
        for item in state.documents
        if item.related_result_id
    }
    result_nodes: list[dict[str, Any]] = []
    region_index: dict[str, list[str]] = {}
    for result in state.results:
        regions = [
            str(item.value).strip()
            for item in result.items
            if item.name.strip().lower() == "región anatómica" and str(item.value).strip()
        ]
        findings = [
            str(item.value).strip()
            for item in result.items
            if item.name.strip().lower() in {"hallazgo", "impresión"} and str(item.value).strip()
        ]
        document = document_by_result.get(result.id)
        node = {
            "result_id": result.id,
            "uploaded_at": result.uploaded_at.isoformat(),
            "panel": result.panel,
            "filename": result.filename,
            "status": result.status,
            "regions": regions,
            "findings": findings,
            "explanation": result.explanation,
            "document_id": document.id if document else None,
            "document_status": document.status if document else None,
        }
        result_nodes.append(node)
        for region in regions:
            key = region.casefold()
            region_index.setdefault(key, []).append(result.id)

    latest_vital = state.vitals[-1].model_dump(mode="json") if state.vitals else None
    latest_weight = state.weights[-1].model_dump(mode="json") if state.weights else None
    latest_activity = state.activity[-1].model_dump(mode="json") if state.activity else None
    latest_device: dict[str, dict[str, Any]] = {}
    for item in state.device_observations:
        latest_device[str(item.metric)] = item.model_dump(mode="json")

    evidence_refs = list(
        dict.fromkeys(
            [*state.twin_source_event_ids]
            + [evidence for item in state.organ_system_states for evidence in item.evidence_ids]
            + [evidence for item in state.anatomy_states for evidence in item.evidence_ids]
            + [evidence for item in state.medication_expectations for evidence in item.evidence_ids]
            + [evidence for item in state.baselines for evidence in item.source_event_ids]
            + [evidence for item in state.trajectories for evidence in item.evidence_ids]
            + [evidence for item in state.deviations for evidence in item.evidence_ids]
            + [evidence for item in state.clinical_event_edges for evidence in item.evidence_ids]
            + [evidence for item in state.obligations for evidence in item.evidence_ids]
        )
    )

    medication_exposures = [
        {
            "id": item.id,
            "name": item.name,
            "generic_name": item.generic_name,
            "purpose": item.purpose,
            "active": item.active,
            "verification_status": item.verification_status,
            "source_id": item.source.source_id,
        }
        for item in state.medication_plans
    ]

    observations = {
        "vital_ids": [item.id for item in state.vitals[-50:]],
        "weight_ids": [item.id for item in state.weights[-50:]],
        "activity_ids": [item.id for item in state.activity[-50:]],
        "device_observation_ids": [item.id for item in state.device_observations[-50:]],
        "result_ids": [item.id for item in state.results[-50:]],
    }

    return {
        "source_of_truth": "patient_state",
        "derived": True,
        "patient_id": state.profile.id,
        "patient_namespace": state.profile.id,
        "identity_context": {
            "patient_id": state.profile.id,
            "locale": state.profile.locale,
            "timezone": state.profile.timezone,
        },
        "schema_version": state.twin_schema_version,
        "version": state.twin_version,
        "parent_version": state.twin_parent_version,
        "source_event_ids": list(state.twin_source_event_ids),
        "conditions": list(state.profile.confirmed_conditions),
        "allergies": list(state.profile.allergies),
        "organ_system_state": [item.model_dump(mode="json") for item in state.organ_system_states],
        "anatomy_state": [item.model_dump(mode="json") for item in state.anatomy_states],
        "medication_expectations": [item.model_dump(mode="json") for item in state.medication_expectations],
        "medication_exposures": medication_exposures,
        "observations": observations,
        "baseline": [item.model_dump(mode="json") for item in state.baselines],
        "baselines": [item.model_dump(mode="json") for item in state.baselines],
        "trajectory": [item.model_dump(mode="json") for item in state.trajectories],
        "deviations": [item.model_dump(mode="json") for item in state.deviations],
        "confidence": {
            "organ_system_state": [item.confidence for item in state.organ_system_states],
            "baseline": [item.confidence for item in state.baselines],
            "trajectory": [item.confidence for item in state.trajectories],
            "deviations": [item.confidence for item in state.deviations],
        },
        "consent_scope": {
            "proactive_enabled": state.consent.proactive_enabled,
            "signal_types": list(state.consent.signal_types),
            "updated_at": state.consent.updated_at.isoformat(),
        },
        "evidence_refs": evidence_refs,
        "clinical_event_edges": [item.model_dump(mode="json") for item in state.clinical_event_edges],
        "obligations": [item.model_dump(mode="json") for item in state.obligations],
        "active_missions": [
            item.model_dump(mode="json")
            for item in state.missions
            if item.status not in {"completed", "cancelled"}
        ],
        "result_nodes": result_nodes[-50:],
        "region_index": region_index,
        "physiology": {
            "latest_vital": latest_vital,
            "latest_weight": latest_weight,
            "latest_activity": latest_activity,
            "latest_device_metrics": latest_device,
        },
        "counts": {
            "results": len(state.results),
            "documents": len(state.documents),
            "device_observations": len(state.device_observations),
            "organ_system_states": len(state.organ_system_states),
            "anatomy_states": len(state.anatomy_states),
            "medication_expectations": len(state.medication_expectations),
            "baselines": len(state.baselines),
            "trajectories": len(state.trajectories),
            "deviations": len(state.deviations),
            "clinical_event_edges": len(state.clinical_event_edges),
            "obligations": len(state.obligations),
        },
        "updated_at": state.updated_at.isoformat(),
        "truth_boundary": (
            "El gemelo organiza evidencia persistida y su procedencia; no crea hallazgos nuevos ni sustituye la interpretación profesional."
        ),
    }
