from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_VIDEO_URL = "https://youtu.be/44LfVn9pPdU"
HISTORICAL_ONE_SAFETY_URL = (
    "https://github.com/arisnachy/healthia-one/releases/download/"
    "healthia-one-autonomous-winner-demo-2026/"
    "HealthIA-ONE-Autonomous-Taskmaster-Charon-ONE-SAFETY.mp4"
)
HISTORICAL_ONE_SAFETY_SHA = "2c82929888c613960cb44ba7cb0c111b22e8a205cf38643d3199f3a1c5e542cf"
ARCHIVED_WEBM_SHA = "cfd91b0d08cf6659e1fb924c2e85071cd3b79bd414578b7112908c46f91adb19"


def test_current_judge_entry_is_separate_from_historical_byte_proof() -> None:
    proof = json.loads(
        (ROOT / "hackathon/evidence/public_judge_video_proof.json").read_text(encoding="utf-8")
    )
    assert proof["status"] == "CURRENT_JUDGE_ENTRY_WITH_HISTORICAL_BYTE_PROOF"
    assert proof["synthetic_only"] is True

    current = proof["current_judge_submission"]
    assert current["youtube_url"] == CURRENT_VIDEO_URL
    assert current["label"] == "V5"
    assert current["current_judge_entry_point"] is True
    assert current["byte_identity_proven_by_this_file"] is False

    historical = proof["canonical_submission"]
    assert historical["backward_compatibility_name"] is True
    assert historical["current_submission"] is False
    assert historical["historical_proof_lineage"] is True
    assert historical["release_url"] == HISTORICAL_ONE_SAFETY_URL
    assert historical["enhanced_master_sha256"] == HISTORICAL_ONE_SAFETY_SHA

    archived = proof["historical_public_video"]
    assert archived["archived"] is True
    assert archived["not_for_submission"] is True
    assert archived["video_sha256"] == ARCHIVED_WEBM_SHA
    assert archived["historical_anonymous_download_verified"] is True


def test_final_submission_documents_use_current_v5_url() -> None:
    for relative in (
        "README.md",
        "JUDGES_START_HERE.md",
        "docs/DEVPOST_SUBMISSION.md",
        "docs/DEMO_SCRIPT.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert CURRENT_VIDEO_URL in text, relative
        assert "99/100" not in text, relative


def test_current_docs_do_not_promote_historical_master_as_submission() -> None:
    for relative in ("README.md", "JUDGES_START_HERE.md", "docs/DEVPOST_SUBMISSION.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        lowered = text.lower()
        assert "v5" in lowered, relative
        assert "historical proof lineage" in lowered, relative


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
