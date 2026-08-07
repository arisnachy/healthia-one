from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


class CloudProofError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudProofConfig:
    base_url: str
    project_id: str
    bucket_name: str
    identity_token: str = ""
    timeout: int = 45


def _request(config: CloudProofConfig, method: str, path: str, body: bytes | None = None, content_type: str | None = None) -> tuple[int, bytes, dict[str, str]]:
    url = f"{config.base_url.rstrip('/')}{path}"
    headers = {"Accept": "application/json"}
    if config.identity_token:
        headers["Authorization"] = f"Bearer {config.identity_token}"
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise CloudProofError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise CloudProofError(f"{method} {path} failed: {type(exc).__name__}: {exc}") from exc


def _json(config: CloudProofConfig, method: str, path: str, body: bytes | None = None, content_type: str | None = None) -> dict[str, Any]:
    status, raw, _ = _request(config, method, path, body, content_type)
    if status < 200 or status >= 300:
        raise CloudProofError(f"{method} {path} returned status {status}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CloudProofError(f"{method} {path} did not return JSON") from exc
    if not isinstance(payload, dict):
        raise CloudProofError(f"{method} {path} returned non-object JSON")
    return payload


def _post_json(config: CloudProofConfig, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _json(
        config,
        "POST",
        path,
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        "application/json",
    )


def _multipart_file(field: str, filename: str, mime_type: str, content: bytes) -> tuple[bytes, str]:
    boundary = f"healthia-proof-{uuid.uuid4().hex}"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + content + tail, f"multipart/form-data; boundary={boundary}"


def _minimal_pdf() -> bytes:
    """Create a tiny synthetic text PDF without external dependencies."""
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>")
    stream = (
        b"BT /F1 16 Tf 72 720 Td (SYNTHETIC LAB RESULT - HEALTHIA CLOUD PROOF) Tj "
        b"0 -28 Td (Glucose: 104 mg/dL - reference 70-99 - HIGH) Tj "
        b"0 -28 Td (Hemoglobin: 14.2 g/dL - reference 12.0-16.0) Tj ET"
    )
    objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def verify_firestore_and_gcs(config: CloudProofConfig, result_id: str, document_id: str) -> dict[str, Any]:
    try:
        from google.cloud import firestore, storage
    except Exception as exc:
        raise CloudProofError("google-cloud-firestore and google-cloud-storage must be installed") from exc

    firestore_client = firestore.Client(project=config.project_id)
    snapshot = firestore_client.collection("healthia_one_patients").document("patient_demo").get()
    if not snapshot.exists:
        raise CloudProofError("Firestore patient_demo document does not exist after Cloud Run write")
    state = snapshot.to_dict() or {}
    result = next((item for item in state.get("results", []) if item.get("id") == result_id), None)
    document = next((item for item in state.get("documents", []) if item.get("id") == document_id), None)
    adk_audit = next(
        (
            item for item in reversed(state.get("audit_events", []))
            if item.get("actor") == "google_adk" and item.get("action") == "execute_demand_driven_clinical_plan"
        ),
        None,
    )
    if result is None or document is None:
        raise CloudProofError("Firestore does not contain the uploaded result/document IDs")
    if adk_audit is None:
        raise CloudProofError("Firestore does not contain Google ADK execution audit evidence")
    storage_path = str(document.get("storage_path") or "")
    expected_prefix = f"gs://{config.bucket_name}/"
    if not storage_path.startswith(expected_prefix):
        raise CloudProofError(f"Document evidence is not in configured GCS bucket: {storage_path}")
    object_name = storage_path[len(expected_prefix):]
    blob = storage.Client(project=config.project_id).bucket(config.bucket_name).blob(object_name)
    if not blob.exists():
        raise CloudProofError(f"GCS object does not exist: {object_name}")
    blob.reload()
    return {
        "firestore_document": snapshot.reference.path,
        "firestore_update_time": snapshot.update_time.isoformat() if snapshot.update_time else None,
        "adk_audit_resource_id": adk_audit.get("resource_id"),
        "adk_executed_roles": (adk_audit.get("details") or {}).get("executed_roles", []),
        "gcs_uri": storage_path,
        "gcs_generation": str(blob.generation or ""),
        "gcs_size": int(blob.size or 0),
    }


def run(config: CloudProofConfig) -> dict[str, Any]:
    health = _json(config, "GET", "/healthz")
    if health.get("status") != "ok":
        raise CloudProofError(f"Cloud Run health check failed: {health}")

    readiness = _json(config, "GET", "/api/readiness")
    expected = {
        "llm_backend": "gemini_api",
        "store_backend": "firestore",
        "evidence_backend": "gcs",
        "agent_execution": "demand_driven",
    }
    for key, value in expected.items():
        if readiness.get(key) != value:
            raise CloudProofError(f"Readiness mismatch {key}: expected {value!r}, found {readiness.get(key)!r}")
    if not readiness.get("adk_ready") or not readiness.get("ai_ready"):
        raise CloudProofError("Cloud runtime does not report real Google AI readiness")

    reset = _json(config, "POST", "/api/demo/reset", body=b"")
    if not reset.get("reset"):
        raise CloudProofError("Synthetic cloud patient reset failed")

    ai_probe = _json(config, "POST", "/api/ai/test", body=b"")
    if not (ai_probe.get("ok") and ai_probe.get("status") == "ready" and ai_probe.get("live_request")):
        raise CloudProofError(f"Real Gemini probe failed: {ai_probe}")

    clinical = _post_json(
        config,
        "/api/chat",
        {"message": "Desde ayer tengo fiebre, dolor de garganta y náuseas; quiero hacer una consulta."},
    )
    clinical_message = clinical.get("message") or {}
    clinical_metadata = clinical_message.get("metadata") or {}
    interview = clinical_metadata.get("clinical_interview") or {}
    if clinical_metadata.get("llm_status") != "dynamic_clinical_questions":
        raise CloudProofError(f"Clinical runtime did not produce dynamic Gemini questions: {clinical_metadata}")
    if interview.get("question_source") != "gemini_dynamic":
        raise CloudProofError(f"Clinical question block is not Gemini dynamic: {interview}")
    questions = (interview.get("question_block") or {}).get("questions") or []
    if len(questions) != 5:
        raise CloudProofError(f"Clinical runtime did not produce exactly five adaptive questions: {questions}")

    audit_payload = _json(config, "GET", "/api/audit?limit=100")
    adk_events = [
        item for item in audit_payload.get("events", [])
        if item.get("actor") == "google_adk" and item.get("action") == "execute_demand_driven_clinical_plan"
    ]
    if not adk_events:
        raise CloudProofError("Visible clinical request has no Google ADK execution audit")
    latest_adk = adk_events[0]
    executed_roles = (latest_adk.get("details") or {}).get("executed_roles") or []
    if "interview" not in executed_roles or "safety" not in executed_roles or len(executed_roles) > 4:
        raise CloudProofError(f"Google ADK tool trajectory violated the minimum-tool contract: {executed_roles}")

    pairing = _json(config, "POST", "/api/devices/pairing", body=b"")
    code = str(pairing.get("code") or "")
    if not code:
        raise CloudProofError("Device pairing did not return a code")
    claim = _post_json(
        config,
        "/api/devices/pairing/claim",
        {"code": code, "device_id": "cloud-proof-phone", "display_name": "Synthetic Cloud Proof Phone"},
    )
    if claim.get("credential_persistence") != "restart_safe":
        raise CloudProofError(f"Device credential is not restart-safe in Cloud: {claim}")
    if claim.get("patient_id") != "patient_demo" or not claim.get("connection_id") or not claim.get("access_token"):
        raise CloudProofError(f"Device credential did not bind patient/connection identity: {claim}")

    pdf = _minimal_pdf()
    multipart, content_type = _multipart_file("file", "synthetic_lab_cloud_proof.pdf", "application/pdf", pdf)
    uploaded = _json(config, "POST", "/api/results/upload", multipart, content_type)
    if uploaded.get("status") != "parsed":
        raise CloudProofError(f"Gemini multimodal result was not parsed: {uploaded}")
    if uploaded.get("evidence_backend") != "gcs" or not uploaded.get("original_available") or not uploaded.get("twin_updated"):
        raise CloudProofError(f"Upload did not prove durable evidence/twin linkage: {uploaded}")
    result_id = str(uploaded.get("id") or "")
    document_id = str(uploaded.get("document_id") or "")
    if not result_id or not document_id:
        raise CloudProofError("Upload omitted result/document identity")

    twin = _json(config, "GET", "/api/twin")
    node = next((item for item in twin.get("result_nodes", []) if item.get("result_id") == result_id), None)
    if node is None or node.get("document_id") != document_id:
        raise CloudProofError("Clinical twin does not link the uploaded result to its original evidence")

    status, downloaded, headers = _request(config, "GET", f"/api/documents/{document_id}/download")
    if status != 200 or downloaded != pdf:
        raise CloudProofError("Original evidence did not round-trip byte-for-byte through Cloud Run/GCS")

    persistence = verify_firestore_and_gcs(config, result_id, document_id)
    return {
        "ok": True,
        "cloud_run_url": config.base_url,
        "project_id": config.project_id,
        "model": ai_probe.get("model"),
        "gemini_request_number": ai_probe.get("request_number"),
        "adk_session_id": latest_adk.get("resource_id"),
        "adk_executed_roles": executed_roles,
        "device_connection_id": claim.get("connection_id"),
        "device_credential_persistence": claim.get("credential_persistence"),
        "multimodal_result_id": result_id,
        "document_id": document_id,
        "download_content_type": headers.get("Content-Type", ""),
        "clinical_twin_linked": True,
        "firestore": persistence,
        "proof": [
            "cloud_run_health",
            "firestore_active_store",
            "gcs_original_evidence",
            "live_gemini_interactions_call",
            "google_adk_runner_tool_trajectory",
            "five_dynamic_clinical_questions",
            "restart_safe_device_identity",
            "gemini_multimodal_pdf_extraction",
            "clinical_twin_provenance",
            "original_evidence_roundtrip",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strict HealthIA ONE Google Cloud proof gate")
    parser.add_argument("--url", default=os.getenv("HEALTHIA_CLOUD_URL", ""))
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument("--bucket", default=os.getenv("HEALTHIA_GCS_BUCKET", ""))
    parser.add_argument("--identity-token", default=os.getenv("HEALTHIA_CLOUD_ID_TOKEN", ""))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing = [name for name, value in (("url", args.url), ("project", args.project), ("bucket", args.bucket)) if not value]
    if missing:
        print(f"HEALTHIA_CLOUD_PROOF_BLOCKED missing={','.join(missing)}", file=sys.stderr)
        return 2
    config = CloudProofConfig(
        base_url=args.url,
        project_id=args.project,
        bucket_name=args.bucket,
        identity_token=args.identity_token,
    )
    try:
        result = run(config)
    except CloudProofError as exc:
        print(f"HEALTHIA_CLOUD_PROOF_FAILED {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("HEALTHIA_CLOUD_PROOF_OK " + " ".join(result["proof"]))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
