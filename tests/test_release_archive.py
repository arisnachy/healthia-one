import json
from zipfile import ZipFile

from scripts.build_release_zip import build


def test_release_archive_contains_manifest_and_excludes_runtime_data(tmp_path):
    output = tmp_path / "HealthIA-ONE-release-candidate.zip"
    archive_path, file_count = build(output, "test-commit")
    assert archive_path == output
    assert file_count > 40

    with ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "healthia-one/README.md" in names
        assert "healthia-one/app/main.py" in names
        assert "healthia-one/web/ui-v5.js" in names
        assert "healthia-one/scripts/smoke_test.py" in names
        assert "healthia-one/RELEASE-MANIFEST.json" in names
        assert not any("/.git/" in name or "/.venv/" in name for name in names)
        assert not any(name.startswith("healthia-one/uploads/") and not name.endswith(".gitkeep") for name in names)
        manifest = json.loads(archive.read("healthia-one/RELEASE-MANIFEST.json"))
        assert manifest["source_ref"] == "test-commit"
        assert manifest["synthetic_demo_only"] is True
