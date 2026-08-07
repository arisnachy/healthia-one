from __future__ import annotations

from typing import Any

from healthia_one.models import PatientState


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

    return {
        "source_of_truth": "patient_state",
        "derived": True,
        "patient_id": state.profile.id,
        "conditions": list(state.profile.confirmed_conditions),
        "allergies": list(state.profile.allergies),
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
        },
        "truth_boundary": (
            "El gemelo organiza evidencia persistida y su procedencia; no crea hallazgos nuevos ni sustituye la interpretación profesional."
        ),
    }
