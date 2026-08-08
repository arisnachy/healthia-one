from healthia_one.deterministic_router import respond
from healthia_one.models import ClinicalDocument, HealthResult, MissionStatus
from healthia_one.service import seed_state


def test_result_review_mission_closes_with_result_and_original_evidence() -> None:
    state = seed_state()
    result = HealthResult(
        filename="synthetic-lab.pdf",
        panel="Laboratorio sintético",
        status="parsed",
        explained=True,
        explanation="Glucosa y hemoglobina extraídas del documento sintético.",
    )
    document = ClinicalDocument(
        patient_id=state.profile.id,
        title="Evidencia laboratorio",
        filename="synthetic-lab.pdf",
        storage_path="uploads/patient_demo/synthetic-lab.pdf",
        status="parsed",
        related_result_id=result.id,
    )
    state.results.append(result)
    state.documents.append(document)

    response = respond(state, "Explícame el resultado synthetic-lab.pdf que subí")

    assert response.mission is not None
    assert response.mission.mission_type == "result_explanation"
    assert response.mission.status == MissionStatus.COMPLETED
    assert result.id in response.mission.evidence_ids
    assert document.id in response.mission.evidence_ids
    assert response.mission.closure_evidence == [
        "persisted_result_retrieved",
        "patient_explanation_returned",
        "original_evidence_link_resolved",
    ]
    assert "Misión cerrada" in response.mission.next_action
    assert "synthetic-lab.pdf" in response.message.content


def test_result_review_mission_stays_open_without_persisted_result() -> None:
    state = seed_state()
    response = respond(state, "Explícame el resultado que subí")

    assert response.mission is not None
    assert response.mission.status == MissionStatus.ACTIVE
    assert response.mission.evidence_ids == []
    assert response.mission.closure_evidence == []
    assert response.mission.next_action == "Cargar el resultado que quieres revisar"
