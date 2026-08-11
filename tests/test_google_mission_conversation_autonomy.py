from __future__ import annotations

from pathlib import Path

from healthia_one.google_mission_chat import should_consider_google_mission
from healthia_one.models import ChatMessage, PatientState

ROOT = Path(__file__).resolve().parents[1]


def _state_with_google_mission() -> PatientState:
    state = PatientState()
    state.messages.extend(
        [
            ChatMessage(role="patient", author="Patient", content="Busca una clínica cerca de Santiago."),
            ChatMessage(
                role="assistant",
                author="HealthIA",
                content="Encontré tres opciones verificables. ¿Cuál prefieres?",
                metadata={
                    "google_mission_id": "gmission_demo",
                    "google_mission_state": "awaiting_selection",
                    "google_mission_next_action": "patient_or_context_selects_candidate",
                },
            ),
        ]
    )
    return state


def test_active_google_mission_understands_ordinal_correction() -> None:
    state = _state_with_google_mission()
    assert should_consider_google_mission(state, "No, la segunda") is True
    assert should_consider_google_mission(state, "the second one") is True


def test_active_google_mission_understands_natural_continuation() -> None:
    state = _state_with_google_mission()
    assert should_consider_google_mission(state, "Ese me sirve") is True
    assert should_consider_google_mission(state, "continúa con eso") is True
    assert should_consider_google_mission(state, "go ahead with that") is True


def test_explicit_clinical_topic_switch_outranks_old_google_mission() -> None:
    state = _state_with_google_mission()
    assert should_consider_google_mission(state, "No, hablaba de mi presión") is False
    assert should_consider_google_mission(state, "abre el resultado de laboratorio") is False


def test_no_google_mission_means_generic_pronoun_is_not_hijacked() -> None:
    state = PatientState()
    assert should_consider_google_mission(state, "la segunda") is False
    assert should_consider_google_mission(state, "continúa con eso") is False


def test_adk_autonomy_and_execution_receipt_are_locked_to_real_events() -> None:
    adk = (ROOT / "healthia_one/google_mission_adk.py").read_text(encoding="utf-8")
    chat = (ROOT / "healthia_one/google_mission_chat.py").read_text(encoding="utf-8")

    assert "continue through every verifiable read-only or non-mutating step" in adk
    assert "Stop immediately at the first real human/external boundary" in adk
    assert 'executed_tools: list[str] = []' in adk
    assert 'getattr(part, "function_call", None)' in adk
    assert 'payload["_execution"]' in adk
    assert '"public_action_receipt": receipt' in chat
    assert '"requires_human_authorization": requires_auth' in chat
    assert 'action="advance_google_health_mission"' in chat
    assert '### Comprobante de misión' in chat
    assert 'content = f"{content}\\n\\n{_receipt_markdown(receipt)}"' in chat
    assert "HealthIA no ejecutó ese paso por su cuenta" in chat


def test_adk_tool_response_short_circuits_exact_location_authorization_boundary() -> None:
    from healthia_one.google_mission_adk import _boundary_plan_from_tool_response

    plan = _boundary_plan_from_tool_response(
        "discover_care_options",
        {
            "result": {
                "ok": True,
                "mission_id": "gmission_demo",
                "state": "blocked",
                "next_action": "authorize_location_for_mission",
                "requires_authorization": True,
                "authorization_kind": "maps_location_for_mission",
                "public_summary": "Google Places lookup is paused; no Places search was performed.",
                "data": {"candidates": []},
            }
        },
    )
    assert plan is not None
    assert plan["mission_id"] == "gmission_demo"
    assert plan["state"] == "blocked"
    assert plan["requires_human_authorization"] is True
    assert plan["authorization_kind"] == "maps_location_for_mission"
    assert plan["next_action"] == "authorize_location_for_mission"
    assert plan["ui_action"]["type"] == "authorize_google_location"
    assert "no Places search" in plan["patient_message"]
    assert plan["_boundary_source"] == "tool_response:discover_care_options"


def test_adk_tool_response_does_not_short_circuit_without_real_authorization_boundary() -> None:
    from healthia_one.google_mission_adk import _boundary_plan_from_tool_response

    assert _boundary_plan_from_tool_response(
        "discover_care_options",
        {
            "result": {
                "mission_id": "gmission_demo",
                "state": "awaiting_selection",
                "next_action": "patient_or_context_selects_candidate",
                "requires_authorization": False,
                "authorization_kind": "",
                "public_summary": "Found two place candidates.",
            }
        },
    ) is None


def test_adk_runtime_reads_function_response_events_and_returns_before_post_tool_model_round() -> None:
    source = (ROOT / "healthia_one/google_mission_adk.py").read_text(encoding="utf-8")
    assert 'getattr(part, "function_response", None)' in source
    assert '_boundary_plan_from_tool_response(response_name, response_payload)' in source
    assert '"stopped_at_real_boundary": True' in source
    assert 'return boundary_payload' in source
    assert '"Google Places lookup is paused until the patient explicitly authorizes location lookup for this mission; "' in source
    assert '"no Places search was performed."' in source


def test_explicit_candidate_ordinal_parser_is_bounded_and_bilingual() -> None:
    from healthia_one.google_mission_chat import _explicit_candidate_ordinal_index

    assert _explicit_candidate_ordinal_index("The first one.") == 0
    assert _explicit_candidate_ordinal_index("The second one.") == 1
    assert _explicit_candidate_ordinal_index("No, the third one") == 2
    assert _explicit_candidate_ordinal_index("la primera") == 0
    assert _explicit_candidate_ordinal_index("No, la segunda") == 1
    assert _explicit_candidate_ordinal_index("el tercero") == 2
    assert _explicit_candidate_ordinal_index("the second clinic near me") is None
    assert _explicit_candidate_ordinal_index("second opinion") is None


def test_explicit_ordinal_selection_bypasses_adk_and_persists_exact_discovered_candidate() -> None:
    import asyncio
    from healthia_one.google_mission_chat import GoogleMissionConversationRouter
    from healthia_one.google_mission_runtime import MemoryMissionStore, MissionState
    from healthia_one.google_navigation_coordinator import HealthIAGoogleMissionCoordinator
    from healthia_one.models import ChatMessage, PatientState

    class _MustNotExecuteProvider:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("No provider connector is needed to select an already discovered candidate")

    class _Constellation:
        def __init__(self, patient_id: str):
            self.patient_id = patient_id
            self.store = MemoryMissionStore()
            self.coordinator = HealthIAGoogleMissionCoordinator(_MustNotExecuteProvider(), store=self.store)
        def load_mission(self, patient_id: str, mission_id: str):
            assert patient_id == self.patient_id
            value = self.store.load(patient_id, mission_id)
            if value is None:
                raise KeyError(mission_id)
            return value
        def grants(self, patient_id: str):
            assert patient_id == self.patient_id
            return []

    class _AdkMustNotInterpretOrdinal:
        ready = True
        async def run(self, **_kwargs):
            raise AssertionError("An explicit ordinal candidate choice must not require Gemini interpretation")

    state = PatientState()
    constellation = _Constellation(state.profile.id)
    mission = constellation.coordinator.create_navigation_mission(
        patient_id=state.profile.id,
        condition_or_need="follow-up care",
        provider_query="clinic",
        location_text="Santiago de los Caballeros, Dominican Republic",
    )
    mission.state = MissionState.AWAITING_SELECTION
    mission.tool_outputs["place_candidates"] = [
        {"id": "place-a", "displayName": {"text": "Clinic A"}, "formattedAddress": "Synthetic A"},
        {"id": "place-b", "displayName": {"text": "Clinic B"}, "formattedAddress": "Synthetic B"},
        {"id": "place-c", "displayName": {"text": "Clinic C"}, "formattedAddress": "Synthetic C"},
    ]
    constellation.store.save(mission)
    state.messages.append(
        ChatMessage(
            role="assistant",
            author="HealthIA",
            content="I found three verified options.",
            metadata={
                "google_mission_id": mission.id,
                "google_mission_state": "awaiting_selection",
                "google_mission_next_action": "patient_or_context_selects_candidate",
            },
        )
    )

    router = GoogleMissionConversationRouter.__new__(GoogleMissionConversationRouter)
    router.settings = None
    router.constellation = constellation
    router.adk = _AdkMustNotInterpretOrdinal()
    response = asyncio.run(router.respond(state, "The second one."))
    persisted = constellation.load_mission(state.profile.id, mission.id)

    assert persisted.selected_place["id"] == "place-b"
    assert response.message.metadata["google_mission_id"] == mission.id
    assert response.message.metadata["deterministic_candidate_index"] == 1
    assert response.message.metadata["policy_executed_tool"] == "select_discovered_candidate"
    assert response.message.metadata["external_action_executed"] is False
    assert response.message.metadata["external_mutation_performed"] is False
    receipt = response.message.metadata["public_action_receipt"]
    assert receipt["tool_count"] == 1
    assert any("selection" in str(step).lower() or "selección" in str(step).lower() for step in receipt["executed_steps"])
