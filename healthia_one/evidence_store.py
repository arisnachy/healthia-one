from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

from healthia_one.models import ClinicalDocument


class EvidenceStoreError(RuntimeError):
    pass


def configured_bucket() -> str:
    return os.getenv("HEALTHIA_GCS_BUCKET", "").strip()


def evidence_backend() -> str:
    return "gcs" if configured_bucket() else "local"


def _object_name(document: ClinicalDocument) -> str:
    return f"patients/{document.patient_id}/documents/{document.id}/{Path(document.filename).name}"


def _parse_gs_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.strip("/"):
        raise EvidenceStoreError("Ruta de Cloud Storage inválida.")
    return parsed.netloc, parsed.path.lstrip("/")


def _safe_local_path(root: Path, storage_path: str) -> Path:
    root = root.resolve()
    path = (root / storage_path).resolve()
    if root != path and root not in path.parents:
        raise EvidenceStoreError("La ruta de evidencia salió del directorio autorizado.")
    return path


async def persist_evidence(document: ClinicalDocument, content: bytes, root: Path) -> ClinicalDocument:
    """Persist original bytes before any AI interpretation.

    In Cloud, evidence is stored in GCS and the durable `gs://` URI is saved in the
    clinical document. Locally the existing patient-scoped path is preserved.
    """

    bucket_name = configured_bucket()
    if not bucket_name:
        path = _safe_local_path(root, document.storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
        return document

    object_name = _object_name(document)

    def upload() -> None:
        from google.cloud import storage

        client = storage.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.metadata = {
            "healthia_document_id": document.id,
            "healthia_patient_id": document.patient_id,
            "healthia_original_filename": document.filename,
        }
        blob.upload_from_string(content, content_type=document.mime_type or "application/octet-stream")

    await asyncio.to_thread(upload)
    document.storage_path = f"gs://{bucket_name}/{object_name}"
    return document


async def load_evidence(document: ClinicalDocument, root: Path) -> bytes:
    if document.storage_path.startswith("gs://"):
        bucket_name, object_name = _parse_gs_uri(document.storage_path)

        def download() -> bytes:
            from google.cloud import storage

            client = storage.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
            return client.bucket(bucket_name).blob(object_name).download_as_bytes()

        return await asyncio.to_thread(download)

    path = _safe_local_path(root, document.storage_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(document.storage_path)
    return await asyncio.to_thread(path.read_bytes)


def local_evidence_path(document: ClinicalDocument, root: Path) -> Path | None:
    if document.storage_path.startswith("gs://"):
        return None
    path = _safe_local_path(root, document.storage_path)
    return path if path.exists() and path.is_file() else None
