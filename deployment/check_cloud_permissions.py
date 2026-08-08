from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# This gate is deliberately non-mutating. It asks IAM for the permissions needed
# by BOTH phases of the judge-facing Cloud evidence path:
#   1) provision/deploy the bounded Cloud Run stack;
#   2) independently read back Firestore/GCS/Vertex/Cloud Run evidence.
REQUIRED_PERMISSIONS: tuple[str, ...] = (
    "serviceusage.services.enable",
    "serviceusage.services.use",
    "run.services.create",
    "run.services.update",
    "run.services.get",
    "run.routes.invoke",
    "iam.serviceAccounts.create",
    "iam.serviceAccounts.get",
    "iam.serviceAccounts.actAs",
    "resourcemanager.projects.setIamPolicy",
    "datastore.databases.create",
    "datastore.databases.get",
    "datastore.entities.get",
    "storage.buckets.create",
    "storage.buckets.get",
    "storage.objects.get",
    "secretmanager.secrets.create",
    "secretmanager.secrets.get",
    "cloudbuild.builds.create",
    "artifactregistry.repositories.create",
    "aiplatform.endpoints.predict",
)

ROLE_HINTS: dict[str, str] = {
    "serviceusage.services.enable": "roles/serviceusage.serviceUsageAdmin",
    "serviceusage.services.use": "roles/serviceusage.serviceUsageConsumer",
    "run.services.create": "roles/run.sourceDeveloper",
    "run.services.update": "roles/run.sourceDeveloper",
    "run.services.get": "roles/run.sourceDeveloper",
    "run.routes.invoke": "roles/run.sourceDeveloper",
    "iam.serviceAccounts.create": "roles/iam.serviceAccountAdmin",
    "iam.serviceAccounts.get": "roles/iam.serviceAccountAdmin",
    "iam.serviceAccounts.actAs": "roles/iam.serviceAccountUser",
    "resourcemanager.projects.setIamPolicy": "roles/resourcemanager.projectIamAdmin",
    "datastore.databases.create": "roles/datastore.owner",
    "datastore.databases.get": "roles/datastore.owner",
    "datastore.entities.get": "roles/datastore.viewer",
    "storage.buckets.create": "roles/storage.admin",
    "storage.buckets.get": "roles/storage.admin",
    "storage.objects.get": "roles/storage.objectViewer",
    "secretmanager.secrets.create": "roles/secretmanager.admin",
    "secretmanager.secrets.get": "roles/secretmanager.admin",
    "cloudbuild.builds.create": "roles/cloudbuild.builds.editor",
    "artifactregistry.repositories.create": "roles/artifactregistry.admin",
    "aiplatform.endpoints.predict": "roles/aiplatform.user",
}


def _principal(credentials: Any) -> str:
    for attr in ("service_account_email", "signer_email"):
        value = str(getattr(credentials, attr, "") or "").strip()
        if value:
            return value
    return "unknown"


def test_permissions(project: str) -> dict[str, Any]:
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("google-auth is required for the Cloud permission probe") from exc

    credentials, detected_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    principal = _principal(credentials)
    session = AuthorizedSession(credentials)
    endpoint = f"https://cloudresourcemanager.googleapis.com/v3/projects/{project}:testIamPermissions"
    response = session.post(
        endpoint,
        json={"permissions": list(REQUIRED_PERMISSIONS)},
        timeout=30,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(
            f"Cloud Resource Manager testIamPermissions failed: HTTP {response.status_code}: "
            f"{response.text[:600]}"
        )
    body = response.json()
    granted = sorted(set(body.get("permissions") or []))
    missing = [permission for permission in REQUIRED_PERMISSIONS if permission not in granted]
    role_hints = sorted({ROLE_HINTS[item] for item in missing if item in ROLE_HINTS})
    return {
        "status": "ready" if not missing else "blocked",
        "project": project,
        "principal": principal,
        "detected_adc_project": detected_project or "",
        "required_permission_count": len(REQUIRED_PERMISSIONS),
        "granted_permission_count": len(granted),
        "granted_permissions": granted,
        "missing_permissions": missing,
        "role_hints": role_hints,
        "mutation_performed": False,
        "proof_scope": "provision_and_independent_readback",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--json-out", default="deployment/cloud-permissions-latest.json")
    args = parser.parse_args()

    output = Path(args.json_out)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = test_permissions(args.project)
    except Exception as exc:
        payload = {
            "status": "error",
            "project": args.project,
            "mutation_performed": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"HEALTHIA_CLOUD_PERMISSION_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Authenticated principal: {payload['principal']}")
    if payload["status"] == "ready":
        print(
            "HEALTHIA_CLOUD_PERMISSIONS_READY "
            f"project={args.project} granted={payload['granted_permission_count']}"
        )
        return 0

    print(
        "HEALTHIA_CLOUD_PERMISSIONS_BLOCKED "
        f"project={args.project} missing={len(payload['missing_permissions'])}"
    )
    print("Missing permissions:")
    for permission in payload["missing_permissions"]:
        print(f"- {permission}")
    print("Suggested temporary provisioning/proof roles:")
    for role in payload["role_hints"]:
        print(f"- {role}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
