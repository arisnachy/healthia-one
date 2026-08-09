from healthia_one.google_cloud_capabilities import CAPABILITIES, CapabilityStatus, capability_manifest


def test_step9_guarded_slices_are_executable_without_claiming_live_configuration():
    expected = {
        "document_ai",
        "healthcare_interop",
        "speech_input",
        "speech_output",
        "fcm_notifications",
        "education_video",
    }
    assert all(CAPABILITIES[item].status == CapabilityStatus.EXECUTABLE for item in expected)

    assert "not yet proven" in CAPABILITIES["document_ai"].notes.lower()
    assert "no live healthia fhir/dicom store" in CAPABILITIES["healthcare_interop"].notes.lower()
    assert "not yet live-proven" in CAPABILITIES["fcm_notifications"].notes.lower()
    assert "no live veo generation" in CAPABILITIES["education_video"].notes.lower()


def test_sync_voice_does_not_falsely_promote_streaming_or_gemini_live():
    assert CAPABILITIES["speech_input"].status == CapabilityStatus.EXECUTABLE
    assert "synchronous" in CAPABILITIES["speech_input"].notes.lower()
    assert "streaming" in CAPABILITIES["speech_input"].notes.lower()
    assert CAPABILITIES["gemini_live_voice"].status == CapabilityStatus.CONTRACT


def test_private_veo_does_not_promote_public_youtube():
    assert CAPABILITIES["education_video"].google_product == "Vertex AI Veo"
    assert CAPABILITIES["education_video"].status == CapabilityStatus.EXECUTABLE
    assert CAPABILITIES["youtube_public"].status == CapabilityStatus.CONTRACT
    assert "separate" in CAPABILITIES["youtube_public"].notes.lower()


def test_vision_translation_and_firebase_auth_remain_contract_only():
    assert CAPABILITIES["vision_ocr"].status == CapabilityStatus.CONTRACT
    assert CAPABILITIES["translation"].status == CapabilityStatus.CONTRACT
    assert CAPABILITIES["firebase_auth"].status == CapabilityStatus.CONTRACT


def test_manifest_explains_executable_is_not_synonymous_with_live():
    manifest = capability_manifest()
    assert "does not imply live external configuration" in manifest["truth_boundary"].lower()
    assert manifest["counts"]["executable"] >= 12
