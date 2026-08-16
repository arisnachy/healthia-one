import json
from datetime import timedelta

import pytest

from healthia_one.google_connector_runtime import GoogleConnectorError
from healthia_one.google_constellation import GoogleService
from healthia_one.google_oauth_credentials import (
    GoogleOAuthConnection,
    MemoryOAuthConnectionStore,
    OAuthSecretMaterial,
    SecretManagerOAuthTokenProvider,
    service_scope_present,
    utc_now,
)


class SecretReader:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def read(self, resource_name):
        self.calls.append(resource_name)
        return self.payload


class TokenProvider(SecretManagerOAuthTokenProvider):
    def __init__(self, *, token="access-1", **kwargs):
        super().__init__(**kwargs)
        self.token = token
        self.refresh_calls = 0

    def _refresh(self, material, scopes):
        self.refresh_calls += 1
        assert material.refresh_token == "refresh-secret"
        assert material.client_secret == "client-secret"
        return self.token, utc_now() + timedelta(hours=1)


def connection(scopes=None):
    return GoogleOAuthConnection(
        patient_id="patient_demo",
        google_account="patient@example.com",
        granted_scopes=scopes or ["https://www.googleapis.com/auth/gmail.send"],
        secret_version_resource="projects/demo/secrets/google-oauth-patient-demo/versions/1",
    )


def secret_payload():
    return json.dumps(
        {
            "refresh_token": "refresh-secret",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


def test_connection_metadata_contains_only_secret_reference_not_refresh_token():
    item = connection()
    dumped = item.model_dump(mode="json")
    assert "refresh_token" not in dumped
    assert "client_secret" not in dumped
    assert dumped["secret_version_resource"].startswith("projects/")


def test_service_scope_must_be_present_before_secret_is_read():
    store = MemoryOAuthConnectionStore()
    store.save(connection(scopes=["https://www.googleapis.com/auth/calendar.events"]))
    secret = SecretReader(secret_payload())
    provider = TokenProvider(connection_store=store, secret_reader=secret)
    with pytest.raises(GoogleConnectorError, match="lacks a scope"):
        provider.access_token("patient_demo", GoogleService.GMAIL)
    assert secret.calls == []


def test_token_provider_reads_secret_only_on_demand_and_caches_short_lived_access_token():
    store = MemoryOAuthConnectionStore()
    store.save(connection())
    secret = SecretReader(secret_payload())
    provider = TokenProvider(connection_store=store, secret_reader=secret, cache_seconds=120)

    first = provider.access_token("patient_demo", GoogleService.GMAIL)
    second = provider.access_token("patient_demo", GoogleService.GMAIL)

    assert first == second == "access-1"
    assert provider.refresh_calls == 1
    assert secret.calls == ["projects/demo/secrets/google-oauth-patient-demo/versions/1"]


def test_missing_or_disabled_connection_fails_before_secret_access():
    store = MemoryOAuthConnectionStore()
    secret = SecretReader(secret_payload())
    provider = TokenProvider(connection_store=store, secret_reader=secret)
    with pytest.raises(GoogleConnectorError, match="not connected"):
        provider.access_token("patient_demo", GoogleService.GMAIL)

    item = connection()
    item.enabled = False
    store.save(item)
    with pytest.raises(GoogleConnectorError, match="not connected"):
        provider.access_token("patient_demo", GoogleService.GMAIL)
    assert secret.calls == []


def test_oauth_secret_schema_requires_refresh_client_id_and_client_secret():
    with pytest.raises(Exception):
        OAuthSecretMaterial.model_validate({"refresh_token": "x"})


def test_people_scope_does_not_imply_gmail_scope():
    item = connection(scopes=["https://www.googleapis.com/auth/contacts.readonly"])
    assert service_scope_present(item, GoogleService.PEOPLE) is True
    assert service_scope_present(item, GoogleService.GMAIL) is False
