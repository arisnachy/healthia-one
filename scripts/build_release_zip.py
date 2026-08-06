from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".healthia-one",
    "__pycache__",
    "htmlcov",
    "node_modules",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}


def should_include(path: Path, output: Path) -> bool:
    relative = path.relative_to(ROOT)
    if path.resolve() == output.resolve():
        return False
    if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if relative.name == ".env" or relative.name.startswith(".env.") and relative.name != ".env.example":
        return False
    if relative.parts and relative.parts[0] == "uploads" and relative.name != ".gitkeep":
        return False
    return path.is_file()


def write_bytes(archive: ZipFile, archive_name: str, content: bytes) -> None:
    info = ZipInfo(archive_name, date_time=FIXED_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, content)


def build(output: Path, source_ref: str) -> tuple[Path, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(
        (path for path in ROOT.rglob("*") if should_include(path, output)),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    prefix = "healthia-one"
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            write_bytes(archive, f"{prefix}/{relative}", path.read_bytes())
        manifest = {
            "project": "HealthIA ONE",
            "source_ref": source_ref,
            "file_count": len(files),
            "synthetic_demo_only": True,
            "truth_boundary": (
                "Tested hackathon release candidate; not a production clinical system, medical device, "
                "clinical-effectiveness claim, or regulatory clearance."
            ),
        }
        write_bytes(
            archive,
            f"{prefix}/RELEASE-MANIFEST.json",
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n",
        )
    return output, len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deterministic HealthIA ONE release archive.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "HealthIA-ONE-release-candidate.zip",
    )
    parser.add_argument(
        "--source-ref",
        default=os.getenv("GITHUB_SHA", "local-working-tree"),
    )
    args = parser.parse_args()
    output, count = build(args.output.resolve(), args.source_ref)
    print(f"Built {output} with {count} source files")


if __name__ == "__main__":
    main()
