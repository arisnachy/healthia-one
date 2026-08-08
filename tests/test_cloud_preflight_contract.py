from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cloud_preflight_checks_the_real_hackathon_runtime_without_spend_actions() -> None:
    script = (ROOT / "deployment/preflight-cloud-proof.ps1").read_text(encoding="utf-8")
    assert '"billing", "projects", "describe"' in script
    assert '"run", "services", "describe"' in script
    assert '"firestore", "databases", "describe"' in script
    assert '"pubsub", "topics", "describe"' in script
    assert '"pubsub", "subscriptions", "describe"' in script
    assert "HEALTHIA_PROACTIVE_ENABLED" in script
    assert "HEALTHIA_EVENT_DISPATCH_BACKEND" in script
    assert "HEALTHIA_STORE_BACKEND" in script
    assert "HEALTHIA_BLOB_BACKEND" in script
    assert "HEALTHIA_RESULT_BUCKET" in script
    assert "identity_platform" in script
    assert "publicAccessPrevention" in script
    assert "uniformBucketLevelAccess" in script
    assert "allUsers" in script and "allAuthenticatedUsers" in script
    assert "scheduler_paused" in script
    assert "capture-cloud-proof.ps1" in script

    forbidden_mutations = (
        '"run", "deploy"',
        '"storage", "buckets", "create"',
        '"pubsub", "topics", "create"',
        '"firestore", "databases", "create"',
        '"scheduler", "jobs", "create"',
        '"projects", "add-iam-policy-binding"',
    )
    for token in forbidden_mutations:
        assert token not in script
