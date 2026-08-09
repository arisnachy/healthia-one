import pytest

from healthia_one.google_clinical_cloud_connectors import (
    DocumentAIConnector,
    FCMConnector,
    HealthcareConnector,
    SpeechConnector,
    TextToSpeechConnector,
    VeoConnector,
)
from healthia_one.google_connector_runtime import GoogleConnectorError
from healthia_one.google_constellation import (
    ACTION_POLICIES,
    GrantBundle,
    GoogleAction,
    GoogleActionRequest,
    GoogleGrant,
    GoogleService,
    authorize_google_action,
)


class TokenProvider:
    def token(self, scopes=()):
        return "short-lived-test-token"


class Transport:
    def __init__(self):
        self.calls = []

    def call(self, method, url, *, headers=None, body=None):
        self.calls.append((method, url, headers or {}, body))
        if "documentai" in url:
            return {"document": {"text": "private extracted text", "pages": [{"pageNumber": 1}], "entities": []}}
        if "fcm.googleapis.com" in url:
            return {"name": "projects/demo/messages/123"}
        if "speech.googleapis.com" in url:
            return {"results": [{"alternatives": [{"transcript": "private transcript", "confidence": 0.9}]}], "requestId": "77"}
        if "texttospeech" in url:
            return {"audioContent": "UklGRg=="}
        if "aiplatform" in url:
            return {"name": "projects/demo/locations/us-central1/operations/veo123"}
        if method == "GET" and "dicomWeb" in url:
            return [{"00080018": {"vr": "UI", "Value": ["1.2.3"]}}]
        if method == "GET":
            return {"resourceType": "Patient", "id": "p1", "entry": []}
        return {"resourceType": "Patient", "id": "p1"}


def test_new_cloud_actions_have_patient_grant_and_mutation_boundaries():
    assert ACTION_POLICIES[GoogleAction.DOCUMENT_AI_PROCESS].service == GoogleService.DOCUMENT_AI
    assert ACTION_POLICIES[GoogleAction.HEALTHCARE_FHIR_READ].required_grants == {GrantBundle.HEALTHCARE_READ}
    assert ACTION_POLICIES[GoogleAction.HEALTHCARE_FHIR_WRITE].explicit_authorization_required is True
    assert ACTION_POLICIES[GoogleAction.FCM_SEND_MISSION_NOTIFICATION].explicit_authorization_required is True
    assert ACTION_POLICIES[GoogleAction.VEO_GENERATE].explicit_authorization_required is True
    assert ACTION_POLICIES[GoogleAction.SPEECH_RECOGNIZE].required_grants == {GrantBundle.SPEECH_TRANSCRIBE}
    assert ACTION_POLICIES[GoogleAction.TEXT_TO_SPEECH_SYNTHESIZE].required_grants == {GrantBundle.TEXT_TO_SPEECH}

    request = GoogleActionRequest(patient_id="p", mission_id="m", action=GoogleAction.FCM_SEND_MISSION_NOTIFICATION)
    decision = authorize_google_action(request, [GoogleGrant(patient_id="p", bundle=GrantBundle.FCM_NOTIFY)])
    assert decision.allowed is False
    assert decision.explicit_authorization_required is True


def test_document_ai_only_processes_private_gcs_evidence():
    transport = Transport()
    connector = DocumentAIConnector(
        processor_name="projects/demo/locations/us/processors/proc1",
        token_provider=TokenProvider(),
        transport=transport,
    )
    result = connector.execute(
        GoogleAction.DOCUMENT_AI_PROCESS,
        {"gcs_uri": "gs://private/evidence/lab.pdf", "mime_type": "application/pdf", "evidence_id": "ev1"},
        idempotency_key="a" * 64,
    )
    assert result.evidence_ids == ["ev1"]
    assert "private extracted text" in result.data["document"]["text"]
    assert "private extracted text" not in result.safe_summary
    with pytest.raises(GoogleConnectorError, match="private GCS"):
        connector.execute(GoogleAction.DOCUMENT_AI_PROCESS, {"gcs_uri": "https://example.org/lab.pdf"}, idempotency_key="b" * 64)


def test_healthcare_fhir_and_dicom_paths_are_store_bound_and_injection_safe():
    transport = Transport()
    connector = HealthcareConnector(
        fhir_store="projects/demo/locations/us-central1/datasets/ds/fhirStores/main",
        dicom_store="projects/demo/locations/us-central1/datasets/ds/dicomStores/main",
        token_provider=TokenProvider(),
        transport=transport,
    )
    read = connector.execute(GoogleAction.HEALTHCARE_FHIR_READ, {"resource_type": "Patient", "resource_id": "p1"}, idempotency_key="c" * 64)
    assert read.resource_id == "Patient/p1"
    assert transport.calls[-1][1].endswith("/fhir/Patient/p1")

    write = connector.execute(
        GoogleAction.HEALTHCARE_FHIR_WRITE,
        {"resource": {"resourceType": "Patient", "id": "p1", "active": True}},
        idempotency_key="d" * 64,
    )
    assert write.external_mutation is True
    assert transport.calls[-1][0] == "PUT"

    dicom = connector.execute(GoogleAction.HEALTHCARE_DICOM_METADATA, {"study_uid": "1.2.840.113619.2"}, idempotency_key="e" * 64)
    assert dicom.resource_id == "1.2.840.113619.2"
    with pytest.raises(GoogleConnectorError):
        connector.execute(GoogleAction.HEALTHCARE_FHIR_READ, {"resource_type": "Patient/../../Admin", "resource_id": "p1"}, idempotency_key="f" * 64)
    with pytest.raises(GoogleConnectorError):
        connector.execute(GoogleAction.HEALTHCARE_DICOM_METADATA, {"study_uid": "1.2/../../secret"}, idempotency_key="0" * 64)


def test_fcm_ignores_caller_notification_copy_and_sends_phi_neutral_message():
    transport = Transport()
    connector = FCMConnector(project_id="demo", token_provider=TokenProvider(), transport=transport)
    result = connector.execute(
        GoogleAction.FCM_SEND_MISSION_NOTIFICATION,
        {
            "device_token": "device-registration-token",
            "mission_id": "mission_123",
            "event_type": "result_ready",
            "title": "Cancer result",
            "body": "Your HIV viral load changed",
        },
        idempotency_key="1" * 64,
    )
    sent = transport.calls[-1][3]["message"]
    rendered = str(sent)
    assert "Cancer" not in rendered
    assert "HIV" not in rendered
    assert "mission_123" in rendered
    assert result.external_mutation is True
    assert "device-registration-token" not in result.safe_summary


def test_speech_requires_private_gcs_and_tts_does_not_put_text_in_receipt_summary():
    transport = Transport()
    speech = SpeechConnector(token_provider=TokenProvider(), transport=transport)
    result = speech.execute(
        GoogleAction.SPEECH_RECOGNIZE,
        {"gcs_uri": "gs://private/audio/visit.wav", "language_code": "es-DO", "evidence_id": "audio1"},
        idempotency_key="2" * 64,
    )
    assert result.data["transcripts"][0]["transcript"] == "private transcript"
    assert "private transcript" not in result.safe_summary
    with pytest.raises(GoogleConnectorError, match="private GCS"):
        speech.execute(GoogleAction.SPEECH_RECOGNIZE, {"gcs_uri": "https://public.example/audio.wav"}, idempotency_key="3" * 64)

    tts = TextToSpeechConnector(token_provider=TokenProvider(), transport=transport)
    spoken = "This is private patient-facing education."
    audio = tts.execute(GoogleAction.TEXT_TO_SPEECH_SYNTHESIZE, {"text": spoken}, idempotency_key="4" * 64)
    assert audio.data["audio_content_base64"] == "UklGRg=="
    assert spoken not in audio.safe_summary


def test_veo_is_private_allowlisted_and_returns_operation_not_public_url():
    transport = Transport()
    connector = VeoConnector(
        project_id="demo",
        region="us-central1",
        output_prefix="gs://private-healthia-media/education",
        token_provider=TokenProvider(),
        transport=transport,
    )
    result = connector.execute(
        GoogleAction.VEO_GENERATE,
        {
            "prompt": "Simple patient education animation about how blood pressure is measured; no diagnosis.",
            "patient_storage_key": "patient-demo",
            "model": "veo-3.1-fast-generate-001",
        },
        idempotency_key="5" * 64,
    )
    assert result.external_mutation is True
    assert result.resource_id.endswith("veo123")
    assert result.data["private_output_uri"].startswith("gs://private-healthia-media/education/")
    assert "youtube" not in str(result.data).lower()
    with pytest.raises(GoogleConnectorError, match="allowlist"):
        connector.execute(GoogleAction.VEO_GENERATE, {"prompt": "education", "model": "arbitrary-model"}, idempotency_key="6" * 64)
