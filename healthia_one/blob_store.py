from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Protocol

from healthia_one.config import Settings
from healthia_one.result_intelligence import result_storage_path


class ResultBlobStore(Protocol):
    async def put_result(
        self,
        *,
        patient_id: str,
        result_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> str: ...

    async def get_result(
        self,
        *,
        patient_id: str,
        result_id: str,
        filename: str,
    ) -> bytes: ...


def _safe_segment(value: str, *, fallback: str, limit: int = 180) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or ""))[:limit].strip("._")
    return cleaned or fallback


def result_object_key(patient_id: str, result_id: str, filename: str) -> str:
    patient = _safe_segment(patient_id, fallback="patient")
    result = _safe_segment(result_id, fallback="result")
    suffix = Path(filename).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        suffix = ".bin"
    return f"patients/{patient}/results/{result}/{result}{suffix}"


class LocalResultBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, patient_id: str, result_id: str, filename: str) -> Path:
        path = (self.root / result_storage_path(patient_id, result_id, filename)).resolve()
        if self.root not in path.parents:
            raise ValueError("Result blob path escaped the application root")
        return path

    async def put_result(
        self,
        *,
        patient_id: str,
        result_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> str:
        path = self._path(patient_id, result_id, filename)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
        relative = path.relative_to(self.root).as_posix()
        return f"local://{relative}"

    async def get_result(self, *, patient_id: str, result_id: str, filename: str) -> bytes:
        path = self._path(patient_id, result_id, filename)
        if not path.exists():
            raise FileNotFoundError(path)
        return await asyncio.to_thread(path.read_bytes)


class GcsResultBlobStore:
    def __init__(self, bucket_name: str, client: Any | None = None) -> None:
        if not bucket_name.strip():
            raise ValueError("HEALTHIA_RESULT_BUCKET is required when blob_backend=gcs")
        self.bucket_name = bucket_name.strip()
        self._client = client

    def _get_client(self):
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client

    def _blob(self, patient_id: str, result_id: str, filename: str):
        key = result_object_key(patient_id, result_id, filename)
        bucket = self._get_client().bucket(self.bucket_name)
        return key, bucket.blob(key)

    async def put_result(
        self,
        *,
        patient_id: str,
        result_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> str:
        key, blob = self._blob(patient_id, result_id, filename)
        await asyncio.to_thread(blob.upload_from_string, content, content_type=mime_type)
        return f"gs://{self.bucket_name}/{key}"

    async def get_result(self, *, patient_id: str, result_id: str, filename: str) -> bytes:
        _, blob = self._blob(patient_id, result_id, filename)
        try:
            return await asyncio.to_thread(blob.download_as_bytes)
        except Exception as exc:
            # Keep Cloud provider details out of the patient-facing endpoint while
            # normalizing a missing private object to the same contract as local.
            if type(exc).__name__ == "NotFound" or getattr(exc, "code", None) == 404:
                raise FileNotFoundError(filename) from exc
            raise


def build_result_blob_store(settings: Settings, root: Path) -> ResultBlobStore:
    backend = settings.blob_backend.strip().lower()
    if backend == "gcs":
        return GcsResultBlobStore(settings.result_bucket)
    if backend == "local":
        return LocalResultBlobStore(root)
    raise ValueError(f"Unsupported result blob backend: {settings.blob_backend}")
