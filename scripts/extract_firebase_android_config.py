from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_ENV_NAMES = (
    "HEALTHIA_FIREBASE_APP_ID",
    "HEALTHIA_FIREBASE_API_KEY",
    "HEALTHIA_FIREBASE_PROJECT_ID",
    "HEALTHIA_FIREBASE_SENDER_ID",
)


class FirebaseConfigError(ValueError):
    """Raised when Firebase Android client configuration is not mission-safe."""


def decode_payload(payload: str, *, payload_format: str) -> dict[str, Any]:
    raw_payload = str(payload or "").strip()
    if not raw_payload:
        raise FirebaseConfigError("Firebase Android configuration is empty")
    try:
        if payload_format == "base64":
            decoded = base64.b64decode(raw_payload, validate=True).decode("utf-8")
        elif payload_format == "json":
            decoded = raw_payload
        else:
            raise FirebaseConfigError("Unsupported Firebase Android configuration format")
        parsed = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FirebaseConfigError("Firebase Android configuration could not be decoded") from exc
    if not isinstance(parsed, dict):
        raise FirebaseConfigError("Firebase Android configuration root must be an object")
    return parsed


def extract_android_values(
    config: dict[str, Any],
    *,
    package_name: str,
    project_id: str,
) -> dict[str, str]:
    project = config.get("project_info") or {}
    if not isinstance(project, dict):
        raise FirebaseConfigError("Firebase project_info is invalid")

    clients = config.get("client") or []
    if not isinstance(clients, list):
        raise FirebaseConfigError("Firebase client list is invalid")

    matches: list[dict[str, Any]] = []
    for candidate in clients:
        if not isinstance(candidate, dict):
            continue
        client_info = candidate.get("client_info") or {}
        android_info = client_info.get("android_client_info") or {} if isinstance(client_info, dict) else {}
        if isinstance(android_info, dict) and str(android_info.get("package_name") or "") == package_name:
            matches.append(candidate)

    if len(matches) != 1:
        raise FirebaseConfigError("Firebase config must contain exactly one matching Android client")

    client = matches[0]
    client_info = client.get("client_info") or {}
    keys = client.get("api_key") or []
    first_key = keys[0] if isinstance(keys, list) and keys and isinstance(keys[0], dict) else {}

    values = {
        "HEALTHIA_FIREBASE_APP_ID": str(client_info.get("mobilesdk_app_id") or "").strip()
        if isinstance(client_info, dict)
        else "",
        "HEALTHIA_FIREBASE_API_KEY": str(first_key.get("current_key") or "").strip(),
        "HEALTHIA_FIREBASE_PROJECT_ID": str(project.get("project_id") or "").strip(),
        "HEALTHIA_FIREBASE_SENDER_ID": str(project.get("project_number") or "").strip(),
    }

    if values["HEALTHIA_FIREBASE_PROJECT_ID"] != project_id:
        raise FirebaseConfigError("Firebase project id does not match the controlled HealthIA project")
    if not re.fullmatch(r"1:[0-9]+:android:[0-9A-Za-z]+", values["HEALTHIA_FIREBASE_APP_ID"]):
        raise FirebaseConfigError("Firebase Android app id failed shape validation")
    if len(values["HEALTHIA_FIREBASE_API_KEY"]) < 20:
        raise FirebaseConfigError("Firebase API key failed shape validation")
    if not values["HEALTHIA_FIREBASE_SENDER_ID"].isdigit():
        raise FirebaseConfigError("Firebase sender id failed shape validation")
    if any(not values[name] for name in REQUIRED_ENV_NAMES):
        raise FirebaseConfigError("Firebase Android config is missing a required value")

    return values


def write_env_file(values: dict[str, str], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(f"{name}={values[name]}\n" for name in REQUIRED_ENV_NAMES),
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract controlled HealthIA Firebase Android build values")
    parser.add_argument("--format", choices=("base64", "json"), required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = sys.stdin.read()
    try:
        config = decode_payload(payload, payload_format=args.format)
        values = extract_android_values(config, package_name=args.package, project_id=args.project)
        write_env_file(values, args.output)
    except FirebaseConfigError as exc:
        print(f"Firebase Android configuration rejected: {exc}", file=sys.stderr)
        return 2
    print("Firebase Android configuration accepted; values were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
