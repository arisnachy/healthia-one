from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from scripts.extract_firebase_android_config import (
    FirebaseConfigError,
    decode_payload,
    extract_android_values,
    main,
)


SYNTHETIC_KEY = "SYNTHETIC_FIREBASE_KEY_1234567890"


def synthetic_config(*, package: str = "com.healthia.one.bridge", project: str = "healthia-6088a") -> dict:
    return {
        "project_info": {
            "project_number": "123456789012",
            "project_id": project,
        },
        "client": [
            {
                "client_info": {
                    "mobilesdk_app_id": "1:123456789012:android:abcDEF123456",
                    "android_client_info": {"package_name": package},
                },
                "api_key": [{"current_key": SYNTHETIC_KEY}],
            }
        ],
    }


def test_base64_config_extracts_only_controlled_android_values() -> None:
    encoded = base64.b64encode(json.dumps(synthetic_config()).encode()).decode()
    parsed = decode_payload(encoded, payload_format="base64")
    values = extract_android_values(
        parsed,
        package_name="com.healthia.one.bridge",
        project_id="healthia-6088a",
    )

    assert values == {
        "HEALTHIA_FIREBASE_APP_ID": "1:123456789012:android:abcDEF123456",
        "HEALTHIA_FIREBASE_API_KEY": SYNTHETIC_KEY,
        "HEALTHIA_FIREBASE_PROJECT_ID": "healthia-6088a",
        "HEALTHIA_FIREBASE_SENDER_ID": "123456789012",
    }


def test_config_rejects_wrong_package_or_project() -> None:
    with pytest.raises(FirebaseConfigError):
        extract_android_values(
            synthetic_config(package="com.attacker.other"),
            package_name="com.healthia.one.bridge",
            project_id="healthia-6088a",
        )

    with pytest.raises(FirebaseConfigError):
        extract_android_values(
            synthetic_config(project="other-project"),
            package_name="com.healthia.one.bridge",
            project_id="healthia-6088a",
        )


def test_config_rejects_duplicate_matching_clients() -> None:
    config = synthetic_config()
    config["client"].append(dict(config["client"][0]))

    with pytest.raises(FirebaseConfigError):
        extract_android_values(
            config,
            package_name="com.healthia.one.bridge",
            project_id="healthia-6088a",
        )


def test_cli_writes_env_file_but_never_prints_values(tmp_path: Path, monkeypatch, capsys) -> None:
    encoded = base64.b64encode(json.dumps(synthetic_config()).encode()).decode()
    output = tmp_path / "firebase.env"
    monkeypatch.setattr("sys.stdin.read", lambda: encoded)

    code = main(
        [
            "--format",
            "base64",
            "--package",
            "com.healthia.one.bridge",
            "--project",
            "healthia-6088a",
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "values were not printed" in captured.out
    assert SYNTHETIC_KEY not in captured.out + captured.err
    assert "1:123456789012:android" not in captured.out + captured.err
    text = output.read_text(encoding="utf-8")
    assert "HEALTHIA_FIREBASE_PROJECT_ID=healthia-6088a" in text
    assert "HEALTHIA_FIREBASE_SENDER_ID=123456789012" in text
