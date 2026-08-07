from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_no_one_shot_kira_migration_workflows_remain() -> None:
    workflows = ROOT / ".github" / "workflows"
    forbidden = {
        "kira-natural-chat-migration.yml",
        "kira-remove-seed-chat.yml",
    }
    present = {path.name for path in workflows.glob("kira-*.yml")}
    assert not (present & forbidden), f"temporary migration workflows remain: {sorted(present & forbidden)}"
