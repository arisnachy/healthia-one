from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_DOCS_VIDEO_URL = "https://youtu.be/44LfVn9pPdU"
RECORDED_CANONICAL_VIDEO_URL = "https://youtu.be/v7SJUkzzRxw"


def test_public_judge_video_proof_preserves_machine_truth_boundary() -> None:
    proof = json.loads(
        (ROOT / "hackathon/evidence/public_judge_video_proof.json").read_text(encoding="utf-8")
    )
    assert proof["status"] == "CANONICAL_CURRENT_SUBMISSION"
    assert proof["synthetic_only"] is True
    assert proof["canonical_submission"]["youtube_url"] == RECORDED_CANONICAL_VIDEO_URL
    assert proof["machine_verified_current_master"]["continuous_real_application_master"] is True
    assert proof["external_host_visibility"]["youtube_public_privacy_state"] == "NOT_ASSERTED_BY_THIS_MACHINE_PROOF"
    assert proof["historical_public_video"]["not_for_submission"] is True
    assert "does not claim" in proof["truth_boundary"]


def test_current_submission_documents_use_one_recorded_url_without_claiming_machine_proof() -> None:
    for relative in ("README.md", "JUDGES_START_HERE.md", "docs/DEVPOST_SUBMISSION.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert CURRENT_DOCS_VIDEO_URL in text, relative
        assert "99/100" not in text, relative


def test_all_expensive_or_mutating_submission_triggers_are_disabled() -> None:
    trigger_paths = (
        ROOT / ".github/cloud-proof-trigger.txt",
        ROOT / ".github/cloud-continuity-trigger.txt",
        ROOT / ".github/submission-demo-trigger.txt",
        ROOT / ".github/submission-publish-trigger.txt",
    )
    for path in trigger_paths:
        assert path.is_file(), path
        text = path.read_text(encoding="utf-8")
        assert "enabled=false" in text, path
        assert "enabled=true" not in text, path


def test_superseded_gcs_publication_workflows_are_absent() -> None:
    assert not (ROOT / ".github/workflows/publish-submission-video.yml").exists()
    assert not (ROOT / ".github/workflows/public-video-publish-proof.yml").exists()
    assert (ROOT / ".github/workflows/release-submission-video.yml").is_file()
    assert (ROOT / ".github/workflows/public-video-probe.yml").is_file()
