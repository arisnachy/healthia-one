from __future__ import annotations

from pathlib import Path

from healthia_one.models import PatientState
from healthia_one.orchestrator import respond

ROOT = Path(__file__).resolve().parents[1]


def test_unanchored_reference_is_patient_visible_clarification_not_guess() -> None:
    response = respond(PatientState(), "¿Y eso?")
    assert response.message.metadata["reference_clarification_required"] is True
    assert response.message.metadata["external_action_executed"] is False
    assert response.message.metadata["conversation_context"]["needs_clarification"] is True
    assert "No tengo evidencia suficiente" in response.message.content


def test_winning_one_take_locks_wave4_taskmaster_story_and_fallback_rule() -> None:
    doc = (ROOT / "docs/WINNING_ONE_TAKE.md").read_text(encoding="utf-8")
    for marker in (
        "Problem + promise, inside the real app",
        "Evidence-first multimodal result",
        "Flagship Taskmaster mission",
        "Human boundary",
        "real Google Places",
        "The second one",
        "Real external-action proof",
        "Continuity survives logout/login",
        "Google Cloud proof",
        "existing public judge video remains the fallback",
    ):
        assert marker.lower() in doc.lower()
    assert "unresolved pronoun is guessed" in doc
    assert "exact final HEAD is not green before recording/publication" in doc
    assert "do not fake this scene" in doc.lower()
    assert "no gate is lowered" in doc.lower()


def test_judges_start_here_separates_current_wave4_from_preserved_live_proof() -> None:
    doc = (ROOT / "JUDGES_START_HERE.md").read_text(encoding="utf-8")
    assert "a48710eeb5a2e8429a91f5004129064e5af37c1a" in doc
    assert "891745e1ab93dc78b9aa4e54d65b315befa885f2" in doc
    assert "0 external Places searches before location consent" in doc
    assert "same mission" in doc
    assert "Authorization is not execution evidence" in doc
    assert "ancestor of the Wave 4 candidate" in doc
    assert "synthetic patient data" in doc


def test_submission_delta_freezes_infrastructure_and_does_not_claim_replacement() -> None:
    doc = (ROOT / "docs/WAVE3_SUBMISSION_DELTA.md").read_text(encoding="utf-8")
    assert "candidate upgrade in progress" in doc
    assert "does not replace the preserved submission candidate" in doc
    assert "Infrastructure freeze" in doc
    assert "Veo remains an optional separate cost gate" in doc
    assert "Comprobante de misión" in doc
    assert "anonymous SHA verification" in doc


def test_wave3_does_not_modify_provider_live_harness_to_autorun() -> None:
    workflow = (ROOT / ".github/workflows/google-wave2-live-providers.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow.split("jobs:", 1)[0]
    assert "I_AUTHORIZE_STT_DOCUMENTAI_HEALTHCARE_LIVE" in workflow


def test_public_receipt_comes_from_adk_event_trace_not_model_schema() -> None:
    adk = (ROOT / "healthia_one/google_mission_adk.py").read_text(encoding="utf-8")
    chat = (ROOT / "healthia_one/google_mission_chat.py").read_text(encoding="utf-8")
    assert 'payload["_execution"]' in adk
    schema_section = adk.split("MISSION_PLAN_SCHEMA", 1)[1].split("class AdkGoogleMissionRuntime", 1)[0]
    assert "executed_tools" not in schema_section
    assert 'execution = plan.get("_execution")' in chat
    assert '"public_action_receipt": receipt' in chat
