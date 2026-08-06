from healthia_one.family import evaluate_family_history, family_summary
from healthia_one.models import FamilyCondition, FamilyMember, PatientState
from healthia_one.orchestrator import respond
from healthia_one.service import seed_state


def test_seed_genogram_detects_family_clusters_without_diagnosis():
    state = seed_state()
    summary = family_summary(state)
    names = {item["condition"] for item in summary["clusters"]}
    assert "diabetes" in names
    assert "hipertensión arterial" in names
    findings = evaluate_family_history(state)
    assert findings
    assert all("no confirma" in item.why_it_matters.lower() for item in findings)


def test_chat_can_manage_family_history():
    response = respond(seed_state(), "Muéstrame mi genograma y antecedentes familiares")
    assert response.mission is not None
    assert response.mission.mission_type == "family_history"
    assert any(step.agent == "HEREDITAS" for step in response.message.agent_plan)


def test_non_biological_member_does_not_create_cluster():
    state = PatientState()
    state.family_members = [
        FamilyMember(
            display_name="Tutor",
            relation="tutor",
            biological_relative=False,
            conditions=[FamilyCondition(name="Diabetes")],
        ),
        FamilyMember(
            display_name="Amigo",
            relation="amigo",
            biological_relative=False,
            conditions=[FamilyCondition(name="Diabetes")],
        ),
    ]
    assert family_summary(state)["clusters"] == []
