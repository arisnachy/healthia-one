from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CRITICAL_SOURCE_FILES = {
    "Dockerfile",
    "app/main.py",
    "healthia_one/config.py",
    "healthia_one/living_system.py",
    "healthia_one/models.py",
    "healthia_one/service.py",
    "healthia_one/twin.py",
    "web/living.html",
    "web/living-system.css",
    "web/living-system.js",
}


class ProviderBindingError(RuntimeError):
    pass


def _command(*args: str) -> str:
    executable = args[0]
    if executable == "gcloud":
        executable = shutil.which("gcloud.cmd") or shutil.which("gcloud") or executable
    elif executable == "git":
        executable = shutil.which("git.exe") or shutil.which("git") or executable
    completed = subprocess.run(
        [executable, *args[1:]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        raise ProviderBindingError(f"{' '.join(args)} failed: {completed.stderr.strip()[:800]}")
    return completed.stdout.strip()


def _gcloud_json(*args: str) -> dict[str, Any]:
    payload = json.loads(_command("gcloud", *args, "--format=json") or "{}")
    if not isinstance(payload, dict):
        raise ProviderBindingError(f"gcloud {' '.join(args)} returned non-object JSON")
    return payload


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProviderBindingError(message)


def _service_env(service: dict[str, Any]) -> dict[str, str]:
    containers = (((service.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []
    env = containers[0].get("env") or [] if containers else []
    return {str(item.get("name")): str(item.get("value")) for item in env if "value" in item}


def _provider_source_matches_clean_head(source_uri: str, expected_sha: str) -> dict[str, Any]:
    head = _command("git", "rev-parse", "HEAD")
    _require(head == expected_sha, f"Local HEAD {head} does not match expected SHA {expected_sha}")
    _require(not _command("git", "status", "--porcelain"), "Local worktree is not clean")

    with tempfile.TemporaryDirectory(prefix="healthia-provider-source-") as temp_dir:
        archive = Path(temp_dir) / "provider-source.zip"
        _command("gcloud", "storage", "cp", source_uri, str(archive), "--quiet")
        archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        compared: dict[str, str] = {}
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                normalized = PurePosixPath(info.filename).as_posix()
                while normalized.startswith("./"):
                    normalized = normalized[2:]
                if normalized.startswith("../") or normalized.startswith("/"):
                    raise ProviderBindingError(f"Unsafe provider source member: {info.filename}")
                local = ROOT / Path(normalized)
                _require(local.is_file(), f"Provider source member is absent from clean HEAD checkout: {normalized}")
                provider_bytes = bundle.read(info)
                local_bytes = local.read_bytes()
                _require(provider_bytes == local_bytes, f"Provider source differs from clean HEAD: {normalized}")
                compared[normalized] = hashlib.sha256(provider_bytes).hexdigest()
        missing = sorted(CRITICAL_SOURCE_FILES.difference(compared))
        _require(not missing, f"Provider source omitted critical candidate files: {missing}")
        manifest_material = "\n".join(f"{name}\0{compared[name]}" for name in sorted(compared)).encode("utf-8")
        return {
            "provider_source_uri": source_uri,
            "provider_archive_sha256": archive_sha,
            "provider_content_manifest_sha256": hashlib.sha256(manifest_material).hexdigest(),
            "provider_file_count": len(compared),
            "critical_file_sha256": {name: compared[name] for name in sorted(CRITICAL_SOURCE_FILES)},
        }


def verify(
    *,
    project: str,
    region: str,
    service_name: str,
    expected_sha: str,
    identity_token: str = "",
) -> dict[str, Any]:
    service = _gcloud_json(
        "run",
        "services",
        "describe",
        service_name,
        "--project",
        project,
        "--region",
        region,
    )
    metadata = service.get("metadata") or {}
    annotations = metadata.get("annotations") or {}
    status = service.get("status") or {}
    template = (service.get("spec") or {}).get("template") or {}
    containers = (template.get("spec") or {}).get("containers") or []
    _require(containers, "Cloud Run service has no container")
    image = str(containers[0].get("image") or "")
    _require("@sha256:" in image, f"Cloud Run image is not digest pinned: {image}")
    image_digest = "sha256:" + image.rsplit("@sha256:", 1)[1]
    revision = str(status.get("latestReadyRevisionName") or "")
    build_id = str(annotations.get("run.googleapis.com/build-id") or "")
    source_uri = str(annotations.get("run.googleapis.com/build-source-location") or "")
    _require(revision and build_id and source_uri, "Cloud Run provider annotations omit revision/build/source")
    env = _service_env(service)
    _require(env.get("HEALTHIA_RELEASE_SHA") == expected_sha, "Cloud Run revision env is not bound to expected SHA")
    _require(env.get("HEALTHIA_AUTH_REQUIRED") == "true", "Cloud Run patient authentication is not enabled")
    _require(env.get("HEALTHIA_EVALUATION_ENABLED") == "true", "Cloud Run evaluator is not enabled")
    max_scale = str((template.get("metadata") or {}).get("annotations", {}).get("autoscaling.knative.dev/maxScale") or "")
    _require(max_scale == "1", f"Cloud Run max scale is not one: {max_scale}")

    build = _gcloud_json("builds", "describe", build_id, "--project", project, "--region", region)
    _require(build.get("status") == "SUCCESS", f"Cloud Build is not successful: {build.get('status')}")
    resolved = (build.get("sourceProvenance") or {}).get("resolvedStorageSource") or {}
    resolved_uri = f"gs://{resolved.get('bucket')}/{resolved.get('object')}#{resolved.get('generation')}"
    _require(resolved_uri == source_uri, "Cloud Run source annotation differs from Cloud Build provenance")
    build_digests = {
        str(item.get("digest") or "")
        for item in ((build.get("results") or {}).get("images") or [])
    }
    _require(image_digest in build_digests, "Cloud Run digest differs from Cloud Build result")

    artifact = _gcloud_json("artifacts", "docker", "images", "describe", image)
    artifact_version = str(artifact.get("version") or artifact.get("name") or "")
    _require(image_digest in artifact_version or artifact.get("image_summary", {}).get("digest") == image_digest, "Artifact Registry digest reread mismatch")

    url = str(status.get("url") or "").rstrip("/")
    _require(url, "Cloud Run provider did not return a service URL")
    request = urllib.request.Request(f"{url}/api/readiness")
    if identity_token:
        request.add_header("Authorization", f"Bearer {identity_token}")
    with urllib.request.urlopen(request, timeout=45) as response:
        readiness = json.loads(response.read().decode("utf-8"))
    _require(readiness.get("release_sha") == expected_sha, "Runtime readiness SHA differs from clean HEAD")

    source = _provider_source_matches_clean_head(source_uri, expected_sha)
    return {
        "ok": True,
        "expected_clean_head_sha": expected_sha,
        "cloud_run_service": service_name,
        "cloud_run_revision": revision,
        "cloud_run_url": url,
        "cloud_build_id": build_id,
        "cloud_build_status": build.get("status"),
        "artifact_image": image,
        "artifact_digest": image_digest,
        "runtime_release_sha": readiness.get("release_sha"),
        "max_scale": int(max_scale),
        "source": source,
        "proof": [
            "local_clean_head_matches_expected_sha",
            "provider_source_bytes_match_clean_head",
            "cloud_build_source_provenance_matches_cloud_run_annotation",
            "cloud_build_digest_matches_cloud_run_digest",
            "artifact_registry_digest_reread",
            "runtime_release_sha_matches_clean_head",
            "cloud_run_max_scale_one",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify HealthIA exact-SHA Cloud provider binding")
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--identity-token", default=os.getenv("HEALTHIA_CLOUD_ID_TOKEN", ""))
    parser.add_argument("--output", default="deployment/cloud-provider-binding-latest.json")
    args = parser.parse_args()
    try:
        result = verify(
            project=args.project,
            region=args.region,
            service_name=args.service,
            expected_sha=args.expected_sha,
            identity_token=args.identity_token,
        )
    except (ProviderBindingError, OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"HEALTHIA_PROVIDER_BINDING_FAILED {exc}", file=sys.stderr)
        return 3
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
