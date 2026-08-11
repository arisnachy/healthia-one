from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave3_cloud_demo_uses_live_proven_adk_timeout() -> None:
    deploy = (ROOT / "deployment/deploy-cloud-demo.ps1").read_text(encoding="utf-8")
    assert '"HEALTHIA_LLM_TIMEOUT_SECONDS=60",' in deploy


def test_wave3_recorder_matches_shipped_conversational_clinical_ui() -> None:
    recorder = (ROOT / "scripts/record_submission_demo.py").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/cloud_browser_judge_proof.py").read_text(encoding="utf-8")
    assert "I will ask one useful thing at a time" in recorder
    assert '.clinical-next-question' in recorder
    assert "Case-specific questions" not in recorder
    assert "shipped one-at-a-time conversation UI" in helper
    assert "patient-visible 2+3 flow" not in helper
    assert '.clinical-show-all' not in helper
    assert '.clinical-submit' not in helper


def test_wave3_places_story_uses_unambiguous_patient_supplied_search_location() -> None:
    recorder = (ROOT / "scripts/record_submission_demo.py").read_text(encoding="utf-8")
    assert "Find a clinic that can help with follow-up care in Santiago de los Caballeros, Dominican Republic." in recorder


def test_location_consent_auto_resumes_the_same_safe_adk_tool() -> None:
    chat = (ROOT / "healthia_one/google_mission_chat.py").read_text(encoding="utf-8")
    assert "GoogleMissionToolFacade" in chat
    assert "discover_care_options(consent_mission_id)" in chat
    assert 'action="resume_google_health_mission_after_location_consent"' in chat
    assert '"external_mutation_performed": False' in chat
