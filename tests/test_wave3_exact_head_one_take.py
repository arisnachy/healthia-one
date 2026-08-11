from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave3_one_take_is_manual_only_and_exactly_authorized() -> None:
    workflow = (ROOT / ".github/workflows/wave3-exact-head-one-take.yml").read_text(encoding="utf-8")
    trigger = workflow.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger
    assert "pull_request:" not in trigger
    assert "push:" not in trigger
    assert "I_AUTHORIZE_WAVE3_EXACT_CLOUD_ONE_TAKE" in workflow
    assert "candidate_sha" in trigger
    assert "^[0-9a-fA-F]{40}$" in workflow
    assert "cancel-in-progress: false" in workflow


def test_wave3_one_take_fails_locally_before_cloud_and_deploys_exact_sha() -> None:
    workflow = (ROOT / ".github/workflows/wave3-exact-head-one-take.yml").read_text(encoding="utf-8")
    assert 'ref: ${{ steps.gate.outputs.candidate_sha }}' in workflow
    assert 'ref: ${{ needs.exact-head-preflight.outputs.candidate_sha }}' in workflow
    assert 'test "$actual" = "$EXPECTED_SHA"' in workflow
    assert 'test "$actual" = "$CANDIDATE_SHA"' in workflow
    assert "pytest -q" in workflow
    assert "python scripts/full_system_check.py" in workflow
    assert "python scripts/dialogbench.py" in workflow
    assert "python scripts/judge_omega.py" in workflow
    assert "deploy-cloud-demo.ps1" in workflow
    assert "-RequestLimit 20" in workflow
    assert "-Confirmed" in workflow
    assert "python deployment/verify_cloud_demo.py" in workflow


def test_wave3_recorder_is_bound_to_exact_candidate_and_winner_scenes() -> None:
    workflow = (ROOT / ".github/workflows/wave3-exact-head-one-take.yml").read_text(encoding="utf-8")
    recorder = (ROOT / "scripts/record_submission_demo.py").read_text(encoding="utf-8")
    assert 'HEALTHIA_CANDIDATE_SHA: ${{ env.CANDIDATE_SHA }}' in workflow
    assert 'CANDIDATE_SHA = os.getenv("HEALTHIA_CANDIDATE_SHA", "")' in recorder
    assert 'require(len(CANDIDATE_SHA) == 40' in recorder
    for marker in (
        "wave3_unanchored_reference_fails_closed",
        "wave3_evidence_backed_reference_resolution",
        "wave3_places_stops_before_mission_location_consent",
        "wave3_mission_scoped_location_consent_then_real_places",
        "wave3_ordinal_resumes_and_selects_durable_mission",
        "relogin_continuity_including_google_mission",
        "zero_browser_console_or_page_errors",
    ):
        assert marker in recorder
        assert marker in workflow
    assert "What about that?" in recorder
    assert "I authorize my location for this mission." in recorder
    assert "The second one." in recorder


def test_wave3_recording_never_auto_publishes_or_claims_submission_replacement() -> None:
    workflow = (ROOT / ".github/workflows/wave3-exact-head-one-take.yml").read_text(encoding="utf-8")
    assert "releases/" not in workflow
    assert "gh release" not in workflow.lower()
    assert "public_release_performed\": False" in workflow
    assert "does not replace or publish the preserved judge video automatically" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "HealthIA-Wave3-exact-head-one-take" in workflow


def test_wave3_recording_does_not_enable_new_apis_or_touch_veo() -> None:
    workflow = (ROOT / ".github/workflows/wave3-exact-head-one-take.yml").read_text(encoding="utf-8")
    lowered = workflow.lower()
    assert "gcloud services enable" not in lowered
    assert "serviceusage.services.enable" not in lowered
    assert "veo" not in lowered
    assert "roles/owner" not in lowered
    assert "roles/editor" not in lowered
