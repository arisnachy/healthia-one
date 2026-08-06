from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile


def verify(path: Path, expected_ref: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"Release archive not found: {path}")
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        required = {
            "healthia-one/README.md",
            "healthia-one/app/main.py",
            "healthia-one/healthia_one/models.py",
            "healthia-one/healthia_agent/agent.py",
            "healthia-one/web/privacy-controls.js",
            "healthia-one/web/profile-devices.js",
            "healthia-one/web/icons.js",
            "healthia-one/scripts/smoke_test.py",
            "healthia-one/RELEASE-MANIFEST.json",
        }
        missing = sorted(required - names)
        if missing:
            raise RuntimeError(f"Release archive is missing: {missing}")
        if any("/.git/" in name or "/.venv/" in name for name in names):
            raise RuntimeError("Release archive contains Git or virtual-environment data")
        if any(name.startswith("healthia-one/uploads/") and not name.endswith(".gitkeep") for name in names):
            raise RuntimeError("Release archive contains generated patient upload data")
        if any(name.endswith("/.env") or "/.healthia-one/" in name for name in names):
            raise RuntimeError("Release archive contains local secrets or patient state")
        manifest = json.loads(archive.read("healthia-one/RELEASE-MANIFEST.json"))
        if manifest.get("source_ref") != expected_ref:
            raise RuntimeError(
                f"Source ref mismatch: {manifest.get('source_ref')} != {expected_ref}"
            )
        if manifest.get("synthetic_demo_only") is not True:
            raise RuntimeError("Release manifest does not preserve the synthetic-demo boundary")
        if manifest.get("file_count", 0) < 40:
            raise RuntimeError("Release archive has an unexpectedly small source tree")
    print(f"Verified release archive: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a HealthIA ONE release archive.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--source-ref", required=True)
    args = parser.parse_args()
    verify(args.archive.resolve(), args.source_ref)


if __name__ == "__main__":
    main()
