import base64
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from healthia_one.google_constellation import GrantBundle
from healthia_one.google_oauth_credentials import (
    GoogleOAuthConnection,
    MemoryOAuthConnectionStore,
    OAuthSecretMaterial,
)
from healthia_one.google_oauth_web import (
    GOOGLE_AUTH_ENDPOINT,
    GOOGLE_TOKEN_ENDPOINT,
    GOOGLE_USERINFO_ENDPOINT,
    GoogleOAuthBrowserFlow,
    GoogleOAuthFlowError,
    SecretManagerOAuthConnectionSecretWriter,
)


APP_SECRET_RESOURCE = "projects/demo/secrets/google-oauth-client/versions/1"
PATIENT_SECRET_RESOURCE = "projects/demo/secrets/healthia-google-oauth-deadbeef/versions/1"
STATE_SECRET = "s" * 48


class Reader:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.calls = []

    def read(self, resource_name):
        self.calls.append(resource_name)
        return self.values[resource_name]


class Writer:
    def __init__(self, resource=PATIENT_SECRET_RESOURCE):
        self.resource = resource
        self.calls = []

    def write(self, patient_id, material, *, existing_secret_version_resource=""):
        self.calls.append((patient_id, material, existing_secret_version_resource))
        return self.resource


class Transport:
    def __init__(self, token=None, profile=None):
        self.token = token or {
            "access_token": "access-token-not-persisted",
            "refresh_token": "refresh-token-secret",
            "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send",
        }
        self.profile = profile or {
            "sub": "google-subject-123",
            "email": "patient@example.com",
            "email_verified": True,
        }
        self.forms = []
        self.userinfo_tokens = []

    def post_form(self, url, form):
        assert url == GOOGLE_TOKEN_ENDPOINT
        self.forms.append(dict(form))
        return dict(self.token)

    def get_bearer(self, url, access_token):
        assert url == GOOGLE_USERINFO_ENDPOINT
        self.userinfo_tokens.append(access_token)
        return dict(self.profile)


def app_secret_json():
    return json.dumps({"client_id": "client-id.apps.googleusercontent.com", "client_secret": "client-secret-value"})


def flow(*, store=None, reader=None, writer=None, transport=None, state_secret=STATE_SECRET, redirect_uri="https://healthia.example/api/google-constellation/oauth/callback"):
    return GoogleOAuthBrowserFlow(
        connection_store=store or MemoryOAuthConnectionStore(),
        app_secret_resource=APP_SECRET_RESOURCE,
        redirect_uri=redirect_uri,
        state_secret=state_secret,
        secret_reader=reader or Reader({APP_SECRET_RESOURCE: app_secret_json()}),
        secret_writer=writer or Writer(),
        transport=transport or Transport(),
    )


def decode_signed_body(token: str) -> dict:
    _, encoded, _ = token.split(".", 2)
    padded = encoded + "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))


def test_unconfigured_oauth_reports_not_ready_without_crashing_startup():
    value = GoogleOAuthBrowserFlow(
        connection_store=MemoryOAuthConnectionStore(),
        app_secret_resource="",
        redirect_uri="",
        state_secret="",
        secret_reader=Reader(),
        secret_writer=Writer(),
        transport=Transport(),
    )
    readiness = value.readiness()
    assert readiness["ready"] is False
    assert readiness["client_secret_resource_configured"] is False
    assert readiness["redirect_uri_configured"] is False
    assert readiness["state_secret_configured"] is False
    with pytest.raises(GoogleOAuthFlowError, match="state secret"):
        value.begin("patient_demo")


def test_begin_uses_pkce_state_offline_access_and_incremental_narrow_scopes_without_secret_or_patient_id_in_url():
    value = flow()
    authorization_url, cookie = value.begin(
        "patient_demo",
        f"{GrantBundle.GMAIL_READ_RELEVANT.value},{GrantBundle.CALENDAR_READ.value}",
    )
    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == GOOGLE_AUTH_ENDPOINT
    assert query["access_type"] == ["offline"]
    assert query["include_granted_scopes"] == ["true"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) >= 43
    assert query["state"][0]
    assert query["prompt"] == ["consent"]
    scopes = set(query["scope"][0].split())
    assert "openid" in scopes
    assert "email" in scopes
    assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
    assert "https://www.googleapis.com/auth/calendar.freebusy" in scopes
    assert "https://www.googleapis.com/auth/gmail.send" not in scopes
    assert "client-secret-value" not in authorization_url
    state_body = decode_signed_body(query["state"][0])
    assert "patient_id" not in state_body["payload"]
    assert "patient_demo" not in json.dumps(state_body)
    assert set(state_body["payload"]) == {"flow_nonce", "bundles"}
    assert cookie.startswith("hgo1.")


def test_complete_binds_stable_subject_and_writes_refresh_secret_only_through_secret_writer():
    store = MemoryOAuthConnectionStore()
    reader = Reader({APP_SECRET_RESOURCE: app_secret_json()})
    writer = Writer()
    transport = Transport()
    value = flow(store=store, reader=reader, writer=writer, transport=transport)
    authorization_url, cookie = value.begin("patient_demo", GrantBundle.GMAIL_READ_RELEVANT.value)
    state = parse_qs(urlparse(authorization_url).query)["state"][0]

    connection = value.complete("patient_demo", state=state, code="one-time-code", pkce_cookie=cookie)
    saved = store.load("patient_demo")
    assert connection.google_subject == "google-subject-123"
    assert saved.google_subject == "google-subject-123"
    assert saved.google_account == "patient@example.com"
    assert saved.secret_version_resource == PATIENT_SECRET_RESOURCE
    assert "refresh-token-secret" not in saved.model_dump_json()
    assert "access-token-not-persisted" not in saved.model_dump_json()
    assert writer.calls[0][0] == "patient_demo"
    assert writer.calls[0][1].refresh_token == "refresh-token-secret"
    assert writer.calls[0][2] == ""
    form = transport.forms[0]
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "one-time-code"
    assert len(form["code_verifier"]) >= 43
    assert transport.userinfo_tokens == ["access-token-not-persisted"]


def test_tampered_state_and_pkce_cookie_are_rejected_before_token_exchange():
    transport = Transport()
    value = flow(transport=transport)
    authorization_url, cookie = value.begin("patient_demo")
    state = parse_qs(urlparse(authorization_url).query)["state"][0]

    with pytest.raises(GoogleOAuthFlowError):
        value.complete("patient_demo", state=state + "x", code="code", pkce_cookie=cookie)
    with pytest.raises(GoogleOAuthFlowError):
        value.complete("patient_demo", state=state, code="code", pkce_cookie=cookie + "x")
    assert transport.forms == []


def test_pkce_cookie_binds_state_to_current_patient_session_even_though_provider_state_is_patient_opaque():
    transport = Transport()
    value = flow(transport=transport)
    authorization_url, cookie = value.begin("patient_demo")
    state = parse_qs(urlparse(authorization_url).query)["state"][0]

    with pytest.raises(GoogleOAuthFlowError, match="patient session"):
        value.complete("patient_other", state=state, code="code", pkce_cookie=cookie)
    assert transport.forms == []


def test_incremental_same_account_preserves_existing_refresh_token_when_google_omits_a_new_one():
    store = MemoryOAuthConnectionStore()
    store.save(
        GoogleOAuthConnection(
            patient_id="patient_demo",
            google_account="patient@example.com",
            google_subject="google-subject-123",
            granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            secret_version_resource=PATIENT_SECRET_RESOURCE,
        )
    )
    old_material = OAuthSecretMaterial(
        refresh_token="old-refresh-token",
        client_id="client-id.apps.googleusercontent.com",
        client_secret="client-secret-value",
    )
    reader = Reader(
        {
            APP_SECRET_RESOURCE: app_secret_json(),
            PATIENT_SECRET_RESOURCE: old_material.model_dump_json(),
        }
    )
    writer = Writer("projects/demo/secrets/healthia-google-oauth-deadbeef/versions/2")
    transport = Transport(
        token={
            "access_token": "incremental-access",
            "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.freebusy",
        }
    )
    value = flow(store=store, reader=reader, writer=writer, transport=transport)
    authorization_url, cookie = value.begin("patient_demo", GrantBundle.CALENDAR_READ.value)
    query = parse_qs(urlparse(authorization_url).query)
    assert "prompt" not in query
    state = query["state"][0]

    connection = value.complete("patient_demo", state=state, code="incremental-code", pkce_cookie=cookie)
    assert connection.secret_version_resource.endswith("/versions/2")
    assert writer.calls[0][1].refresh_token == "old-refresh-token"
    assert writer.calls[0][2] == PATIENT_SECRET_RESOURCE


def test_different_google_subject_is_rejected_until_explicit_disconnect():
    store = MemoryOAuthConnectionStore()
    store.save(
        GoogleOAuthConnection(
            patient_id="patient_demo",
            google_account="old@example.com",
            google_subject="subject-old",
            granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            secret_version_resource=PATIENT_SECRET_RESOURCE,
        )
    )
    writer = Writer()
    transport = Transport(profile={"sub": "subject-new", "email": "new@example.com", "email_verified": True})
    reader = Reader({APP_SECRET_RESOURCE: app_secret_json()})
    value = flow(store=store, reader=reader, writer=writer, transport=transport)
    authorization_url, cookie = value.begin("patient_demo")
    state = parse_qs(urlparse(authorization_url).query)["state"][0]

    with pytest.raises(GoogleOAuthFlowError, match="different Google account"):
        value.complete("patient_demo", state=state, code="code", pkce_cookie=cookie)
    assert writer.calls == []
    assert store.load("patient_demo").google_subject == "subject-old"


def test_disconnect_disables_local_connection_without_claiming_provider_revocation():
    store = MemoryOAuthConnectionStore()
    store.save(
        GoogleOAuthConnection(
            patient_id="patient_demo",
            google_account="patient@example.com",
            google_subject="subject",
            granted_scopes=[],
            secret_version_resource=PATIENT_SECRET_RESOURCE,
        )
    )
    value = flow(store=store)
    disconnected = value.disconnect("patient_demo")
    assert disconnected.enabled is False
    assert store.load("patient_demo").enabled is False


class NotFound(Exception):
    pass


class SecretClient:
    def __init__(self):
        self.created = []
        self.versions = []

    def get_secret(self, request):
        raise NotFound()

    def create_secret(self, request):
        self.created.append(request)
        return SimpleNamespace(name=f"{request['parent']}/secrets/{request['secret_id']}")

    def add_secret_version(self, request):
        self.versions.append(request)
        return SimpleNamespace(name=f"{request['parent']}/versions/1")


def test_secret_manager_writer_uses_hashed_patient_secret_name_and_returns_only_version_reference():
    client = SecretClient()
    writer = SecretManagerOAuthConnectionSecretWriter("demo", client=client)
    resource = writer.write(
        "patient_sensitive_identifier",
        OAuthSecretMaterial(
            refresh_token="secret-refresh",
            client_id="client-id.apps.googleusercontent.com",
            client_secret="client-secret-value",
        ),
    )
    assert resource.startswith("projects/demo/secrets/healthia-google-oauth-")
    assert resource.endswith("/versions/1")
    assert "patient_sensitive_identifier" not in resource
    assert "patient_sensitive_identifier" not in json.dumps(client.created)
    payload = json.loads(client.versions[0]["payload"]["data"].decode("utf-8"))
    assert payload["refresh_token"] == "secret-refresh"
