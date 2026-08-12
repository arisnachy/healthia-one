from healthia_one.models import PatientState
from healthia_one.google_mission_chat import should_consider_google_mission

# Importing the permissions module mirrors central orchestrator startup and
# installs only the additive Wave 4 resource-navigation vocabulary.
import healthia_one.opportunity_permissions  # noqa: F401,E402


def test_english_support_resource_request_routes_to_google_mission() -> None:
    state = PatientState()
    assert should_consider_google_mission(
        state,
        "Find autism support groups and community resources near Santiago",
    ) is True


def test_spanish_support_resource_request_routes_to_google_mission() -> None:
    state = PatientState()
    assert should_consider_google_mission(
        state,
        "Busca grupos de apoyo y recursos para autismo cerca de Santiago",
    ) is True


def test_government_assistance_nearby_routes_to_location_gated_mission() -> None:
    state = PatientState()
    assert should_consider_google_mission(
        state,
        "Find government assistance near Santiago",
    ) is True


def test_non_navigation_benefits_question_is_not_hijacked() -> None:
    state = PatientState()
    assert should_consider_google_mission(
        state,
        "What are the benefits of exercise?",
    ) is False
