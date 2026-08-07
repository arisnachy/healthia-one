from concurrent.futures import ThreadPoolExecutor

from healthia_one.models import ClinicalDocument, HealthResult, PatientState
from healthia_one.pairing import DevicePairingManager, PairingError
from healthia_one.result_ai import apply_multimodal_analysis, infer_result_kind, multimodal_supported
from healthia_one.result_search import conversational_result_context
from healthia_one.twin import clinical_twin_summary


def test_pairing_wait_is_event_driven_and_patient_bound() -> None:
    manager = DevicePairingManager(ttl_minutes=10)
    session = manager.create(patient_id="patient-alpha")
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiter = pool.submit(manager.wait_for_claim, session["code"], 2)
        claim = manager.claim(session["code"], "phone-alpha", "Pixel test")
        waited = waiter.result(timeout=2)

    assert waited["claimed"] is True
    assert waited["connection_id"] == session["connection_id"]
    principal = manager.authorize(claim["access_token"], "phone-alpha", "patient-alpha")
    assert principal is not None
    assert principal.connection_id == session["connection_id"]
    assert manager.authorize(claim["access_token"], "phone-alpha", "patient-beta") is None
    assert manager.authorize(claim["access_token"], "other-phone", "patient-alpha") is None


def test_pairing_code_is_single_use_even_for_same_device() -> None:
    manager = DevicePairingManager()
    code = manager.create()["code"]
    manager.claim(code, "phone-1", "Phone")
    try:
        manager.claim(code, "phone-1", "Phone")
    except PairingError as exc:
        assert "consumido" in str(exc)
    else:
        raise AssertionError("A pairing code must not mint a second bearer token")


def test_signed_device_credential_survives_restart_with_stable_secret() -> None:
    secret = "restart-safe-device-secret-0123456789abcdef"
    first = DevicePairingManager(token_secret=secret)
    session = first.create(patient_id="patient-alpha")
    claim = first.claim(session["code"], "phone-alpha", "Pixel test")
    assert claim["credential_persistence"] == "restart_safe"

    restarted = DevicePairingManager(token_secret=secret)
    principal = restarted.authorize(claim["access_token"], "phone-alpha", "patient-alpha")
    assert principal is not None
    assert principal.connection_id == session["connection_id"]
    assert restarted.authorize(claim["access_token"], "phone-alpha", "patient-beta") is None
    assert DevicePairingManager(token_secret="different-secret-0123456789abcdef").authorize(
        claim["access_token"], "phone-alpha", "patient-alpha"
    ) is None


def test_result_kind_detection_covers_requested_modalities() -> None:
    assert infer_result_kind("analitica_abril.pdf", "application/pdf") == "laboratory"
    assert infer_result_kind("TAC_torax.png", "image/png") == "ct"
    assert infer_result_kind("resonancia_cerebral.jpg", "image/jpeg") == "mri"
    assert infer_result_kind("sonografia_abdominal.webp", "image/webp") == "ultrasound"
    assert infer_result_kind("ECG_control.png", "image/png") == "ecg"
    assert multimodal_supported("study.pdf", "application/pdf") is True
    assert multimodal_supported("study.webp", "image/webp") is True


def test_multimodal_analysis_is_mapped_without_inventing_new_schema() -> None:
    result = HealthResult(filename="TAC_torax.png", status="pending_multimodal")
    parsed = apply_multimodal_analysis(
        result,
        {
            "status": "parsed",
            "panel": "TC de tórax",
            "anatomical_regions": ["Tórax", "Pulmón derecho"],
            "observations": [{"name": "Texto visible", "value": "Serie axial"}],
            "findings": ["Opacidad focal descrita en la evidencia"],
            "impression": "Hallazgo que requiere correlación clínica",
            "limitations": ["Imagen aislada; no sustituye el estudio completo"],
            "patient_explanation": "HealthIA organizó únicamente lo visible en el archivo.",
            "requires_professional_review": True,
        },
    )
    assert parsed.status == "parsed"
    assert parsed.explained is True
    assert parsed.panel == "TC de tórax"
    assert any(item.name == "Región anatómica" and item.value == "Tórax" for item in parsed.items)
    assert any(item.name == "Hallazgo" for item in parsed.items)
    assert "revisión" not in parsed.explanation.lower() or "profesional" in parsed.explanation.lower()


def test_clinical_twin_links_result_to_original_evidence() -> None:
    state = PatientState()
    result = apply_multimodal_analysis(
        HealthResult(filename="ecg_control.png", status="pending_multimodal"),
        {
            "status": "parsed",
            "panel": "ECG",
            "anatomical_regions": ["Corazón"],
            "observations": [],
            "findings": ["Ritmo descrito en el trazado"],
            "impression": "Requiere correlación profesional",
            "limitations": [],
            "patient_explanation": "Resumen de la evidencia.",
            "requires_professional_review": True,
        },
    )
    document = ClinicalDocument(
        title="ECG original",
        filename="ecg_control.png",
        mime_type="image/png",
        storage_path="uploads/patient_demo/ecg_control.png",
        status="parsed",
        related_result_id=result.id,
    )
    state.results.append(result)
    state.documents.append(document)

    twin = clinical_twin_summary(state)
    node = twin["result_nodes"][0]
    assert node["result_id"] == result.id
    assert node["document_id"] == document.id
    assert node["regions"] == ["Corazón"]
    assert twin["region_index"]["corazón"] == [result.id]
    assert twin["source_of_truth"] == "patient_state"


def test_chat_retrieval_finds_requested_tac_instead_of_latest_lab() -> None:
    state = PatientState()
    tac = HealthResult(
        filename="TAC_torax_enero.png",
        panel="TC de tórax",
        explanation="Estudio de tórax de enero.",
    )
    lab = HealthResult(
        filename="laboratorio_julio.json",
        panel="Laboratorio de julio",
        explanation="Laboratorio más reciente.",
    )
    document = ClinicalDocument(
        title="TAC original",
        filename=tac.filename,
        mime_type="image/png",
        storage_path="uploads/patient_demo/tac.png",
        status="parsed",
        related_result_id=tac.id,
    )
    state.results.extend([tac, lab])
    state.documents.append(document)

    context = conversational_result_context(state, "Háblame de mi TAC de tórax")
    assert context is not None
    assert context["result_id"] == tac.id
    assert context["document_id"] == document.id
    assert context["filename"] == "TAC_torax_enero.png"


def test_browser_pairing_has_no_repetitive_interval_polling() -> None:
    source = open("web/profile-devices.js", encoding="utf-8").read()
    assert "setInterval(" not in source
    assert "/wait" in source
    assert "AbortController" in source


def test_server_has_no_permanent_proactive_loop_in_lifespan() -> None:
    source = open("app/main.py", encoding="utf-8").read()
    assert "background_loop(" not in source
    assert '"agent_execution": "demand_driven"' in source
