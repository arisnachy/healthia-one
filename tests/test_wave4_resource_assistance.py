from healthia_one.models import FamilyCondition, FamilyMember
from healthia_one.opportunity_autopilot import AssistanceProgram, ProgramRequirement
from healthia_one.opportunity_store import MemoryOpportunityStore
from healthia_one.service import seed_state
import healthia_one.opportunity_integration as integration


def test_each_explicit_resource_search_gets_a_fresh_bounded_radar(monkeypatch):
    monkeypatch.setattr(integration, "_paid_resource_ai_enabled", lambda: True)

    first = integration._new_resource_radar()
    second = integration._new_resource_radar()

    assert first is not second
    assert first.enabled is True
    assert second.enabled is True
    assert first.max_calls == 1
    assert second.max_calls == 1
    assert first.calls == 0
    assert second.calls == 0


def test_resource_topic_can_target_a_family_condition_instead_of_scanning_unrelated_topics(monkeypatch):
    store = MemoryOpportunityStore()
    monkeypatch.setattr(integration, "_STORE", store)
    state = seed_state()
    state.family_members.append(
        FamilyMember(
            display_name="Child",
            relation="son",
            generation=1,
            conditions=[FamilyCondition(name="Autism", confirmed=True)],
        )
    )
    integration._sync_topics(state)

    subject_id, condition = integration._explicit_resource_topic(
        state,
        "Find financial assistance and support programs for autism",
    )

    assert subject_id
    assert condition.lower() == "autism"


def test_application_request_is_explicit_and_generic_form_questions_do_not_trigger_it():
    assert integration._application_request("Prepare the application for this program") is True
    assert integration._application_request("Completa el formulario de esa ayuda") is True
    assert integration._application_request("What documents might a program require?") is False


def test_unverified_program_requirements_must_be_verified_before_prefill():
    program = AssistanceProgram(
        title="Synthetic support program",
        provider="Synthetic government office",
        url="https://example.gov/program",
        requirements=[
            ProgramRequirement(
                key="req_1",
                label="Official eligibility requirement",
                rule={"type": "unknown", "source_verification_required": True},
            )
        ],
    )

    assert integration._program_needs_verification(program) is True


def test_verified_program_requirements_do_not_force_another_source_verification():
    program = AssistanceProgram(
        title="Synthetic support program",
        provider="Synthetic government office",
        url="https://example.gov/program",
        requirements=[
            ProgramRequirement(
                key="req_1",
                label="Verified condition requirement",
                rule={"type": "condition", "value": "Autism", "source_verification_required": False},
            )
        ],
    )

    assert integration._program_needs_verification(program) is False