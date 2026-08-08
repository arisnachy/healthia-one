from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VIDEO_SHA = "cfd91b0d08cf6659e1fb924c2e85071cd3b79bd414578b7112908c46f91adb19"
PUBLIC_VIDEO_URL = (
    "https://github.com/arisnachy/healthia-one/releases/download/"
    "healthia-one-hackathon-judge-demo-2026/HealthIA-ONE-final-judge-demo.webm"
)


def test_public_judge_video_proof_is_locked_to_exact_verified_bytes() -> None:
    proof = json.loads(
        (ROOT / "hackathon/evidence/public_judge_video_proof.json").read_text(encoding="utf-8")
    )
    assert proof["status"] == "PASS"
    assert proof["synthetic_only"] is True
    assert proof["public_url"] == PUBLIC_VIDEO_URL
    assert proof["video_sha256"] == EXPECTED_VIDEO_SHA
    assert proof["release_publication_proof"]["anonymous_download_verified"] is True
    assert proof["release_publication_proof"]["anonymous_download_sha256_match"] is True
    assert proof["independent_public_probe"]["authentication_required"] is False
    assert proof["independent_public_probe"]["full_video_sha256_match"] is True


def test_final_submission_documents_use_the_proven_public_video_url() -> None:
    for relative in ("README.md", "docs/DEVPOST_SUBMISSION.md", "docs/DEMO_SCRIPT.md", "docs/EVIDENCE.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert PUBLIC_VIDEO_URL in text, relative
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
