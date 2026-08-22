from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Protocol

from pydantic import BaseModel, Field

from healthia_one.google_constellation import GoogleService, new_id
from healthia_one.google_connector_runtime import AccessTokenProvider, GoogleConnectorError
from healthia_one.lazy_google_clients import LazyFirestoreClient


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GoogleOAuthConnection(BaseModel):
    id: str = Field(default_factory=lambda: new_id("gconn"))
    patient_id: str
    google_account: str
    google_subject: str = ""
    granted_scopes: list[str] = Field(default_factory=list)
    secret_version_resource: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OAuthConnectionStore(Protocol):
    def load(self, patient_id: str) -> GoogleOAuthConnection | None: ...
    def save(self, connection: GoogleOAuthConnection) -> None: ...


class MemoryOAuthConnectionStore:
    def __init__(self) -> None:
        self._values: dict[str, GoogleOAuthConnection] = {}

    def load(self, patient_id: str) -> GoogleOAuthConnection | None:
        value = self._values.get(patient_id)
        return value.model_copy(deep=True) if value else None

    def save(self, connection: GoogleOAuthConnection) -> None:
        self._values[connection.patient_id] = connection.model_copy(deep=True)


class FirestoreOAuthConnectionStore(LazyFirestoreClient):
    COLLECTION = "healthia_google_oauth_connections"

    def __init__(self, project: str | None = None) -> None:
        self._configure_firestore(project)

    def load(self, patient_id: str) -> GoogleOAuthConnection | None:
        snapshot = self.client.collection(self.COLLECTION).document(patient_id).get()
        return GoogleOAuthConnection.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, connection: GoogleOAuthConnection) -> None:
        # Only opaque metadata is persisted here. OAuth secret material belongs
        # exclusively in Secret Manager.
        self.client.collection(self.COLLECTION).document(connection.patient_id).set(
            connection.model_dump(mode="json")
        )


SERVICE_SCOPE_HINTS: dict[GoogleService, tuple[str, ...]] = {
    GoogleService.CALENDAR: ("calendar",),
    GoogleService.GMAIL: ("gmail",),
    GoogleService.PEOPLE: ("contacts", "contacts.readonly"),
    GoogleService.DRIVE: ("drive",),
    GoogleService.TASKS: ("tasks",),
    GoogleService.YOUTUBE: ("youtube",),
}


def service_scope_present(connection: GoogleOAuthConnection, service: GoogleService) -> bool:
    if service == GoogleService.MAPS:
        return True
    needles = SERVICE_SCOPE_HINTS.get(service)
    if not needles:
        return True
    scopes = [str(item).lower() for item in connection.granted_scopes]
    return any(any(needle in scope for needle in needles) for scope in scopes)


class SecretPayloadReader(Protocol):
    def read(self, resource_name: str) -> str: ...


class SecretManagerPayloadReader:
    def __init__(self, client=None) -> None:
        if client is None:
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
        self.client = client

    def read(self, resource_name: str) -> str:
        if not resource_name.startswith("projects/") or "/secrets/" not in resource_name or "/versions/" not in resource_name:
            raise GoogleConnectorError("OAuth secret reference is not a Secret Manager version resource")
        response = self.client.access_secret_version(request={"name": resource_name})
        data = bytes(response.payload.data)
        if not data:
            raise GoogleConnectorError("OAuth secret payload is empty")
        return data.decode("utf-8")


class OAuthSecretMaterial(BaseModel):
    refresh_token: str
    client_id: str
    client_secret: str
    token_uri: str = "https://oauth2.googleapis.com/token"


class SecretManagerOAuthTokenProvider(AccessTokenProvider):
    """Mint short-lived Google access tokens without exposing refresh tokens.

    Firestore contains only connection metadata and a Secret Manager resource
    pointer. The Secret Manager client itself is lazy: a process that only reads
    capability state or runs local tests never needs cloud credentials. Secret
    material is decoded into process memory only for token refresh and is never
    returned by public methods or persisted into patient state/prompts/receipts.
    """

    def __init__(
        self,
        *,
        connection_store: OAuthConnectionStore,
        secret_reader: SecretPayloadReader | None = None,
        refresh_request=None,
        cache_seconds: int = 300,
    ) -> None:
        self.connection_store = connection_store
        self.secret_reader = secret_reader
        self.refresh_request = refresh_request
        self.cache_seconds = max(30, min(int(cache_seconds), 300))
        self._cache: dict[tuple[str, GoogleService], tuple[str, datetime]] = {}
        self._lock = threading.RLock()

    def _connection(self, patient_id: str, service: GoogleService) -> GoogleOAuthConnection:
        connection = self.connection_store.load(patient_id)
        if connection is None or not connection.enabled:
            raise GoogleConnectorError("Google account is not connected for this patient")
        if not service_scope_present(connection, service):
            raise GoogleConnectorError(f"Google OAuth connection lacks a scope for {service.value}")
        return connection

    def _reader(self) -> SecretPayloadReader:
        if self.secret_reader is None:
            self.secret_reader = SecretManagerPayloadReader()
        return self.secret_reader

    def _material(self, connection: GoogleOAuthConnection) -> OAuthSecretMaterial:
        raw = self._reader().read(connection.secret_version_resource)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GoogleConnectorError("OAuth Secret Manager payload is not valid JSON") from exc
        try:
            return OAuthSecretMaterial.model_validate(data)
        except Exception as exc:
            raise GoogleConnectorError("OAuth Secret Manager payload is missing required credential fields") from exc

    def _refresh(self, material: OAuthSecretMaterial, scopes: list[str]) -> tuple[str, datetime]:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        credentials = Credentials(
            token=None,
            refresh_token=material.refresh_token,
            token_uri=material.token_uri,
            client_id=material.client_id,
            client_secret=material.client_secret,
            scopes=list(scopes) or None,
        )
        request_value = self.refresh_request or Request()
        try:
            credentials.refresh(request_value)
        except Exception as exc:
            raise GoogleConnectorError(f"Google OAuth token refresh failed: {type(exc).__name__}") from exc
        if not credentials.token:
            raise GoogleConnectorError("Google OAuth refresh returned no access token")
        expiry = credentials.expiry
        if expiry is None:
            expiry = utc_now() + timedelta(seconds=self.cache_seconds)
        elif expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return str(credentials.token), expiry

    def access_token(self, patient_id: str, service: GoogleService) -> str:
        key = (patient_id, service)
        now = utc_now()
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached[1] > now + timedelta(seconds=30):
                return cached[0]
            connection = self._connection(patient_id, service)
            material = self._material(connection)
            token, provider_expiry = self._refresh(material, connection.granted_scopes)
            local_ceiling = now + timedelta(seconds=self.cache_seconds)
            cache_until = min(provider_expiry, local_ceiling)
            self._cache[key] = (token, cache_until)
            return token
