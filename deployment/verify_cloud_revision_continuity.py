from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deployment.verify_cloud_demo import (  # noqa: E402
    CloudProofConfig,
    CloudProofError,
    _json,
    _minimal_pdf,
    _multipart_file,
    _post_json,
    _register,
    _request,
)


DEFAULT_EVIDENCE = Path("deployment/cloud-revision-continuity-latest.json")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CloudProofError(message)


def _persistent_snapshot(
    config: CloudProofConfig,
    patient_id: str,
    result_id: str,
    document_id: str,
    mission_id: str,
) -> dict[str, Any]:
    try:
        from google.cloud import firestore, storage
    except Exception as exc:  # pragma: no cover
        raise CloudProofError("google-cloud-firestore and google-cloud-storage are required") from exc

    firestore_client = firestore.Client(project=config.project_id)
    snapshot = firestore_client.collection("healthia_one_patients").document(patient_id).get()
    _require(snapshot.exists, f"Firestore patient document missing: {patient_id}")
    state = snapshot.to_dict() or {}
    _require((state.get("profile") or {}).get("id") == patient_id, "Firestore patient identity mismatch")

    result = next((item for item in state.get("results") or [] if item.get("id") == result_id), None)
    document = next((item for item in state.get("documents") or [] if item.get("id") == document_id), None)
    missions = state.get("missions") or []
    mission = next((item for item in missions if mission_id and item.get("id") == mission_id), None)
    if mission is None:
        mission = next(
            (
                item
                for item in reversed(missions)
                if item.get("mission_type") == "result_explanation"
                and item.get("status") == "completed"
                and result_id in (item.get("evidence_ids") or [])
                and document_id in (item.get("evidence_ids") or [])
            ),
            None,
        )

    _require(result is not None, "Firestore lost the uploaded result")
    _require(document is not None, "Firestore lost the original document metadata")
    _require(mission is not None, "Firestore lost the completed result-explanation mission")

    storage_path = str(document.get("storage_path") or "")
    prefix = f"gs://{config.bucket_name}/"
    _require(storage_path.startswith(prefix), f"Document is not stored in expected GCS bucket: {storage_path}")
    object_name = storage_path[len(prefix) :]
    _require(object_name.startswith(f"patients/{patient_id}/"), f"GCS evidence is not patient scoped: {object_name}")

    blob = storage.Client(project=config.project_id).bucket(config.bucket_name).blob(object_name)
    _require(blob.exists(), f"GCS object missing: {object_name}")
    blob.reload()
    content = blob.download_as_bytes()

    return {
        "firestore_document": snapshot.reference.path,
        "firestore_update_time": snapshot.update_time.isoformat() if snapshot.update_time else None,
        "result_id": result_id,
        "document_id": document_id,
        "mission_id": str(mission.get("id") or mission_id),
        "mission_status": mission.get("status"),
        "mission_type": mission.get("mission_type"),
        "mission_evidence_ids": list(mission.get("evidence_ids") or []),
        "mission_closure_evidence": list(mission.get("closure_evidence") or []),
        "gcs_uri": storage_path,
        "gcs_generation": str(blob.generation or ""),
        "gcs_size": int(blob.size or 0),
        "gcs_sha256": hashlib.sha256(content).hexdigest(),
    }


def _assert_readiness(config: CloudProofConfig) -> dict[str, Any]:
    readiness = _json(config, "GET", "/api/readiness")
    expected = {
        "ready": True,
        "llm_backend": "gemini_api",
        "model": "gemini-3.5-flash",
        "store_backend": "firestore",
        "evidence_backend": "gcs",
        "auth_required": True,
        "patient_session_persistence": "restart_safe",
        "patient_state_scope": "authenticated_patient",
    }
    for key, value in expected.items():
        _require(readiness.get(key) == value, f"Readiness mismatch {key}: {readiness.get(key)!r}")
    _require(readiness.get("adk_ready") is True and readiness.get("ai_ready") is True, "ADK/AI readiness missing")
    return readiness


def prepare(config: CloudProofConfig, state_path: Path, before_revision: str) -> dict[str, Any]:
    _assert_readiness(config)
    suffix = uuid4().hex[:12]
    password = f"RevisionProof!{suffix}Aa9"
    email_a = f"revision-a-{suffix}@example.test"
    email_b = f"revision-b-{suffix}@example.test"
    weight_marker = 73.456

    account_a = _register(config, email_a, password, "Paciente Revision A")
    patient_a = str((account_a.get("account") or {}).get("patient_id") or "")
    _require(patient_a.startswith("patient_"), "Revision proof patient A registration failed")

    weight = _post_json(config, "/api/weight", {"weight_kg": weight_marker, "note": "synthetic revision continuity marker"})
    _require(abs(float(weight.get("weight_kg", 0)) - weight_marker) < 0.001, "Revision marker write failed")

    pdf = _minimal_pdf()
    filename = "revision-continuity-synthetic-lab.pdf"
    multipart, content_type = _multipart_file("file", filename, "application/pdf", pdf)
    uploaded = _json(config, "POST", "/api/results/upload", multipart, content_type)
    _require(uploaded.get("status") == "parsed", f"Revision proof multimodal upload failed: {uploaded}")
    _require(uploaded.get("evidence_backend") == "gcs", "Revision proof did not use GCS evidence")
    _require(uploaded.get("original_available") is True and uploaded.get("twin_updated") is True, "Result/original/twin linkage failed")
    result_id = str(uploaded.get("id") or "")
    document_id = str(uploaded.get("document_id") or "")
    _require(result_id and document_id, "Revision proof upload omitted result/document IDs")

    chat = _post_json(
        config,
        "/api/chat",
        {"message": f"Explícame el resultado {filename} que acabo de subir y confirma que quedó guardado."},
    )
    mission = chat.get("mission") or {}
    _require(mission.get("mission_type") == "result_explanation", f"Unexpected mission type: {mission}")
    _require(mission.get("status") == "completed", f"Result-explanation mission did not complete: {mission}")
    evidence_ids = mission.get("evidence_ids") or []
    _require(result_id in evidence_ids and document_id in evidence_ids, "Completed mission lost result/original provenance")
    closures = mission.get("closure_evidence") or []
    for marker in ("persisted_result_retrieved", "patient_explanation_returned", "original_evidence_link_resolved"):
        _require(marker in closures, f"Completed mission missing closure evidence: {marker}")
    mission_id = str(mission.get("id") or "")

    twin = _json(config, "GET", "/api/twin")
    node = next((item for item in twin.get("result_nodes") or [] if item.get("result_id") == result_id), None)
    _require(node is not None and node.get("document_id") == document_id, "Clinical twin lost result/original linkage before revision")

    status, downloaded, _ = _request(config, "GET", f"/api/documents/{document_id}/download")
    _require(status == 200 and downloaded == pdf, "Original evidence failed pre-revision byte round-trip")
    original_sha256 = hashlib.sha256(pdf).hexdigest()

    durable_before = _persistent_snapshot(config, patient_a, result_id, document_id, mission_id)
    _require(durable_before["gcs_sha256"] == original_sha256, "GCS bytes differ from uploaded original before revision")

    _json(config, "POST", "/api/auth/logout", body=b"")
    account_b = _register(config, email_b, password, "Paciente Revision B")
    patient_b = str((account_b.get("account") or {}).get("patient_id") or "")
    _require(patient_b.startswith("patient_") and patient_b != patient_a, "Revision proof patient B identity invalid")
    state_b = _json(config, "GET", "/api/bootstrap")
    _require(not any(item.get("id") == result_id for item in state_b.get("results") or []), "Patient B can see Patient A result before revision")
    _require(not any(item.get("id") == document_id for item in state_b.get("documents") or []), "Patient B can see Patient A document before revision")
    _require(
        not any(result_id in (item.get("evidence_ids") or []) for item in state_b.get("missions") or []),
        "Patient B can see Patient A mission before revision",
    )
    b_status, _, _ = _request(config, "GET", f"/api/documents/{document_id}/download")
    _require(b_status == 404, f"Patient B could probe Patient A original before revision: HTTP {b_status}")
    _json(config, "POST", "/api/auth/logout", body=b"")

    private_state = {
        "email_a": email_a,
        "email_b": email_b,
        "password": password,
        "patient_a": patient_a,
        "patient_b": patient_b,
        "weight_marker": weight_marker,
        "result_id": result_id,
        "document_id": document_id,
        "mission_id": mission_id,
        "filename": filename,
        "original_sha256": original_sha256,
        "before_revision": before_revision,
        "durable_before": durable_before,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(private_state, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "prepared",
        "before_revision": before_revision,
        "patient_ids_distinct": patient_a != patient_b,
        "result_id": result_id,
        "document_id": document_id,
        "mission_status": mission.get("status"),
        "mission_type": mission.get("mission_type"),
        "gcs_generation": durable_before["gcs_generation"],
        "checks": [
            "patient_a_created",
            "weight_marker_persisted",
            "gemini_multimodal_result_persisted",
            "original_gcs_roundtrip",
            "clinical_twin_linked",
            "result_explanation_mission_completed",
            "patient_b_isolated_before_revision",
        ],
    }


def verify(config: CloudProofConfig, state_path: Path, after_revision: str, evidence_path: Path) -> dict[str, Any]:
    private_state = json.loads(state_path.read_text(encoding="utf-8"))
    before_revision = str(private_state.get("before_revision") or "")
    _require(before_revision and after_revision and after_revision != before_revision, "Cloud Run revision did not change")
    _assert_readiness(config)

    _post_json(
        config,
        "/api/auth/login",
        {"email": private_state["email_a"], "password": private_state["password"]},
    )
    patient_a = private_state["patient_a"]
    patient_b = private_state["patient_b"]
    result_id = private_state["result_id"]
    document_id = private_state["document_id"]
    mission_id = private_state["mission_id"]
    weight_marker = float(private_state["weight_marker"])

    state_a = _json(config, "GET", "/api/bootstrap")
    _require((state_a.get("profile") or {}).get("id") == patient_a, "Patient A identity did not survive new revision")
    _require(
        any(abs(float(item.get("weight_kg", 0)) - weight_marker) < 0.001 for item in state_a.get("weights") or []),
        "Patient A longitudinal marker did not survive new revision",
    )
    _require(any(item.get("id") == result_id for item in state_a.get("results") or []), "Patient A result did not survive new revision")
    _require(any(item.get("id") == document_id for item in state_a.get("documents") or []), "Patient A document metadata did not survive new revision")
    closed = [
        item
        for item in state_a.get("missions") or []
        if item.get("mission_type") == "result_explanation"
        and item.get("status") == "completed"
        and result_id in (item.get("evidence_ids") or [])
        and document_id in (item.get("evidence_ids") or [])
    ]
    _require(closed, "Completed Taskmaster mission did not survive new revision")

    twin = _json(config, "GET", "/api/twin")
    node = next((item for item in twin.get("result_nodes") or [] if item.get("result_id") == result_id), None)
    _require(node is not None and node.get("document_id") == document_id, "Clinical twin linkage did not survive new revision")

    status, downloaded, _ = _request(config, "GET", f"/api/documents/{document_id}/download")
    _require(status == 200, f"Original evidence unavailable after revision: HTTP {status}")
    _require(hashlib.sha256(downloaded).hexdigest() == private_state["original_sha256"], "Original evidence bytes changed across revision")

    durable_after = _persistent_snapshot(config, patient_a, result_id, document_id, mission_id)
    durable_before = private_state["durable_before"]
    _require(durable_after["gcs_uri"] == durable_before["gcs_uri"], "GCS object path changed across revision")
    _require(durable_after["gcs_generation"] == durable_before["gcs_generation"], "Original GCS object was replaced across revision")
    _require(durable_after["gcs_sha256"] == durable_before["gcs_sha256"], "GCS original bytes changed across revision")
    _require(durable_after["mission_status"] == "completed", "Firestore mission no longer completed after revision")

    _json(config, "POST", "/api/auth/logout", body=b"")
    _post_json(
        config,
        "/api/auth/login",
        {"email": private_state["email_b"], "password": private_state["password"]},
    )
    state_b = _json(config, "GET", "/api/bootstrap")
    _require((state_b.get("profile") or {}).get("id") == patient_b, "Patient B identity did not survive new revision")
    _require(not any(item.get("id") == result_id for item in state_b.get("results") or []), "Patient B can see Patient A result after revision")
    _require(not any(item.get("id") == document_id for item in state_b.get("documents") or []), "Patient B can see Patient A document after revision")
    _require(
        not any(result_id in (item.get("evidence_ids") or []) for item in state_b.get("missions") or []),
        "Patient B can see Patient A mission after revision",
    )
    b_status, _, _ = _request(config, "GET", f"/api/documents/{document_id}/download")
    _require(b_status == 404, f"Patient B could probe Patient A original after revision: HTTP {b_status}")

    evidence = {
        "ok": True,
        "cloud_run_url": config.base_url,
        "before_revision": before_revision,
        "after_revision": after_revision,
        "revision_changed": after_revision != before_revision,
        "patient_a": patient_a,
        "patient_b": patient_b,
        "patient_ids_distinct": patient_a != patient_b,
        "result_id": result_id,
        "document_id": document_id,
        "mission_id": durable_after["mission_id"],
        "mission_type": durable_after["mission_type"],
        "mission_status": durable_after["mission_status"],
        "gcs_uri": durable_after["gcs_uri"],
        "gcs_generation_before": durable_before["gcs_generation"],
        "gcs_generation_after": durable_after["gcs_generation"],
        "original_sha256_unchanged": durable_after["gcs_sha256"] == durable_before["gcs_sha256"],
        "proof": [
            "new_cloud_run_revision_ready",
            "patient_a_reauthenticated_after_revision",
            "patient_a_longitudinal_state_persisted",
            "multimodal_result_persisted_across_revision",
            "original_gcs_object_generation_unchanged",
            "original_evidence_bytes_unchanged",
            "clinical_twin_provenance_persisted",
            "completed_taskmaster_mission_persisted",
            "patient_b_identity_persisted",
            "two_patient_isolation_persisted_after_revision",
            "cross_patient_document_denied_after_revision",
        ],
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


def _config(args: argparse.Namespace) -> CloudProofConfig:
    return CloudProofConfig(
        base_url=args.url,
        project_id=args.project,
        bucket_name=args.bucket,
        identity_token=args.identity_token,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HealthIA Cloud Run revision/reconnect continuity proof")
    sub = parser.add_subparsers(dest="phase", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--url", required=True)
        p.add_argument("--project", required=True)
        p.add_argument("--bucket", required=True)
        p.add_argument("--identity-token", default="")
        p.add_argument("--state-file", required=True)

    prepare_parser = sub.add_parser("prepare")
    common(prepare_parser)
    prepare_parser.add_argument("--before-revision", required=True)

    verify_parser = sub.add_parser("verify")
    common(verify_parser)
    verify_parser.add_argument("--after-revision", required=True)
    verify_parser.add_argument("--evidence-file", default=str(DEFAULT_EVIDENCE))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.phase == "prepare":
            result = prepare(_config(args), Path(args.state_file), args.before_revision)
        else:
            result = verify(_config(args), Path(args.state_file), args.after_revision, Path(args.evidence_file))
    except Exception as exc:
        print(f"HEALTHIA_CLOUD_REVISION_PROOF_FAILED {type(exc).__name__}: {str(exc)[:1200]}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
