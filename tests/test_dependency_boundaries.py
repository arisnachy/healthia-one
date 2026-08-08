from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def test_adk_core_is_used_without_unneeded_gcp_extra_bundle() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert '"google-adk>=2.5,<3"' in text
    assert "google-adk[gcp]" not in text


def test_cloud_state_clients_are_declared_explicitly() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert '"google-cloud-firestore>=2.21,<3"' in text
    assert '"google-cloud-storage>=3.3,<4"' in text
