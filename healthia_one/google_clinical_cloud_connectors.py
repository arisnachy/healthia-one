from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib import parse

from healthia_one.google_connector_runtime import ConnectorResult, GoogleConnectorError, JsonTransport
from healthia_one.google_constellation import GoogleAction, GoogleService


_CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_SAFE_FHIR_TYPE = re.compile(r"^[A-Z][A-Za-z0-9]{1,63}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9\-.]{1,128}$")
_SAFE_DICOM_UID = re.compile(r"^[0-9.]{1,128}$")


class ServerAdcTokenProvider:
    """Short-lived server token provider using Application Default Credentials.

    Patient OAuth refresh tokens are deliberately not used here. These APIs run
    as the Cloud workload identity, while HealthIA's grant/action policy remains
    the independent patient-consent boundary above the connector.
    """

    def __init__(self) -> None:
        self._credentials: dict[tuple[str, ...], Any] = {}

    def token(self, scopes: tuple[str, ...] = (_CLOUD_SCOPE,)) -> str:
        from google.auth import default
        from google.auth.transport.requests import Request

        normalized = tuple(sorted(set(scopes)))
        credentials = self._credentials.get(normalized)
        if credentials is None:
            credentials, _ = default(scopes=list(normalized))
            self._credentials[normalized] = credentials
        if not credentials.valid or not credentials.token:
            credentials.refresh(Request())
        token = str(credentials.token or "")
        if not token:
            raise GoogleConnectorError("Google ADC did not produce a short-lived access token")
        return token


class AdcConnectorBase:
    service: GoogleService

    def __init__(self, token_provider: ServerAdcTokenProvider | None = None, transport: JsonTransport | None = None) -> None:
        self.token_provider = token_provider or ServerAdcTokenProvider()
        self.transport = transport or JsonTransport()

    def _headers(self, *, fcm: bool = False) -> dict[str, str]:
        scopes = (_CLOUD_SCOPE, _FCM_SCOPE) if fcm else (_CLOUD_SCOPE,)
        return {"Authorization": f"Bearer {self.token_provider.token(scopes)}"}


class DocumentAIConnector(AdcConnectorBase):
    service = GoogleService.DOCUMENT_AI

    def __init__(self, processor_name: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.processor_name = (processor_name or os.getenv("HEALTHIA_DOCUMENT_AI_PROCESSOR", "")).strip()

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action != GoogleAction.DOCUMENT_AI_PROCESS:
            raise GoogleConnectorError(f"Unsupported Document AI action: {action}")
        if not self.processor_name.startswith("projects/") or "/locations/" not in self.processor_name or "/processors/" not in self.processor_name:
            raise GoogleConnectorError("HEALTHIA_DOCUMENT_AI_PROCESSOR is not configured with a processor resource")
        gcs_uri = str(payload.get("gcs_uri") or "").strip()
        mime_type = str(payload.get("mime_type") or "application/pdf").strip()
        if not gcs_uri.startswith("gs://"):
            raise GoogleConnectorError("Document AI accepts only a private GCS evidence URI in this HealthIA connector")
        body: dict[str, Any] = {
            "gcsDocument": {"gcsUri": gcs_uri, "mimeType": mime_type},
            "imagelessMode": bool(payload.get("imageless_mode", True)),
        }
        field_mask = str(payload.get("field_mask") or "text,entities,pages.pageNumber,pages.formFields,pages.tables").strip()
        if field_mask:
            body["fieldMask"] = field_mask
        url = f"https://documentai.googleapis.com/v1/{self.processor_name}:process"
        result = self.transport.call("POST", url, headers=self._headers(), body=body)
        document = result.get("document") or {}
        page_count = len(document.get("pages") or [])
        entity_count = len(document.get("entities") or [])
        return ConnectorResult(
            resource_id=self.processor_name,
            safe_summary=f"Document AI processed private evidence ({page_count} page(s), {entity_count} structured entity candidate(s)).",
            data={"document": document, "humanReviewStatus": result.get("humanReviewStatus")},
            evidence_ids=[str(payload.get("evidence_id") or "")] if payload.get("evidence_id") else [],
        )


class HealthcareConnector(AdcConnectorBase):
    service = GoogleService.HEALTHCARE

    def __init__(self, fhir_store: str | None = None, dicom_store: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.fhir_store = (fhir_store or os.getenv("HEALTHIA_FHIR_STORE", "")).strip()
        self.dicom_store = (dicom_store or os.getenv("HEALTHIA_DICOM_STORE", "")).strip()

    @staticmethod
    def _resource_type(value: Any) -> str:
        item = str(value or "").strip()
        if not _SAFE_FHIR_TYPE.fullmatch(item):
            raise GoogleConnectorError("FHIR resource type is invalid")
        return item

    @staticmethod
    def _resource_id(value: Any) -> str:
        item = str(value or "").strip()
        if not _SAFE_ID.fullmatch(item):
            raise GoogleConnectorError("FHIR resource id is invalid")
        return item

    def _fhir_base(self) -> str:
        if not self.fhir_store.startswith("projects/") or "/fhirStores/" not in self.fhir_store:
            raise GoogleConnectorError("HEALTHIA_FHIR_STORE is not configured")
        return f"https://healthcare.googleapis.com/v1/{self.fhir_store}/fhir"

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        headers = {**self._headers(), "Content-Type": "application/fhir+json"}
        if action == GoogleAction.HEALTHCARE_FHIR_READ:
            resource_type = self._resource_type(payload.get("resource_type"))
            resource_id = self._resource_id(payload.get("resource_id"))
            result = self.transport.call("GET", f"{self._fhir_base()}/{resource_type}/{resource_id}", headers=headers)
            return ConnectorResult(
                resource_id=f"{resource_type}/{resource_id}",
                safe_summary=f"Read one authorized {resource_type} resource through the HealthIA FHIR gateway.",
                data={"resource": result},
            )
        if action == GoogleAction.HEALTHCARE_FHIR_SEARCH:
            resource_type = self._resource_type(payload.get("resource_type"))
            params = payload.get("query") or {}
            if not isinstance(params, dict) or len(params) > 12:
                raise GoogleConnectorError("FHIR search query is invalid or too broad")
            clean: dict[str, str] = {}
            for key, value in params.items():
                key_text = str(key or "").strip()
                if not key_text or len(key_text) > 80 or any(ch in key_text for ch in "\r\n&="):
                    raise GoogleConnectorError("FHIR search parameter name is invalid")
                clean[key_text] = str(value)[:500]
            query = parse.urlencode(clean)
            url = f"{self._fhir_base()}/{resource_type}"
            if query:
                url += f"?{query}"
            result = self.transport.call("GET", url, headers=headers)
            entries = result.get("entry") or []
            return ConnectorResult(
                resource_id=resource_type,
                safe_summary=f"FHIR search returned {len(entries)} authorized resource candidate(s).",
                data={"bundle": result},
            )
        if action == GoogleAction.HEALTHCARE_FHIR_WRITE:
            resource = payload.get("resource") or {}
            if not isinstance(resource, dict):
                raise GoogleConnectorError("FHIR write requires a JSON resource object")
            resource_type = self._resource_type(resource.get("resourceType") or payload.get("resource_type"))
            resource_id_raw = resource.get("id") or payload.get("resource_id")
            if resource_id_raw:
                resource_id = self._resource_id(resource_id_raw)
                url = f"{self._fhir_base()}/{resource_type}/{resource_id}"
                result = self.transport.call("PUT", url, headers=headers, body=resource)
                resource_ref = f"{resource_type}/{resource_id}"
            else:
                url = f"{self._fhir_base()}/{resource_type}"
                result = self.transport.call("POST", url, headers=headers, body=resource)
                resource_ref = f"{resource_type}/{str(result.get('id') or '')}".rstrip("/")
            return ConnectorResult(
                resource_id=resource_ref,
                safe_summary=f"Wrote one exactly authorized {resource_type} resource through the FHIR gateway.",
                data={"resource": result},
                external_mutation=True,
            )
        if action == GoogleAction.HEALTHCARE_DICOM_METADATA:
            if not self.dicom_store.startswith("projects/") or "/dicomStores/" not in self.dicom_store:
                raise GoogleConnectorError("HEALTHIA_DICOM_STORE is not configured")
            study_uid = str(payload.get("study_uid") or "").strip()
            if not _SAFE_DICOM_UID.fullmatch(study_uid):
                raise GoogleConnectorError("DICOM study UID is invalid")
            url = f"https://healthcare.googleapis.com/v1/{self.dicom_store}/dicomWeb/studies/{parse.quote(study_uid, safe='.')}/metadata"
            result = self.transport.call("GET", url, headers=self._headers())
            metadata = result if isinstance(result, list) else result.get("instances") or result
            count = len(metadata) if isinstance(metadata, list) else 1
            return ConnectorResult(
                resource_id=study_uid,
                safe_summary=f"Retrieved authorized DICOM metadata for one study ({count} metadata record(s)).",
                data={"metadata": metadata},
            )
        raise GoogleConnectorError(f"Unsupported Cloud Healthcare action: {action}")


class FCMConnector(AdcConnectorBase):
    service = GoogleService.FCM

    def __init__(self, project_id: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.project_id = (project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")).strip()

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action != GoogleAction.FCM_SEND_MISSION_NOTIFICATION:
            raise GoogleConnectorError(f"Unsupported FCM action: {action}")
        if not self.project_id:
            raise GoogleConnectorError("GOOGLE_CLOUD_PROJECT is required for FCM")
        token = str(payload.get("device_token") or "").strip()
        mission_id = str(payload.get("mission_id") or "").strip()
        event_type = str(payload.get("event_type") or "mission_update").strip()[:80]
        if not token or not mission_id:
            raise GoogleConnectorError("FCM notification requires a device token and mission id")
        # Caller text is intentionally ignored. Keep lock-screen copy PHI-neutral.
        body = {
            "message": {
                "token": token,
                "notification": {
                    "title": "HealthIA update",
                    "body": "You have a HealthIA update. Open the app to review it privately.",
                },
                "data": {
                    "mission_id": mission_id,
                    "event_type": event_type,
                    "open_view": "missions",
                },
                "android": {"priority": "HIGH"},
            }
        }
        result = self.transport.call(
            "POST",
            f"https://fcm.googleapis.com/v1/projects/{parse.quote(self.project_id, safe='')}/messages:send",
            headers=self._headers(fcm=True),
            body=body,
        )
        name = str(result.get("name") or "")
        return ConnectorResult(
            resource_id=name,
            safe_summary="Sent one PHI-neutral mission notification through FCM.",
            data={"message_name": name},
            external_mutation=True,
        )


class SpeechConnector(AdcConnectorBase):
    service = GoogleService.SPEECH

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action != GoogleAction.SPEECH_RECOGNIZE:
            raise GoogleConnectorError(f"Unsupported Speech action: {action}")
        gcs_uri = str(payload.get("gcs_uri") or "").strip()
        if not gcs_uri.startswith("gs://"):
            raise GoogleConnectorError("Speech recognition accepts only a private GCS audio URI")
        language_code = str(payload.get("language_code") or "es-DO").strip()[:32]
        config: dict[str, Any] = {
            "languageCode": language_code,
            "enableAutomaticPunctuation": True,
            "enableWordTimeOffsets": False,
        }
        if payload.get("encoding"):
            config["encoding"] = str(payload["encoding"])
        if payload.get("sample_rate_hertz"):
            config["sampleRateHertz"] = int(payload["sample_rate_hertz"])
        result = self.transport.call(
            "POST",
            "https://speech.googleapis.com/v1/speech:recognize",
            headers=self._headers(),
            body={"config": config, "audio": {"uri": gcs_uri}},
        )
        transcripts: list[dict[str, Any]] = []
        for item in result.get("results") or []:
            alternatives = item.get("alternatives") or []
            if alternatives:
                best = alternatives[0]
                transcripts.append({"transcript": str(best.get("transcript") or ""), "confidence": best.get("confidence")})
        return ConnectorResult(
            safe_summary=f"Transcribed private audio into {len(transcripts)} speech segment(s).",
            data={"transcripts": transcripts, "request_id": str(result.get("requestId") or "")},
            evidence_ids=[str(payload.get("evidence_id") or "")] if payload.get("evidence_id") else [],
        )


class TextToSpeechConnector(AdcConnectorBase):
    service = GoogleService.TEXT_TO_SPEECH

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action != GoogleAction.TEXT_TO_SPEECH_SYNTHESIZE:
            raise GoogleConnectorError(f"Unsupported Text-to-Speech action: {action}")
        text = str(payload.get("text") or "").strip()
        if not text or len(text) > 5000:
            raise GoogleConnectorError("Text-to-Speech input must contain 1-5000 characters")
        language_code = str(payload.get("language_code") or "es-US").strip()[:32]
        body = {
            "input": {"text": text},
            "voice": {"languageCode": language_code},
            "audioConfig": {"audioEncoding": str(payload.get("audio_encoding") or "MP3")},
        }
        result = self.transport.call("POST", "https://texttospeech.googleapis.com/v1/text:synthesize", headers=self._headers(), body=body)
        audio_content = str(result.get("audioContent") or "")
        if not audio_content:
            raise GoogleConnectorError("Text-to-Speech returned no audio content")
        return ConnectorResult(
            safe_summary="Synthesized one private patient-facing audio response.",
            data={"audio_content_base64": audio_content, "audio_encoding": body["audioConfig"]["audioEncoding"]},
        )


class VeoConnector(AdcConnectorBase):
    service = GoogleService.VEO

    def __init__(self, project_id: str | None = None, region: str | None = None, output_prefix: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.project_id = (project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")).strip()
        self.region = (region or os.getenv("HEALTHIA_VEO_REGION", "us-central1")).strip()
        self.output_prefix = (output_prefix or os.getenv("HEALTHIA_VEO_PRIVATE_GCS_PREFIX", "")).rstrip("/")

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action != GoogleAction.VEO_GENERATE:
            raise GoogleConnectorError(f"Unsupported Veo action: {action}")
        if not self.project_id or not self.output_prefix.startswith("gs://"):
            raise GoogleConnectorError("Veo requires GOOGLE_CLOUD_PROJECT and HEALTHIA_VEO_PRIVATE_GCS_PREFIX")
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt or len(prompt) > 3000:
            raise GoogleConnectorError("Veo educational prompt must contain 1-3000 characters")
        model = str(payload.get("model") or "veo-3.1-fast-generate-001").strip()
        allowed_models = {"veo-3.1-generate-001", "veo-3.1-fast-generate-001", "veo-3.0-generate-001", "veo-3.0-fast-generate-001"}
        if model not in allowed_models:
            raise GoogleConnectorError("Veo model is outside the HealthIA education allowlist")
        output_uri = f"{self.output_prefix}/{parse.quote(str(payload.get('patient_storage_key') or 'education'), safe='-_')}/{idempotency_key[:20]}/"
        body = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "storageUri": output_uri,
                "sampleCount": 1,
                "durationSeconds": min(max(int(payload.get("duration_seconds", 8)), 4), 8),
                "resolution": str(payload.get("resolution") or "720p"),
                "personGeneration": "dont_allow",
            },
        }
        endpoint = (
            f"https://{self.region}-aiplatform.googleapis.com/v1/projects/{parse.quote(self.project_id, safe='')}"
            f"/locations/{parse.quote(self.region, safe='')}/publishers/google/models/{parse.quote(model, safe='-.')}:predictLongRunning"
        )
        result = self.transport.call("POST", endpoint, headers=self._headers(), body=body)
        operation_name = str(result.get("name") or "")
        if not operation_name:
            raise GoogleConnectorError("Veo returned no long-running operation name")
        return ConnectorResult(
            resource_id=operation_name,
            safe_summary="Started one explicitly authorized private educational video generation job.",
            data={"operation_name": operation_name, "private_output_uri": output_uri, "model": model},
            external_mutation=True,
        )
