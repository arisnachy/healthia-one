from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from healthia_one.models import (
    AnatomicalLink,
    ClinicalTwinEvent,
    HealthResult,
    OpenClinicalLoop,
    PatientState,
    SourceRef,
)


def _event_at_from_result(result: HealthResult) -> datetime:
    if result.exam_date:
        return datetime.combine(result.exam_date, time.min, tzinfo=timezone.utc)
    return result.uploaded_at


def _result_certainty(result: HealthResult) -> str:
    if result.verification_status == "document_reported":
        return "document_reported"
    if result.verification_status in {"ai_observed_unverified", "mixed_unverified"}:
        return "ai_extraction"
    return "unknown"


def _verification(result: HealthResult) -> str:
    if result.verification_status == "document_reported":
        return "verified" if result.source.verified else "pending_review"
    if result.verification_status == "mixed_unverified":
        return "mixed"
    return "unverified"


def _anatomical_system(region: str) -> str:
    text = region.lower()
    mappings = (
        ("Respiratory", ("lung", "pulm", "chest", "thorax", "torax", "pleura", "bronch")),
        ("Cardiovascular", ("heart", "cardiac", "coron", "aorta", "vascular", "arter")),
        ("Neurologic", ("brain", "cerebr", "head", "cran", "neuro", "spinal cord")),
        ("Genitourinary", ("kidney", "renal", "bladder", "ureter", "urinary", "prostate")),
        ("Gastrointestinal", ("abdomen", "abdominal", "liver", "hepatic", "pancre", "bowel", "colon", "stomach")),
        ("Musculoskeletal", ("bone", "joint", "spine", "lumbar", "cervical", "shoulder", "knee", "muscle")),
        ("Reproductive", ("uter", "ovary", "ovarian", "pelvis", "breast", "mamm")),
    )
    for system, needles in mappings:
        if any(needle in text for needle in needles):
            return system
    return "Other"


def _laterality(region: str) -> str:
    text = region.lower()
    if any(token in text for token in ("left", "izquierd")):
        return "left"
    if any(token in text for token in ("right", "derech")):
        return "right"
    if any(token in text for token in ("bilateral", "ambos", "both")):
        return "bilateral"
    return "unknown"


def _append_event_once(state: PatientState, event: ClinicalTwinEvent) -> ClinicalTwinEvent:
    existing = next(
        (
            item
            for item in state.twin_events
            if item.event_type == event.event_type
            and item.entity_type == event.entity_type
            and item.entity_id == event.entity_id
        ),
        None,
    )
    if existing:
        return existing
    state.twin_events.append(event)
    state.twin_events.sort(key=lambda item: (item.event_at, item.recorded_at))
    return event


def _open_loop_once(state: PatientState, loop: OpenClinicalLoop) -> OpenClinicalLoop:
    existing = next(
        (item for item in state.open_clinical_loops if item.topic == loop.topic and item.status == "open"),
        None,
    )
    if existing:
        return existing
    state.open_clinical_loops.append(loop)
    return loop


def record_result_in_state(state: PatientState, result: HealthResult) -> ClinicalTwinEvent:
    result.patient_id = state.profile.id
    summary = result.reported_impression or result.explanation or result.panel
    event = _append_event_once(
        state,
        ClinicalTwinEvent(
            patient_id=state.profile.id,
            event_type="result_ingested",
            entity_type="result",
            entity_id=result.id,
            event_at=_event_at_from_result(result),
            title=result.panel or result.filename,
            summary=summary[:2400],
            source=result.source,
            certainty=_result_certainty(result),
            verification_status=_verification(result),
            payload={
                "filename": result.filename,
                "artifact_type": result.artifact_type,
                "modality": result.modality,
                "anatomical_region": result.anatomical_region,
                "exam_date": result.exam_date.isoformat() if result.exam_date else None,
                "reported_impression": result.reported_impression,
                "ai_observations": result.ai_observations,
                "measurements": [item.model_dump(mode="json") for item in result.items],
                "safety_flags": result.safety_flags,
                "quality_limitations": result.quality_limitations,
                "ai_confidence": result.ai_confidence,
                "verification_status": result.verification_status,
                "original_storage_uri": result.original_storage_uri,
            },
        ),
    )

    if result.anatomical_region and not any(
        item.entity_type == "result" and item.entity_id == result.id for item in state.anatomical_links
    ):
        status = "document_reported" if result.reported_impression else (
            "suspected" if result.ai_observations else "unknown"
        )
        state.anatomical_links.append(
            AnatomicalLink(
                patient_id=state.profile.id,
                system=_anatomical_system(result.anatomical_region),
                region=result.anatomical_region,
                laterality=_laterality(result.anatomical_region),
                entity_type="result",
                entity_id=result.id,
                status=status,
                source=result.source,
            )
        )

    if result.status == "pending_multimodal":
        _open_loop_once(
            state,
            OpenClinicalLoop(
                patient_id=state.profile.id,
                topic=f"result:{result.id}:interpretation",
                target_field="result.verification_status",
                question=f"Revisar {result.filename} cuando exista una interpretación disponible.",
                reason="El archivo está conservado pero aún no existe extracción multimodal verificable.",
                priority="medium",
                source_event_ids=[event.id],
            ),
        )
    elif result.ai_observations or result.safety_flags:
        _open_loop_once(
            state,
            OpenClinicalLoop(
                patient_id=state.profile.id,
                topic=f"result:{result.id}:professional_review",
                target_field="result.verification_status",
                question=f"¿Este resultado ya fue revisado por un profesional?",
                reason="La extracción de IA debe permanecer separada de un hallazgo clínicamente confirmado.",
                priority="high" if result.safety_flags else "medium",
                source_event_ids=[event.id],
            ),
        )
    return event


def record_interview_in_state(
    state: PatientState,
    *,
    interview_id: str,
    chief_complaint: str,
    answers: list[dict[str, Any]],
) -> ClinicalTwinEvent:
    compact_answers: list[dict[str, Any]] = []
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        compact_answers.append(
            {
                "question_id": str(answer.get("question_id", ""))[:120],
                "question": str(answer.get("question_prompt", ""))[:500],
                "selected": [str(item)[:220] for item in answer.get("selected", [])][:20],
                "detail": str(answer.get("detail", ""))[:800],
            }
        )
    event = _append_event_once(
        state,
        ClinicalTwinEvent(
            patient_id=state.profile.id,
            event_type="clinical_interview_reported",
            entity_type="clinical_interview",
            entity_id=interview_id,
            title="Información referida durante conversación clínica",
            summary=chief_complaint[:2400],
            source=SourceRef(source_type="patient_report", source_id=interview_id, verified=False),
            certainty="patient_reported",
            verification_status="unverified",
            payload={"chief_complaint": chief_complaint, "answers": compact_answers},
        ),
    )
    return event


def record_measurement_in_state(state: PatientState, item: Any, kind: str) -> ClinicalTwinEvent:
    source = getattr(item, "source", SourceRef(source_type="patient_entry", source_id="web"))
    event_at = getattr(item, "measured_at", None) or getattr(item, "recorded_at", None) or datetime.now(timezone.utc)
    return _append_event_once(
        state,
        ClinicalTwinEvent(
            patient_id=state.profile.id,
            event_type=f"{kind}_recorded",
            entity_type=kind,
            entity_id=str(getattr(item, "id", "")),
            event_at=event_at,
            title=f"{kind.replace('_', ' ').title()} registrado",
            source=source,
            certainty="device_observed" if source.source_type == "health_connect" else "patient_reported",
            verification_status="verified" if source.verified else "unverified",
            payload=item.model_dump(mode="json") if hasattr(item, "model_dump") else {},
        ),
    )


def record_device_observation_in_state(state: PatientState, observation: Any) -> ClinicalTwinEvent:
    source = SourceRef(
        source_type="health_connect",
        source_id=observation.source_package or observation.source_name or "health_connect",
        captured_at=observation.observed_at,
        verified=True,
    )
    return _append_event_once(
        state,
        ClinicalTwinEvent(
            patient_id=state.profile.id,
            event_type="device_observation",
            entity_type="device_metric",
            entity_id=observation.id,
            event_at=observation.observed_at,
            title=f"Dato de dispositivo: {observation.metric}",
            source=source,
            certainty="device_observed",
            verification_status="verified",
            payload=observation.model_dump(mode="json"),
        ),
    )


async def persist_result(service: Any, result: HealthResult) -> ClinicalTwinEvent:
    async with service._mutation_lock:
        state = await service.store.load()
        event = record_result_in_state(state, result)
        await service.store.save(state)
    await service.broker.publish({"type": "state", "section": "twin"})
    return event


async def persist_measurement(service: Any, item: Any, kind: str) -> ClinicalTwinEvent:
    async with service._mutation_lock:
        state = await service.store.load()
        event = record_measurement_in_state(state, item, kind)
        await service.store.save(state)
    await service.broker.publish({"type": "state", "section": "twin"})
    return event
