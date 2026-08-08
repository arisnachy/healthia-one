from __future__ import annotations

from pathlib import Path

import pytest

from healthia_one.blob_store import GcsResultBlobStore, LocalResultBlobStore, build_result_blob_store, result_object_key
from healthia_one.config import Settings


class FakeBlob:
    def __init__(self, key: str, objects: dict[str, tuple[bytes, str]]) -> None:
        self.key = key
        self.objects = objects

    def upload_from_string(self, content: bytes, content_type: str = "application/octet-stream") -> None:
        self.objects[self.key] = (bytes(content), content_type)

    def download_as_bytes(self) -> bytes:
        if self.key not in self.objects:
            error = RuntimeError("missing")
            error.code = 404  # type: ignore[attr-defined]
            raise error
        return self.objects[self.key][0]


class FakeBucket:
    def __init__(self, objects: dict[str, tuple[bytes, str]]) -> None:
        self.objects = objects

    def blob(self, key: str) -> FakeBlob:
        return FakeBlob(key, self.objects)


class FakeStorageClient:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.bucket_names: list[str] = []

    def bucket(self, name: str) -> FakeBucket:
        self.bucket_names.append(name)
        return FakeBucket(self.objects)


@pytest.mark.asyncio
async def test_local_result_blob_round_trip_is_exact_and_tenant_scoped(tmp_path: Path) -> None:
    store = LocalResultBlobStore(tmp_path)
    payload = b"exact-private-clinical-bytes"
    uri = await store.put_result(
        patient_id="uid_alpha",
        result_id="result_123",
        filename="CT Chest.PNG",
        content=payload,
        mime_type="image/png",
    )
    assert uri.startswith("local://uploads/results/uid_alpha/result_123.png")
    assert await store.get_result(patient_id="uid_alpha", result_id="result_123", filename="CT Chest.PNG") == payload
    with pytest.raises(FileNotFoundError):
        await store.get_result(patient_id="uid_beta", result_id="result_123", filename="CT Chest.PNG")


def test_gcs_object_key_cannot_escape_patient_namespace() -> None:
    key = result_object_key("../../uid/alpha", "../result/123", "../../scan.PDF")
    assert key.startswith("patients/")
    assert ".." not in key.split("/")
    assert key.endswith(".pdf")
    assert "/results/" in key


@pytest.mark.asyncio
async def test_gcs_result_blob_round_trip_uses_private_uid_derived_object_key() -> None:
    client = FakeStorageClient()
    store = GcsResultBlobStore("healthia-private-results", client)
    payload = b"ecg-image-bytes"
    uri = await store.put_result(
        patient_id="firebase_uid_123",
        result_id="result_ecg",
        filename="ECG.png",
        content=payload,
        mime_type="image/png",
    )
    expected_key = "patients/firebase_uid_123/results/result_ecg/result_ecg.png"
    assert uri == f"gs://healthia-private-results/{expected_key}"
    assert client.objects[expected_key] == (payload, "image/png")
    assert await store.get_result(patient_id="firebase_uid_123", result_id="result_ecg", filename="ECG.png") == payload
    with pytest.raises(FileNotFoundError):
        await store.get_result(patient_id="other_uid", result_id="result_ecg", filename="ECG.png")


def test_blob_store_factory_requires_bucket_for_gcs(tmp_path: Path) -> None:
    local = build_result_blob_store(Settings(blob_backend="local"), tmp_path)
    assert isinstance(local, LocalResultBlobStore)
    with pytest.raises(ValueError):
        build_result_blob_store(Settings(blob_backend="gcs", result_bucket=""), tmp_path)
