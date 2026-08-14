from healthia_one.education_video_models import EducationFact, EducationScene, EducationVideoPlan
from healthia_one.education_video_recovery import harden_plan_for_delivery, validate_hardened_plan


def facts():
    return [
        EducationFact(
            key="result_glucose",
            label="Glucose",
            value="103 mg/dL",
            source_id="result_demo",
            source_type="health_result",
            certainty="recorded",
        )
    ]


def test_hardening_filters_unknown_fact_and_downgrades_unsafe_veo():
    plan = EducationVideoPlan(
        title="Understanding your glucose result",
        patient_fact_keys=["result_glucose", "unknown_fact"],
        scenes=[
            EducationScene(
                heading="Your result",
                body="A controlled card can show the exact value.",
                narration="Your recorded value stays on the controlled HealthIA card.",
                visual_kind="veo",
                veo_prompt="Show glucose 103 mg/dL flowing through the bloodstream",
            ),
            EducationScene(
                heading="What glucose does",
                body="Glucose is an energy source used by cells.",
                narration="Glucose circulates in the blood and is used by cells for energy.",
                visual_kind="veo",
                veo_prompt="Generic medical education animation of glucose moving from blood into cells with no text or numbers",
            ),
            EducationScene(
                heading="Follow-up",
                body="Use the result to prepare questions for your care team.",
                narration="Use this explanation to prepare questions for your care team.",
            ),
        ],
    )

    hardened = harden_plan_for_delivery(plan, facts(), "Demo Patient")
    assert hardened.patient_fact_keys == ["result_glucose"]
    assert hardened.scenes[0].visual_kind == "card"
    assert hardened.scenes[0].veo_prompt == ""
    assert sum(scene.visual_kind == "veo" for scene in hardened.scenes) == 1
    validate_hardened_plan(hardened, facts(), "Demo Patient")


def test_safe_medication_negation_is_not_treated_as_a_change_instruction():
    plan = EducationVideoPlan(
        title="Safe education",
        scenes=[
            EducationScene(
                heading="Safety",
                body="Do not change your dose based on this video.",
                narration="Do not change your dose based on this video.",
            ),
            EducationScene(heading="Context", body="Review the result with your care team.", narration="Review the result with your care team."),
            EducationScene(heading="Questions", body="Prepare questions for follow-up.", narration="Prepare questions for follow-up."),
        ],
    )
    validate_hardened_plan(plan, facts(), "Demo Patient")


def test_real_medication_change_instruction_remains_fail_closed():
    plan = EducationVideoPlan(
        title="Unsafe education",
        scenes=[
            EducationScene(heading="Unsafe", body="Increase your dose today.", narration="Increase your dose today."),
            EducationScene(heading="Context", body="Review the result with your care team.", narration="Review the result with your care team."),
            EducationScene(heading="Questions", body="Prepare questions for follow-up.", narration="Prepare questions for follow-up."),
        ],
    )

    try:
        validate_hardened_plan(plan, facts(), "Demo Patient")
    except ValueError as exc:
        assert "medication-change" in str(exc)
    else:
        raise AssertionError("unsafe medication instruction must remain fail-closed")
