from __future__ import annotations

import argparse
import http.cookiejar
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


_COOKIE_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_COOKIE_JAR))


def _cloud_credentials():
    token = os.getenv("HEALTHIA_CLOUD_ACCESS_TOKEN", "").strip()
    if not token:
        return None
    from google.oauth2.credentials import Credentials

    return Credentials(token=token)


@dataclass(frozen=True)
class CloudProofConfig:
    base_url: str
    project_id: str
    bucket_name: str
    identity_token: str = ""
    evaluation_access_key: str = ""
    release_sha: str = ""
    timeout: int = 45


def _request(
    config: CloudProofConfig,
    method: str,
    path: str,
    body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    url = f"{config.base_url.rstrip('/')}{path}"
    headers = {"Accept": "application/json"}
    if config.identity_token:
        headers["Authorization"] = f"Bearer {config.identity_token}"
    if config.evaluation_access_key:
        headers["X-HealthIA-Evaluation-Key"] = config.evaluation_access_key
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=config.timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())
    except Exception as exc:
        raise CloudProofError(f"{method} {path} failed: {type(exc).__name__}: {exc}") from exc


def _json(
    config: CloudProofConfig,
    method: str,
    path: str,
    body: bytes | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    status, raw, _ = _request(config, method, path, body, content_type)
    if status < 200 or status >= 300:
        detail = raw.decode("utf-8", errors="replace")[:800]
        raise CloudProofError(f"{method} {path} -> HTTP {status}: {detail}")
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
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    ]
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
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(output)


def _safe_option(question: dict[str, Any]) -> str:
    options = [str(item) for item in question.get("options") or []]
    for preferred in ("ninguna", "no ", "sin ", "no tengo", "no he", "no estoy"):
        for option in options:
            if preferred in option.lower():
                return option
    return options[-1] if options else "No estoy seguro"


def _interview_answer(interview: dict[str, Any]) -> str:
    block = interview.get("question_block") or {}
    answers = [
        {
            "question_id": question.get("id"),
            "question_prompt": question.get("prompt"),
            "selected": [_safe_option(question)],
            "detail": "",
        }
        for question in block.get("questions") or []
    ]
    return "[ENTREVISTA_CLINICA]" + json.dumps(
        {"interview_id": interview.get("id"), "stage": block.get("stage"), "answers": answers},
        ensure_ascii=False,
    )


def _register(config: CloudProofConfig, email: str, password: str, display_name: str) -> dict[str, Any]:
    return _post_json(
        config,
        "/api/auth/register",
        {"email": email, "password": password, "display_name": display_name},
    )


def verify_firestore_and_gcs(
    config: CloudProofConfig,
    patient_id: str,
    result_id: str,
    document_id: str,
) -> dict[str, Any]:
    try:
        from google.cloud import firestore, storage
    except Exception as exc:
        raise CloudProofError("google-cloud-firestore and google-cloud-storage must be installed") from exc

    credentials = _cloud_credentials()
    firestore_client = firestore.Client(project=config.project_id, credentials=credentials)
    snapshot = firestore_client.collection("healthia_one_patients").document(patient_id).get()
    if not snapshot.exists:
        raise CloudProofError(f"Firestore patient document does not exist: {patient_id}")
    state = snapshot.to_dict() or {}
    if (state.get("profile") or {}).get("id") != patient_id:
        raise CloudProofError("Firestore profile identity differs from authenticated patient document")
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
    if not object_name.startswith(f"patients/{patient_id}/"):
        raise CloudProofError(f"GCS object is not patient scoped: {object_name}")
    blob = storage.Client(project=config.project_id, credentials=credentials).bucket(config.bucket_name).blob(object_name)
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


def verify_living_system_firestore(config: CloudProofConfig, session_id: str) -> dict[str, Any]:
    try:
        from google.cloud import firestore
    except Exception as exc:
        raise CloudProofError("google-cloud-firestore must be installed") from exc

    snapshot = firestore.Client(project=config.project_id, credentials=_cloud_credentials()).collection("healthia_one_patients").document("patient_eval_living").get()
    if not snapshot.exists:
        raise CloudProofError("Firestore synthetic evaluator document does not exist")
    state = snapshot.to_dict() or {}
    session = state.get("evaluation_session") or {}
    events = state.get("living_twin_events") or []
    if session.get("id") != session_id or session.get("status") != "completed":
        raise CloudProofError("Firestore evaluator lease does not match completed Cloud run")
    if session.get("release_sha") != config.release_sha:
        raise CloudProofError("Firestore evaluator lease is not bound to the candidate release SHA")
    if len(events) != 14 or events[-1].get("event_type") != "twin_updated_from_verified_outcome":
        raise CloudProofError("Firestore does not contain the exact completed 14-event replay")
    mission_id = session.get("mission_id")
    mission = next((item for item in state.get("missions", []) if item.get("id") == mission_id), None)
    if mission is None or mission.get("status") != "completed" or not mission.get("closure_evidence"):
        raise CloudProofError("Firestore Living System mission lacks persisted closure evidence")
    return {
        "firestore_document": snapshot.reference.path,
        "firestore_update_time": snapshot.update_time.isoformat() if snapshot.update_time else None,
        "session_id": session_id,
        "release_sha": session.get("release_sha"),
        "runtime_revision": session.get("runtime_revision"),
        "event_count": len(events),
        "mission_id": mission_id,
        "closure_evidence": mission.get("closure_evidence"),
    }


def verify_living_system(config: CloudProofConfig) -> dict[str, Any]:
    if not config.evaluation_access_key:
        raise CloudProofError("Living System evaluator key was not supplied to the strict proof")
    living_status, living_html, _ = _request(config, "GET", "/living")
    if living_status != 200 or b"It is a living health system" not in living_html:
        raise CloudProofError("Public Living System UI is unavailable")

    state = _post_json(config, "/api/evaluation/arm", {})
    session = state.get("session") or {}
    session_id = str(session.get("id") or "")
    if not session_id:
        raise CloudProofError("Living System arm did not return a session ID")
    if session.get("status") in {"armed", "active"}:
        state = _post_json(config, "/api/evaluation/run", {"session_id": session_id})
        session = state.get("session") or {}
    if session.get("status") == "waiting_human":
        state = _post_json(
            config,
            "/api/evaluation/complete",
            {"session_id": session_id, "systolic": 132, "diastolic": 82, "pulse": 70},
        )
        session = state.get("session") or {}
    expected = state.get("expected_event_sequence") or []
    if session.get("status") != "completed" or state.get("event_types") != expected or len(expected) != 14:
        raise CloudProofError("Living System did not complete the exact 14-event sequence")
    if session.get("release_sha") != config.release_sha or session.get("runtime_revision") in {"", "local", None}:
        raise CloudProofError("Living System session is not bound to the candidate SHA and Cloud Run revision")
    if state.get("model_calls") != 0:
        raise CloudProofError("Deterministic Living System unexpectedly consumed a model call")
    provider = verify_living_system_firestore(config, session_id)
    return {
        "ui_status": living_status,
        "session_status": session.get("status"),
        "twin_version": (state.get("twin") or {}).get("version"),
        "event_count": len(expected),
        "model_calls": state.get("model_calls"),
        "provider_reread": provider,
    }


def _verify_clinical_memory_and_resolution(config: CloudProofConfig) -> dict[str, Any]:
    first = _post_json(
        config,
        "/api/chat",
        {"message": "Desde ayer tengo ardor al orinar y voy al baño muy seguido. Quiero saber qué información necesitas para orientarme."},
    )
    message1 = first.get("message") or {}
    meta1 = message1.get("metadata") or {}
    interview1 = meta1.get("clinical_interview") or {}
    questions1 = (interview1.get("question_block") or {}).get("questions") or []
    if meta1.get("llm_status") != "dynamic_clinical_questions" or interview1.get("question_source") != "gemini_dynamic":
        raise CloudProofError(f"First clinical block is not live Gemini/ADK: {meta1}")
    if len(questions1) != 5:
        raise CloudProofError("First clinical block is not exactly five questions")

    second = _post_json(config, "/api/chat", {"message": _interview_answer(interview1)})
    message2 = second.get("message") or {}
    meta2 = message2.get("metadata") or {}
    interview2 = meta2.get("clinical_interview") or {}
    questions2 = (interview2.get("question_block") or {}).get("questions") or []
    if meta2.get("llm_status") != "dynamic_clinical_questions" or interview2.get("question_source") != "gemini_dynamic":
        raise CloudProofError(f"Second clinical block is not live Gemini/ADK: {meta2}")
    if len(questions2) != 5:
        raise CloudProofError("Second clinical block is not exactly five questions")
    previous = interview2.get("previous_answers") or []
    if len(previous) < 5 or not all(item.get("question_prompt") for item in previous[:5]):
        raise CloudProofError("Second block did not preserve semantic memory of first questions")
    prompts1 = {str(q.get("prompt", "")).strip().lower() for q in questions1}
    prompts2 = {str(q.get("prompt", "")).strip().lower() for q in questions2}
    if prompts1.intersection(prompts2):
        raise CloudProofError("Second block repeated a first-block question verbatim")

    third = _post_json(config, "/api/chat", {"message": _interview_answer(interview2)})
    final_message = third.get("message") or {}
    final_meta = final_message.get("metadata") or {}
    final_interview = final_meta.get("clinical_interview") or {}
    if final_meta.get("llm_status") == "dynamic_clinical_followup_questions":
        questions3 = (final_interview.get("question_block") or {}).get("questions") or []
        if len(questions3) != 5 or len(final_interview.get("previous_answers") or []) < 10:
            raise CloudProofError("AI-requested third block is not a valid memory-preserving adaptive block")
        fourth = _post_json(config, "/api/chat", {"message": _interview_answer(final_interview)})
        final_message = fourth.get("message") or {}
        final_meta = final_message.get("metadata") or {}
    if final_meta.get("llm_status") != "clinical_ai_orientation_completed":
        raise CloudProofError(f"AI did not decide when to close with patient orientation: {final_meta.get('llm_status')}")
    if final_meta.get("clinical_synthesis_source") != "gemini" or len(str(final_message.get("content") or "")) < 120:
        raise CloudProofError("Final clinical orientation is missing or not generated by Gemini")

    audit_payload = _json(config, "GET", "/api/audit?limit=150")
    adk_events = [
        item for item in audit_payload.get("events", [])
        if item.get("actor") == "google_adk" and item.get("action") == "execute_demand_driven_clinical_plan"
    ]
    if len(adk_events) < 2:
        raise CloudProofError("Clinical workflow has fewer than two Google ADK execution traces")
    for event in adk_events:
        roles = (event.get("details") or {}).get("executed_roles") or []
        if "interview" not in roles or "safety" not in roles or len(roles) > 4:
            raise CloudProofError(f"Google ADK tool trajectory violates minimum-tool contract: {roles}")
    return {
        "first_question_count": len(questions1),
        "second_question_count": len(questions2),
        "adk_event_count": len(adk_events),
        "final_status": final_meta.get("llm_status"),
        "latest_adk_session": adk_events[0].get("resource_id"),
        "latest_adk_roles": (adk_events[0].get("details") or {}).get("executed_roles") or [],
    }


def run(config: CloudProofConfig) -> dict[str, Any]:
    # Cloud Run reserves some URL paths ending in `z`. The deployed gate
    # therefore uses the richer public readiness endpoint; /healthz remains only
    # as a local/backward-compatibility route.
    readiness = _json(config, "GET", "/api/readiness")
    if readiness.get("ready") is not True:
        raise CloudProofError(f"Cloud Run readiness check failed: {readiness}")
    expected = {
        "llm_backend": "gemini_api",
        "store_backend": "firestore",
        "evidence_backend": "gcs",
        "agent_execution": "demand_driven",
        "auth_required": True,
        "patient_state_scope": "authenticated_patient",
        "patient_session_persistence": "restart_safe",
    }
    for key, value in expected.items():
        if readiness.get(key) != value:
            raise CloudProofError(f"Readiness mismatch {key}: expected {value!r}, found {readiness.get(key)!r}")
    if not readiness.get("adk_ready") or not readiness.get("ai_ready"):
        raise CloudProofError("Cloud runtime does not report real Google AI readiness")
    if readiness.get("living_evaluation_available") is not True:
        raise CloudProofError("Cloud runtime does not report the bounded Living System evaluator")
    if not config.release_sha or readiness.get("release_sha") != config.release_sha:
        raise CloudProofError("Cloud readiness is not bound to the requested release SHA")

    living_system = verify_living_system(config)

    anonymous_status, _, _ = _request(config, "GET", "/api/bootstrap")
    if anonymous_status != 401:
        raise CloudProofError(f"Anonymous patient API was not rejected: HTTP {anonymous_status}")

    suffix = uuid.uuid4().hex[:12]
    password = f"CloudProof!{suffix}Aa9"
    account_a = _register(config, f"cloud-a-{suffix}@example.test", password, "Paciente Cloud A")
    patient_a = str((account_a.get("account") or {}).get("patient_id") or "")
    if not patient_a.startswith("patient_"):
        raise CloudProofError("Cloud registration did not create a patient-scoped identity")

    weight = _post_json(config, "/api/weight", {"weight_kg": 81.2, "note": "synthetic isolation marker"})
    if abs(float(weight.get("weight_kg", 0)) - 81.2) > 0.001:
        raise CloudProofError("Authenticated patient write failed")

    ai_probe = _json(config, "POST", "/api/ai/test", body=b"")
    if not (ai_probe.get("ok") and ai_probe.get("status") == "ready" and ai_probe.get("live_request")):
        raise CloudProofError(f"Real Gemini probe failed: {ai_probe}")

    clinical = _verify_clinical_memory_and_resolution(config)

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
    if claim.get("patient_id") != patient_a or not claim.get("connection_id") or not claim.get("access_token"):
        raise CloudProofError("Device credential did not bind the authenticated patient/connection identity")

    pdf = _minimal_pdf()
    multipart, content_type = _multipart_file("file", "synthetic_lab_cloud_proof.pdf", "application/pdf", pdf)
    uploaded = _json(config, "POST", "/api/results/upload", multipart, content_type)
    if uploaded.get("status") != "parsed":
        raise CloudProofError(f"Gemini multimodal result was not parsed: {uploaded}")
    if uploaded.get("evidence_backend") != "gcs" or not uploaded.get("original_available") or not uploaded.get("twin_updated"):
        raise CloudProofError("Upload did not prove durable evidence/twin linkage")
    result_id = str(uploaded.get("id") or "")
    document_id = str(uploaded.get("document_id") or "")
    if not result_id or not document_id:
        raise CloudProofError("Upload omitted result/document identity")

    twin = _json(config, "GET", "/api/twin")
    node = next((item for item in twin.get("result_nodes", []) if item.get("result_id") == result_id), None)
    if node is None or node.get("document_id") != document_id:
        raise CloudProofError("Clinical twin does not link uploaded result to original evidence")

    status, downloaded, headers = _request(config, "GET", f"/api/documents/{document_id}/download")
    if status != 200 or downloaded != pdf:
        raise CloudProofError("Original evidence did not round-trip byte-for-byte through Cloud Run/GCS")

    persistence = verify_firestore_and_gcs(config, patient_a, result_id, document_id)

    _json(config, "POST", "/api/auth/logout", body=b"")
    account_b = _register(config, f"cloud-b-{suffix}@example.test", password, "Paciente Cloud B")
    patient_b = str((account_b.get("account") or {}).get("patient_id") or "")
    if not patient_b.startswith("patient_") or patient_b == patient_a:
        raise CloudProofError("Second Cloud account did not receive a distinct patient identity")
    state_b = _json(config, "GET", "/api/bootstrap")
    if (state_b.get("profile") or {}).get("id") != patient_b:
        raise CloudProofError("Patient B bootstrap identity mismatch")
    if any(abs(float(item.get("weight_kg", 0)) - 81.2) < 0.001 for item in state_b.get("weights") or []):
        raise CloudProofError("Patient B can see Patient A longitudinal weight")
    b_document_status, _, _ = _request(config, "GET", f"/api/documents/{document_id}/download")
    if b_document_status != 404:
        raise CloudProofError(f"Patient B could probe Patient A document: HTTP {b_document_status}")

    _json(config, "POST", "/api/auth/logout", body=b"")
    _post_json(config, "/api/auth/login", {"email": f"cloud-a-{suffix}@example.test", "password": password})
    state_a = _json(config, "GET", "/api/bootstrap")
    if (state_a.get("profile") or {}).get("id") != patient_a:
        raise CloudProofError("Patient A identity not restored after logout/login")
    if not any(abs(float(item.get("weight_kg", 0)) - 81.2) < 0.001 for item in state_a.get("weights") or []):
        raise CloudProofError("Patient A longitudinal state not restored after login")
    if not any(item.get("id") == result_id for item in state_a.get("results") or []):
        raise CloudProofError("Patient A result not restored after login")

    return {
        "ok": True,
        "cloud_run_url": config.base_url,
        "project_id": config.project_id,
        "model": ai_probe.get("model"),
        "patient_a": patient_a,
        "patient_b": patient_b,
        "patient_ids_distinct": patient_a != patient_b,
        "clinical": clinical,
        "device_connection_id": claim.get("connection_id"),
        "device_credential_persistence": claim.get("credential_persistence"),
        "multimodal_result_id": result_id,
        "document_id": document_id,
        "download_content_type": headers.get("Content-Type", ""),
        "clinical_twin_linked": True,
        "firestore": persistence,
        "living_system": living_system,
        "proof": [
            "cloud_run_health",
            "authenticated_patient_runtime",
            "anonymous_patient_api_rejected",
            "two_patient_state_isolation",
            "cross_patient_document_denied",
            "logout_relogin_state_restoration",
            "firestore_patient_scoped_state",
            "gcs_patient_scoped_original_evidence",
            "live_gemini_interactions_call",
            "google_adk_runner_tool_trajectory",
            "two_memory_preserving_dynamic_question_blocks",
            "gemini_followup_or_orientation_decision",
            "restart_safe_browser_session_identity",
            "restart_safe_device_identity",
            "gemini_multimodal_pdf_extraction",
            "clinical_twin_provenance",
            "original_evidence_roundtrip",
            "living_system_public_ui",
            "living_system_exact_14_event_replay",
            "living_system_firestore_provider_reread",
            "living_system_zero_model_calls",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strict HealthIA ONE Google Cloud proof gate")
    parser.add_argument("--url", default=os.getenv("HEALTHIA_CLOUD_URL", ""))
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument("--bucket", default=os.getenv("HEALTHIA_GCS_BUCKET", ""))
    parser.add_argument("--identity-token", default=os.getenv("HEALTHIA_CLOUD_ID_TOKEN", ""))
    parser.add_argument("--evaluation-access-key", default=os.getenv("HEALTHIA_EVALUATION_ACCESS_KEY", ""))
    parser.add_argument("--release-sha", default=os.getenv("HEALTHIA_RELEASE_SHA", ""))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing = [
        name
        for name, value in (
            ("url", args.url),
            ("project", args.project),
            ("bucket", args.bucket),
            ("release_sha", args.release_sha),
        )
        if not value
    ]
    if missing:
        print(f"HEALTHIA_CLOUD_PROOF_BLOCKED missing={','.join(missing)}", file=sys.stderr)
        return 2
    config = CloudProofConfig(
        base_url=args.url,
        project_id=args.project,
        bucket_name=args.bucket,
        identity_token=args.identity_token,
        evaluation_access_key=args.evaluation_access_key,
        release_sha=args.release_sha,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
