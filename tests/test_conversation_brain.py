from __future__ import annotations

from healthia_one.conversation_brain import build_frame, explicit_topic, selective_memory, semantic_packet
from healthia_one.models import ChatMessage, HealthMission, MissionStatus, PatientState
from scripts.dialogbench import run, scenarios


def _state(target: str, mission_type: str) -> PatientState:
    state = PatientState()
    mission = HealthMission(
        title="Continuity thread",
        mission_type=mission_type,
        status=MissionStatus.WAITING_PATIENT,
        next_action="Continue",
    )
    state.missions.append(mission)
    state.messages.extend([
        ChatMessage(role="patient", author="Patient", content="Quiero revisar esto."),
        ChatMessage(
            role="assistant",
            author="HealthIA",
            content="Ya encontré el contexto que estabas revisando.",
            mission_id=mission.id,
            metadata={"action_target": target, "mission_type": mission_type},
        ),
    ])
    return state


def test_result_pronoun_keeps_prior_verified_topic_without_rewriting_patient_words() -> None:
    frame = build_frame(_state("results", "result_explanation"), "¿Y eso es grave?")
    assert frame.ambiguous_reference is True
    assert frame.routing_text.startswith("¿Y eso es grave?")
    assert "resultado" in frame.routing_text.lower()
    assert frame.last_action_target == "results"
    assert frame.reference_status == "resolved_recent_context"
    assert frame.resolved_reference is not None
    assert frame.resolved_reference["target"] == "results"
    assert frame.needs_clarification is False


def test_explicit_current_result_outranks_stale_treatment_context_even_with_pronoun() -> None:
    frame = build_frame(
        _state("treatment", "medication_management"),
        "Explain the result I just uploaded and confirm it was saved with the original file.",
    )

    assert frame.ambiguous_reference is True
    assert frame.last_action_target == "treatment"
    assert frame.current_topic == "results"
    assert frame.reference_status == "explicit_current_topic"
    assert frame.routing_text == "Explain the result I just uploaded and confirm it was saved with the original file."
    assert "CONTEXTUAL_ROUTING_HINT" not in frame.routing_text


def test_explicit_current_pressure_outranks_stale_result_context() -> None:
    frame = build_frame(_state("results", "result_explanation"), "No, I mean my blood pressure; is it improving?")

    assert frame.correction is True
    assert frame.current_topic == "measurements"
    assert frame.routing_text == "No, I mean my blood pressure; is it improving?"
    assert "CONTEXTUAL_ROUTING_HINT" not in frame.routing_text


def test_blood_pressure_followup_uses_measurement_context() -> None:
    frame = build_frame(_state("measurements", "blood_pressure"), "¿Y mañana?")
    assert frame.ambiguous_reference is True
    assert "presion" in frame.routing_text.lower()


def test_correction_is_marked_but_explicit_current_words_are_preserved() -> None:
    frame = build_frame(_state("results", "result_explanation"), "No, me refería a mi presión")
    assert frame.correction is True
    assert frame.current_topic == "measurements"
    assert frame.routing_text.startswith("No, me refería a mi presión")
    assert "CONTEXTUAL_ROUTING_HINT" not in frame.routing_text


def test_unanchored_pronoun_fails_closed_instead_of_guessing() -> None:
    state = PatientState()
    frame = build_frame(state, "¿Y eso?")
    assert frame.ambiguous_reference is True
    assert frame.reference_status == "needs_clarification"
    assert frame.resolved_reference is None
    assert frame.needs_clarification is True
    assert frame.routing_text == "¿Y eso?"


def test_semantic_packet_carries_fail_closed_reference_contract() -> None:
    packet = semantic_packet(PatientState(), "the second one")
    conversation = packet["conversation"]
    assert conversation["needs_clarification"] is True
    assert conversation["reference_status"] == "needs_clarification"
    assert conversation["resolved_reference"] is None
    assert "instead of guessing" in packet["instruction"]


def test_explicit_topic_is_deterministic_for_winner_demo_domains() -> None:
    assert explicit_topic("No, hablaba de mi presión") == "measurements"
    assert explicit_topic("abre el resultado de laboratorio") == "results"
    assert explicit_topic("quiero ver mi documento") == "documents"
    assert explicit_topic("show my Health Connect device") == "devices"


def test_selective_memory_does_not_dump_hidden_clinical_payloads() -> None:
    state = _state("results", "result_explanation")
    state.messages.append(ChatMessage(role="patient", author="Patient", content='[ENTREVISTA_CLINICA]{"secret":"raw"}'))
    memory = selective_memory(state)
    assert memory
    assert all("ENTREVISTA_CLINICA" not in item["content"] for item in memory)
    assert len(memory) <= 12
    assert sum(len(item["content"]) for item in memory) <= 6000


def test_dialogbench_has_more_than_one_hundred_adversarial_followups() -> None:
    values = scenarios()
    assert len(values) >= 120
    assert {item.locale for item in values} == {"en", "es"}
    assert {"pronoun", "correction", "typo", "spanglish"} <= {item.category for item in values}


def test_dialogbench_context_gate_passes() -> None:
    report = run()
    assert report["status"] == "PASS"
    assert report["dialogue_count"] >= 120
    assert report["score"] >= 0.98
    assert "not perfect human conversation" in report["claim_boundary"].lower()
