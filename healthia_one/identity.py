from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from healthia_one.config import Settings


class IdentityError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthPrincipal:
    uid: str
    email: str = ""
    display_name: str = ""
    provider: str = ""


class IdentityVerifier:
    """Verify Identity Platform/Firebase ID tokens for the custom FastAPI backend.

    Local mode deliberately bypasses remote identity so CI and zero-spend local
    development remain self-contained. Cloud mode requires a signed bearer token
    and derives the patient scope exclusively from its verified ``uid``.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._firebase_app: Any | None = None

    @property
    def required(self) -> bool:
        return self.settings.auth_mode == "identity_platform"

    @property
    def web_ready(self) -> bool:
        if not self.required:
            return True
        return all(
            [
                self.settings.firebase_api_key,
                self.settings.firebase_project_id,
                self.settings.firebase_auth_domain,
                self.settings.firebase_app_id,
            ]
        )

    def public_config(self) -> dict[str, Any]:
        if not self.required:
            return {
                "enabled": False,
                "mode": "local",
                "providers": [],
                "truth_boundary": "Local zero-spend mode does not require a remote account.",
            }
        return {
            "enabled": True,
            "mode": "identity_platform",
            "ready": self.web_ready,
            "providers": ["google.com", "password"],
            "firebase": {
                # Firebase web configuration values are project identifiers, not
                # server credentials. Secret keys remain in Secret Manager.
                "apiKey": self.settings.firebase_api_key,
                "authDomain": self.settings.firebase_auth_domain,
                "projectId": self.settings.firebase_project_id,
                "appId": self.settings.firebase_app_id,
            },
            "truth_boundary": "The backend trusts only verified ID tokens and uses the immutable uid as the patient scope.",
        }

    def _ensure_app(self):
        if self._firebase_app is not None:
            return self._firebase_app
        try:
            import firebase_admin
            from firebase_admin import credentials
        except ImportError as exc:
            raise IdentityError("firebase-admin is required for Identity Platform mode") from exc

        try:
            self._firebase_app = firebase_admin.get_app("healthia-one")
            return self._firebase_app
        except ValueError:
            pass

        options = {"projectId": self.settings.firebase_project_id} if self.settings.firebase_project_id else None
        # Application Default Credentials are used on Cloud Run. Locally, an
        # explicitly configured ADC/service account can be used for a live auth test.
        try:
            credential = credentials.ApplicationDefault()
            self._firebase_app = firebase_admin.initialize_app(
                credential,
                options=options,
                name="healthia-one",
            )
        except Exception as exc:  # pragma: no cover - requires external credentials
            raise IdentityError(f"Identity Platform admin initialization failed: {type(exc).__name__}") from exc
        return self._firebase_app

    async def verify_bearer(self, authorization: str | None) -> AuthPrincipal:
        if not self.required:
            return AuthPrincipal(uid="patient_demo", display_name="Ana Martínez", provider="local")
        value = str(authorization or "").strip()
        if not value.lower().startswith("bearer "):
            raise IdentityError("Authentication required")
        token = value.split(" ", 1)[1].strip()
        if not token:
            raise IdentityError("Authentication token is empty")
        app = self._ensure_app()
        from firebase_admin import auth

        try:
            decoded = await asyncio.to_thread(auth.verify_id_token, token, app, True)
        except Exception as exc:  # pragma: no cover - depends on live Google keys
            raise IdentityError("Authentication token is invalid or expired") from exc
        uid = str(decoded.get("uid") or decoded.get("sub") or "").strip()
        if not uid:
            raise IdentityError("Verified token does not contain a uid")
        firebase_claim = decoded.get("firebase") if isinstance(decoded.get("firebase"), dict) else {}
        return AuthPrincipal(
            uid=uid,
            email=str(decoded.get("email") or "").strip(),
            display_name=str(decoded.get("name") or "").strip(),
            provider=str(firebase_claim.get("sign_in_provider") or "").strip(),
        )
