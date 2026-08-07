from healthia_one.clinical_planner import select_on_demand_agents
from healthia_one.service import seed_state


def test_selected_specialists_execute_concrete_tools() -> None:
    state = seed_state()
    steps = select_on_demand_agents(
        state,
        "Desde ayer me arde al orinar y tomé un medicamento sin receta",
        [],
        stage=1,
        requested_roles=["interview", "safety", "medication"],
    )

    assert {step.agent for step in steps} == {"INTERVIEWER", "SENTINEL", "MEDSAFE"}
    assert all(step.status == "completed" for step in steps)
    assert all("Resultado verificable:" in step.action for step in steps)
    medication = next(step for step in steps if step.agent == "MEDSAFE")
    assert "medicamentos activos" in medication.action
    assert "ARCHIVUM" not in {step.agent for step in steps}
    assert "LUMEN" not in {step.agent for step in steps}


def test_second_block_caps_the_council_at_four_areas() -> None:
    state = seed_state()
    steps = select_on_demand_agents(
        state,
        "Quiero revisar un resultado y un documento antes de mi consulta",
        [{"question_id": "history", "selected": ["Episodio parecido anterior"], "detail": ""}],
        stage=2,
        requested_roles=["results", "documents", "history", "follow_up"],
    )

    assert 2 <= len(steps) <= 4
    assert [step.agent for step in steps[:2]] == ["INTERVIEWER", "SENTINEL"]
    assert all("Resultado verificable:" in step.action for step in steps)
