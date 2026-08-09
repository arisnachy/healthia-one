from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Request as FastAPIRequest
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from healthia_one.auth import current_patient_id
from healthia_one.config import Settings
from healthia_one.google_constellation import GrantBundle
from healthia_one.google_oauth_credentials import (
    GoogleOAuthConnection,
    OAuthConnectionStore,
    OAuthSecretMaterial,
    SecretManagerPayloadReader,
)


GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
OAUTH_COOKIE = "healthia_google_oauth_pkce"


OAUTH_SCOPES_BY_BUNDLE: dict[GrantBundle, tuple[str, ...]] = {
    GrantBundle.CALENDAR_READ: ("https://www.googleapis.com/auth/calendar.freebusy",),
    GrantBundle.CALENDAR_WRITE: ("https://www.googleapis.com/auth/calendar.events",),
    GrantBundle.GMAIL_READ_RELEVANT: ("https://www.googleapis.com/auth/gmail.readonly",),
    GrantBundle.GMAIL_SEND: ("https://www.googleapis.com/auth/gmail.send",),
    GrantBundle.CONTACTS_READ: ("https://www.googleapis.com/auth/contacts.readonly",),
    GrantBundle.DRIVE_EXPORT: ("https://www.googleapis.com/auth/drive.file",),
    GrantBundle.TASKS_WRITE: ("https://www.googleapis.com/auth/tasks",),
    GrantBundle.YOUTUBE_UPLOAD: ("https://www.googleapis.com/auth/youtube.upload",),
}

DEFAULT_CONNECT_BUNDLES: tuple[GrantBundle, ...] = (
    GrantBundle.GMAIL_READ_RELEVANT,
    GrantBundle.GMAIL_SEND,
    GrantBundle.CALENDAR_READ,
    GrantBundle.CALENDAR_WRITE,
    GrantBundle.TASKS_WRITE,
)


class GoogleOAuthFlowError(ValueError):
    pass


class GoogleOAuthAppSecret(BaseModel):
    client_id: str = Field(min_length=10, max_length=500)
    client_secret: str = Field(min_length=8, max_length=500)


class OAuthHttpTransport(Protocol):
    def post_form(self, url: str, form: dict[str, str]) -> dict[str, Any]: ...
    def get_bearer(self, url: str, access_token: str) -> dict[str, Any]: ...


class UrllibOAuthHttpTransport:
    @staticmethod
    def _json_request(request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed Google endpoints only
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                status = str(payload.get("error") or payload.get("error_description") or "oauth_http_error")
            except Exception:
                status = "oauth_http_error"
            raise GoogleOAuthFlowError(f"Google OAuth request failed: {status}") from exc
        except URLError as exc:
            raise GoogleOAuthFlowError("Google OAuth endpoint is temporarily unreachable") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GoogleOAuthFlowError("Google OAuth endpoint returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise GoogleOAuthFlowError("Google OAuth endpoint returned an invalid payload")
        return payload

    def post_form(self, url: str, form: dict[str, str]) -> dict[str, Any]:
        if url != GOOGLE_TOKEN_ENDPOINT:
            raise GoogleOAuthFlowError("Unexpected OAuth token endpoint")
        body = urlencode(form).encode("utf-8")
        request = Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._json_request(request)

    def get_bearer(self, url: str, access_token: str) -> dict[str, Any]:
        if url != GOOGLE_USERINFO_ENDPOINT:
            raise GoogleOAuthFlowError("Unexpected OAuth userinfo endpoint")
        request = Request(url, method="GET", headers={"Authorization": f"Bearer {access_token}"})
        return self._json_request(request)


class OAuthConnectionSecretWriter(Protocol):
    def write(
        self,
        patient_id: str,
        material: OAuthSecretMaterial,
        *,
        existing_secret_version_resource: str = "",
    ) -> str: ...


class SecretManagerOAuthConnectionSecretWriter:
    """Persist one opaque refresh-token bundle per patient in Secret Manager.

    Secret names use a patient-id hash rather than a clinical/user identifier.
    Existing connections append a new version to the same secret. Runtime IAM
    must explicitly allow secret create/add-version; the web flow fails closed
    when that provisioning is absent.
    """

    def __init__(self, project_id: str, client=None) -> None:
        self.project_id = str(project_id or "").strip()
        self.client = client

    def _client(self):
        if self.client is None:
            from google.cloud import secretmanager

            self.client = secretmanager.SecretManagerServiceClient()
        return self.client

    def _secret_name(self, patient_id: str, existing: str) -> str:
        if existing:
            marker = "/versions/"
            if not existing.startswith(f"projects/{self.project_id}/secrets/") or marker not in existing:
                raise GoogleOAuthFlowError("Existing OAuth secret reference is outside the configured project")
            return existing.split(marker, 1)[0]
        digest = hashlib.sha256(patient_id.encode("utf-8")).hexdigest()[:24]
        return f"projects/{self.project_id}/secrets/healthia-google-oauth-{digest}"

    def write(
        self,
        patient_id: str,
        material: OAuthSecretMaterial,
        *,
        existing_secret_version_resource: str = "",
    ) -> str:
        if not self.project_id:
            raise GoogleOAuthFlowError("GOOGLE_CLOUD_PROJECT is required for OAuth Secret Manager storage")
        client = self._client()
        secret_name = self._secret_name(patient_id, existing_secret_version_resource)
        if not existing_secret_version_resource:
            try:
                client.get_secret(request={"name": secret_name})
            except Exception as exc:
                # Avoid importing google.api_core at module load. Only a true
                # NotFound is allowed to fall through to creation.
                if type(exc).__name__ != "NotFound":
                    raise GoogleOAuthFlowError(f"OAuth secret lookup failed: {type(exc).__name__}") from exc
                secret_id = secret_name.rsplit("/", 1)[-1]
                try:
                    client.create_secret(
                        request={
                            "parent": f"projects/{self.project_id}",
                            "secret_id": secret_id,
                            "secret": {"replication": {"automatic": {}}},
                        }
                    )
                except Exception as create_exc:
                    raise GoogleOAuthFlowError(
                        f"OAuth secret creation failed: {type(create_exc).__name__}"
                    ) from create_exc
        raw = json.dumps(material.model_dump(mode="json"), separators=(",", ":")).encode("utf-8")
        try:
            version = client.add_secret_version(
                request={"parent": secret_name, "payload": {"data": raw}}
            )
        except Exception as exc:
            raise GoogleOAuthFlowError(f"OAuth secret version write failed: {type(exc).__name__}") from exc
        resource = str(getattr(version, "name", "") or "").strip()
        if not resource.startswith(f"{secret_name}/versions/"):
            raise GoogleOAuthFlowError("Secret Manager returned an invalid OAuth secret version resource")
        return resource


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signed_token(secret: bytes, purpose: str, payload: dict[str, Any], ttl_seconds: int = 600) -> str:
    now = int(time.time())
    body = {
        "v": 1,
        "purpose": purpose,
        "iat": now,
        "exp": now + min(max(int(ttl_seconds), 60), 900),
        "nonce": secrets.token_hex(16),
        "payload": payload,
    }
    encoded = _b64encode(json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64encode(hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest())
    return f"hgo1.{encoded}.{signature}"


def _verify_signed_token(secret: bytes, token: str, purpose: str) -> dict[str, Any]:
    try:
        version, encoded, signature = token.split(".", 2)
        if version != "hgo1":
            raise ValueError
        expected = _b64encode(hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        body = json.loads(_b64decode(encoded))
        if body.get("purpose") != purpose or int(body.get("exp", 0)) <= int(time.time()):
            raise ValueError
        payload = body.get("payload")
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except Exception as exc:
        raise GoogleOAuthFlowError("Google OAuth state is invalid or expired") from exc


def _pkce_challenge(verifier: str) -> str:
    return _b64encode(hashlib.sha256(verifier.encode("ascii")).digest())


def _normalize_bundles(raw: str | list[str] | tuple[str, ...]) -> tuple[GrantBundle, ...]:
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        values = [str(item).strip() for item in raw if str(item).strip()]
    if not values:
        return DEFAULT_CONNECT_BUNDLES
    bundles: list[GrantBundle] = []
    for value in values:
        try:
            bundle = GrantBundle(value)
        except ValueError as exc:
            raise GoogleOAuthFlowError(f"Unsupported Google OAuth grant bundle: {value}") from exc
        if bundle not in OAUTH_SCOPES_BY_BUNDLE:
            raise GoogleOAuthFlowError(f"Grant bundle does not use patient Google OAuth: {value}")
        if bundle not in bundles:
            bundles.append(bundle)
    return tuple(bundles)


def oauth_scopes_for_bundles(bundles: tuple[GrantBundle, ...]) -> list[str]:
    scopes = {"openid", "email"}
    for bundle in bundles:
        scopes.update(OAUTH_SCOPES_BY_BUNDLE[bundle])
    return sorted(scopes)


class GoogleOAuthBrowserFlow:
    def __init__(
        self,
        *,
        connection_store: OAuthConnectionStore,
        app_secret_resource: str,
        redirect_uri: str,
        state_secret: str | bytes,
        secret_reader=None,
        secret_writer: OAuthConnectionSecretWriter,
        transport: OAuthHttpTransport | None = None,
    ) -> None:
        self.connection_store = connection_store
        self.app_secret_resource = str(app_secret_resource or "").strip()
        self.redirect_uri = str(redirect_uri or "").strip()
        self.state_secret = (
            state_secret.encode("utf-8") if isinstance(state_secret, str) else bytes(state_secret)
        )
        self.secret_reader = secret_reader or SecretManagerPayloadReader()
        self.secret_writer = secret_writer
        self.transport = transport or UrllibOAuthHttpTransport()

    def readiness(self) -> dict[str, bool]:
        checks = {
            "client_secret_resource_configured": bool(self.app_secret_resource),
            "redirect_uri_configured": bool(self.redirect_uri),
            "state_secret_configured": len(self.state_secret) >= 32,
        }
        return {**checks, "ready": all(checks.values())}

    def _require_state_secret(self) -> None:
        if len(self.state_secret) < 32:
            raise GoogleOAuthFlowError("Google OAuth state secret is not configured")

    def _app_secret(self) -> GoogleOAuthAppSecret:
        if not self.app_secret_resource:
            raise GoogleOAuthFlowError("Google OAuth client secret resource is not configured")
        try:
            raw = self.secret_reader.read(self.app_secret_resource)
        except Exception as exc:
            raise GoogleOAuthFlowError(
                f"Google OAuth client secret is unavailable: {type(exc).__name__}"
            ) from exc
        try:
            return GoogleOAuthAppSecret.model_validate_json(raw)
        except Exception as exc:
            raise GoogleOAuthFlowError("Google OAuth application secret payload is invalid") from exc

    def _validate_redirect(self) -> None:
        if not self.redirect_uri:
            raise GoogleOAuthFlowError("Google OAuth redirect URI is not configured")
        if self.redirect_uri.startswith("https://"):
            return
        if self.redirect_uri.startswith("http://localhost") or self.redirect_uri.startswith("http://127.0.0.1"):
            return
        raise GoogleOAuthFlowError("Google OAuth redirect URI must use HTTPS outside localhost")

    def begin(self, patient_id: str, bundles_raw: str = "") -> tuple[str, str]:
        self._require_state_secret()
        self._validate_redirect()
        app_secret = self._app_secret()
        bundles = _normalize_bundles(bundles_raw)
        scopes = oauth_scopes_for_bundles(bundles)
        verifier = secrets.token_urlsafe(64)
        state = _signed_token(
            self.state_secret,
            "google_oauth_state",
            {"patient_id": patient_id, "bundles": [item.value for item in bundles]},
        )
        cookie = _signed_token(
            self.state_secret,
            "google_oauth_pkce",
            {
                "patient_id": patient_id,
                "state_hash": hashlib.sha256(state.encode("utf-8")).hexdigest(),
                "verifier": verifier,
            },
        )
        existing = self.connection_store.load(patient_id)
        params = {
            "client_id": app_secret.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
        if existing is None or not existing.enabled:
            params["prompt"] = "consent"
        return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}", cookie

    def complete(self, patient_id: str, *, state: str, code: str, pkce_cookie: str) -> GoogleOAuthConnection:
        self._require_state_secret()
        self._validate_redirect()
        state_payload = _verify_signed_token(self.state_secret, state, "google_oauth_state")
        cookie_payload = _verify_signed_token(self.state_secret, pkce_cookie, "google_oauth_pkce")
        if state_payload.get("patient_id") != patient_id or cookie_payload.get("patient_id") != patient_id:
            raise GoogleOAuthFlowError("Google OAuth state does not belong to this patient session")
        expected_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(str(cookie_payload.get("state_hash") or ""), expected_hash):
            raise GoogleOAuthFlowError("Google OAuth PKCE cookie does not match the authorization state")
        verifier = str(cookie_payload.get("verifier") or "")
        if len(verifier) < 43:
            raise GoogleOAuthFlowError("Google OAuth PKCE verifier is invalid")
        clean_code = str(code or "").strip()
        if not clean_code:
            raise GoogleOAuthFlowError("Google OAuth authorization code is missing")
        bundles = _normalize_bundles(state_payload.get("bundles") or [])

        app_secret = self._app_secret()
        token = self.transport.post_form(
            GOOGLE_TOKEN_ENDPOINT,
            {
                "code": clean_code,
                "client_id": app_secret.client_id,
                "client_secret": app_secret.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
        access_token = str(token.get("access_token") or "").strip()
        if not access_token:
            raise GoogleOAuthFlowError("Google OAuth token exchange returned no access token")
        profile = self.transport.get_bearer(GOOGLE_USERINFO_ENDPOINT, access_token)
        subject = str(profile.get("sub") or "").strip()
        email = str(profile.get("email") or "").strip().lower()
        if not subject or not email or "@" not in email:
            raise GoogleOAuthFlowError("Google OAuth userinfo returned no stable subject/email")
        if profile.get("email_verified") is False:
            raise GoogleOAuthFlowError("Google account email is not verified")

        existing = self.connection_store.load(patient_id)
        if existing and existing.enabled:
            existing_subject = str(existing.google_subject or "").strip()
            if existing_subject and existing_subject != subject:
                raise GoogleOAuthFlowError(
                    "A different Google account is already connected; disconnect it before switching accounts"
                )
            if not existing_subject and existing.google_account.strip().lower() != email:
                raise GoogleOAuthFlowError(
                    "A different Google account is already connected; disconnect it before switching accounts"
                )

        refresh_token = str(token.get("refresh_token") or "").strip()
        if not refresh_token and existing and existing.secret_version_resource:
            try:
                prior = OAuthSecretMaterial.model_validate_json(
                    self.secret_reader.read(existing.secret_version_resource)
                )
                refresh_token = prior.refresh_token
            except Exception as exc:
                raise GoogleOAuthFlowError(
                    "Google returned no new refresh token and the existing token could not be recovered"
                ) from exc
        if not refresh_token:
            raise GoogleOAuthFlowError(
                "Google returned no refresh token; restart connection and approve offline access"
            )

        material = OAuthSecretMaterial(
            refresh_token=refresh_token,
            client_id=app_secret.client_id,
            client_secret=app_secret.client_secret,
            token_uri=GOOGLE_TOKEN_ENDPOINT,
        )
        version_resource = self.secret_writer.write(
            patient_id,
            material,
            existing_secret_version_resource=(existing.secret_version_resource if existing else ""),
        )
        returned_scopes = {item for item in str(token.get("scope") or "").split() if item}
        if not returned_scopes:
            returned_scopes = set(oauth_scopes_for_bundles(bundles))

        now = datetime.now(timezone.utc)
        if existing:
            connection = existing.model_copy(deep=True)
            connection.google_account = email
            connection.google_subject = subject
            connection.granted_scopes = sorted(returned_scopes)
            connection.secret_version_resource = version_resource
            connection.enabled = True
            connection.updated_at = now
        else:
            connection = GoogleOAuthConnection(
                patient_id=patient_id,
                google_account=email,
                google_subject=subject,
                granted_scopes=sorted(returned_scopes),
                secret_version_resource=version_resource,
                updated_at=now,
            )
        self.connection_store.save(connection)
        return connection

    def disconnect(self, patient_id: str) -> GoogleOAuthConnection | None:
        connection = self.connection_store.load(patient_id)
        if connection is None:
            return None
        connection.enabled = False
        connection.updated_at = datetime.now(timezone.utc)
        self.connection_store.save(connection)
        return connection


def build_google_oauth_browser_flow(settings: Settings, connection_store: OAuthConnectionStore) -> GoogleOAuthBrowserFlow:
    state_secret = os.getenv("HEALTHIA_GOOGLE_OAUTH_STATE_SECRET") or os.getenv("HEALTHIA_SESSION_SECRET") or ""
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    return GoogleOAuthBrowserFlow(
        connection_store=connection_store,
        app_secret_resource=os.getenv("HEALTHIA_GOOGLE_OAUTH_CLIENT_SECRET_RESOURCE", ""),
        redirect_uri=os.getenv("HEALTHIA_GOOGLE_OAUTH_REDIRECT_URI", ""),
        state_secret=state_secret,
        secret_writer=SecretManagerOAuthConnectionSecretWriter(project),
    )


def build_google_oauth_router(flow: GoogleOAuthBrowserFlow, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/google-constellation/oauth", tags=["google-oauth"])

    @router.get("/readiness")
    async def readiness() -> dict[str, Any]:
        return {
            **flow.readiness(),
            "secret_material_exposed": False,
            "truth_boundary": "Readiness reports configuration presence only; it never returns OAuth client or patient token material.",
        }

    @router.get("/connect")
    async def connect(bundles: str = ""):
        try:
            authorization_url, cookie = flow.begin(current_patient_id(), bundles)
        except GoogleOAuthFlowError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        response = RedirectResponse(authorization_url, status_code=303)
        response.set_cookie(
            OAUTH_COOKIE,
            cookie,
            max_age=600,
            httponly=True,
            secure=settings.env != "local",
            samesite="lax",
            path="/api/google-constellation/oauth/callback",
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.get("/callback")
    async def callback(request: FastAPIRequest, state: str = "", code: str = "", error: str = ""):
        if error:
            raise HTTPException(status_code=400, detail="Google account connection was not approved")
        cookie = request.cookies.get(OAUTH_COOKIE, "")
        if not state or not code or not cookie:
            raise HTTPException(status_code=400, detail="Google OAuth callback is incomplete")
        try:
            await asyncio.to_thread(
                flow.complete,
                current_patient_id(),
                state=state,
                code=code,
                pkce_cookie=cookie,
            )
        except GoogleOAuthFlowError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response = RedirectResponse("/?google=connected", status_code=303)
        response.delete_cookie(OAUTH_COOKIE, path="/api/google-constellation/oauth/callback")
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post("/disconnect")
    async def disconnect() -> dict[str, Any]:
        connection = flow.disconnect(current_patient_id())
        return {
            "disconnected": connection is not None,
            "google_account": connection.google_account if connection else "",
            "secret_material_exposed": False,
            "google_grant_revoked": False,
            "truth_boundary": (
                "HealthIA disabled use of the stored Google connection immediately. "
                "Revoking the Google Account grant itself is a separate provider action."
            ),
        }

    return router
