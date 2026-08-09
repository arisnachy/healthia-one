from healthia_one.google_cloud_capabilities import CAPABILITIES, CapabilityStatus, capability_manifest


def test_constellation_registers_requested_google_health_layers_without_claiming_all_live():
    expected = {
        "vertex_brain",
        "places_navigation",
        "calendar_scheduling",
        "gmail_communications",
        "people_trusted_contacts",
        "drive_documents",
        "tasks_followup",
        "document_ai",
        "vision_ocr",
        "healthcare_interop",
        "speech_input",
        "speech_output",
        "translation",
        "firebase_auth",
        "fcm_notifications",
        "cloud_storage",
        "firestore_state",
        "health_connect",
        "bigquery_population",
        "forms_followup",
        "wallet_credentials",
        "education_video",
    }
    assert expected <= set(CAPABILITIES)
    assert CAPABILITIES["document_ai"].status == CapabilityStatus.CONTRACT
    assert CAPABILITIES["healthcare_interop"].status == CapabilityStatus.CONTRACT
    assert CAPABILITIES["bigquery_population"].status == CapabilityStatus.DEFERRED
    assert CAPABILITIES["cloud_storage"].status == CapabilityStatus.EXISTING
    assert CAPABILITIES["places_navigation"].status == CapabilityStatus.EXECUTABLE


def test_manifest_has_truth_boundary_and_counts_every_capability_once():
    manifest = capability_manifest()
    assert sum(manifest["counts"].values()) == len(CAPABILITIES)
    assert "must never be described as a live integration" in manifest["truth_boundary"]


def test_contacts_and_population_capabilities_keep_separate_safety_boundaries():
    contacts = CAPABILITIES["people_trusted_contacts"]
    population = CAPABILITIES["bigquery_population"]
    assert "clinical relationship" in contacts.notes
    assert population.patient_facing is False
    assert "deidentification" in population.dependencies
