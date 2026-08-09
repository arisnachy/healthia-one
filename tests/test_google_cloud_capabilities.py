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
        "youtube_public",
        "gemini_live_voice",
    }
    assert expected <= set(CAPABILITIES)

    # A guarded connector slice may be executable without pretending the external
    # Google resource has been provisioned or live-proven.
    for capability_id in (
        "document_ai",
        "healthcare_interop",
        "speech_input",
        "speech_output",
        "fcm_notifications",
        "education_video",
    ):
        assert CAPABILITIES[capability_id].status == CapabilityStatus.EXECUTABLE

    # Adjacent products that were not implemented by those slices stay honest.
    for capability_id in (
        "vision_ocr",
        "translation",
        "firebase_auth",
        "youtube_public",
        "gemini_live_voice",
    ):
        assert CAPABILITIES[capability_id].status == CapabilityStatus.CONTRACT

    assert CAPABILITIES["bigquery_population"].status == CapabilityStatus.DEFERRED
    assert CAPABILITIES["cloud_storage"].status == CapabilityStatus.EXISTING
    assert CAPABILITIES["places_navigation"].status == CapabilityStatus.EXECUTABLE


def test_manifest_has_truth_boundary_and_counts_every_capability_once():
    manifest = capability_manifest()
    assert sum(manifest["counts"].values()) == len(CAPABILITIES)
    boundary = manifest["truth_boundary"].lower()
    assert "does not imply live external configuration" in boundary
    assert "must never be described as live integrations" in boundary


def test_contacts_and_population_capabilities_keep_separate_safety_boundaries():
    contacts = CAPABILITIES["people_trusted_contacts"]
    population = CAPABILITIES["bigquery_population"]
    assert "clinical relationship" in contacts.notes
    assert population.patient_facing is False
    assert "deidentification" in population.dependencies
