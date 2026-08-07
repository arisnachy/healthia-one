from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from healthia_one.config import Settings


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class PatientPrincipal:
    account_id: str
    patient_id: str
    email: str
    display_name: str


_current_principal: ContextVar[PatientPrincipal | None] = ContextVar("healthia_principal", default=None)


def current_principal() -> PatientPrincipal | None:
    return _current_principal.get()


def current_patient_id() -> str:
    principal = current_principal()
    return principal.patient_id if principal else "patient_demo"


def bind_principal(principal: PatientPrincipal | None) -> Token:
    return _current_principal.set(principal)


def reset_principal(token: Token) -> None:
    _current_principal.reset(token)


@contextmanager
def principal_scope(principal: PatientPrincipal | None) -> Iterator[None]:
    token = bind_principal(principal)
    try:
        yield
    finally:
        reset_principal(token)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or "@" not in email:
        raise AuthError("Introduce un correo válido.")
    local, _, domain = email.partition("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise AuthError("Introduce un correo válido.")
    return email


def _password_hash(password: str, salt: bytes | None = None) -> str:
    if len(password) < 10:
        raise AuthError("La contraseña debe tener al menos 10 caracteres.")
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_b64encode(salt)}${_b64encode(derived)}"


def _password_matches(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = _b64decode(salt_b64)
        expected = _b64decode(digest_b64)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)
    except (ValueError, TypeError):
        return False


class AccountManager:
    """Small hackathon account boundary with patient-scoped identity.

    Local mode stores only salted scrypt password hashes in a private JSON file.
    Firestore mode stores the same account records under email-derived document
    IDs. Browser sessions are stateless HMAC credentials and never contain a
    password or API key.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._session_secret, self.credential_persistence = self._load_session_secret()

    def _load_session_secret(self) -> tuple[bytes, str]:
        configured = os.getenv("HEALTHIA_SESSION_SECRET", "").encode("utf-8")
        if len(configured) >= 32:
            return configured, "restart_safe"
        if self.settings.env == "local":
            path = Path(".healthia-one/session-secret")
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                secret = path.read_bytes().strip()
                if len(secret) >= 32:
                    return secret, "restart_safe_local"
            secret = secrets.token_urlsafe(48).encode("ascii")
            path.write_bytes(secret)
            return secret, "restart_safe_local"
        return secrets.token_bytes(48), "process_local_secret"

    @staticmethod
    def _account_doc_id(email: str) -> str:
        return hashlib.sha256(email.encode("utf-8")).hexdigest()

    def _load_local_accounts(self) -> dict[str, dict]:
        path = self.settings.accounts_path
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            raise AuthError("El almacén local de cuentas no se puede leer.")
        return payload if isinstance(payload, dict) else {}

    def _save_local_accounts(self, accounts: dict[str, dict]) -> None:
        path = self.settings.accounts_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(accounts, ensure_ascii=False, indent=2), "utf-8")
        temp.replace(path)

    def _get_account(self, email: str) -> dict | None:
        if self.settings.store_backend == "firestore":
            from google.cloud import firestore

            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            client = firestore.Client(project=project)
            snapshot = client.collection("healthia_one_accounts").document(self._account_doc_id(email)).get()
            return snapshot.to_dict() if snapshot.exists else None
        with self._lock:
            return self._load_local_accounts().get(email)

    def _put_account(self, email: str, record: dict) -> None:
        if self.settings.store_backend == "firestore":
            from google.cloud import firestore

            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            client = firestore.Client(project=project)
            client.collection("healthia_one_accounts").document(self._account_doc_id(email)).set(record)
            return
        with self._lock:
            accounts = self._load_local_accounts()
            accounts[email] = record
            self._save_local_accounts(accounts)

    def register(self, email: str, password: str, display_name: str) -> PatientPrincipal:
        if not self.settings.allow_registration:
            raise AuthError("El registro de nuevas cuentas está deshabilitado.")
        normalized = _normalize_email(email)
        clean_name = " ".join(display_name.split()).strip()
        if not 2 <= len(clean_name) <= 120:
            raise AuthError("Introduce el nombre del paciente.")
        if self._get_account(normalized):
            raise AuthError("Ya existe una cuenta con ese correo.")
        account_id = f"account_{uuid4().hex}"
        patient_id = f"patient_{uuid4().hex}"
        record = {
            "account_id": account_id,
            "patient_id": patient_id,
            "email": normalized,
            "display_name": clean_name,
            "password_hash": _password_hash(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "disabled": False,
        }
        self._put_account(normalized, record)
        return PatientPrincipal(account_id=account_id, patient_id=patient_id, email=normalized, display_name=clean_name)

    def authenticate(self, email: str, password: str) -> PatientPrincipal:
        normalized = _normalize_email(email)
        record = self._get_account(normalized)
        if not record or record.get("disabled") or not _password_matches(password, str(record.get("password_hash", ""))):
            raise AuthError("Correo o contraseña incorrectos.")
        return PatientPrincipal(
            account_id=str(record["account_id"]),
            patient_id=str(record["patient_id"]),
            email=normalized,
            display_name=str(record.get("display_name") or "Paciente"),
        )

    def issue_session(self, principal: PatientPrincipal) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "v": 1,
            "account_id": principal.account_id,
            "patient_id": principal.patient_id,
            "email": principal.email,
            "display_name": principal.display_name,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=self.settings.session_hours)).timestamp()),
            "nonce": secrets.token_hex(12),
        }
        encoded = _b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        signature = _b64encode(hmac.new(self._session_secret, encoded.encode("ascii"), hashlib.sha256).digest())
        return f"h1.{encoded}.{signature}"

    def verify_session(self, token: str | None) -> PatientPrincipal | None:
        if not token:
            return None
        try:
            version, encoded, signature = token.split(".", 2)
            if version != "h1":
                return None
            expected = _b64encode(hmac.new(self._session_secret, encoded.encode("ascii"), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(_b64decode(encoded))
            if int(payload.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
                return None
            patient_id = str(payload.get("patient_id", ""))
            account_id = str(payload.get("account_id", ""))
            email = _normalize_email(str(payload.get("email", "")))
            display_name = str(payload.get("display_name", "Paciente"))[:120]
            if not patient_id.startswith("patient_") or not account_id.startswith("account_"):
                return None
            return PatientPrincipal(account_id=account_id, patient_id=patient_id, email=email, display_name=display_name)
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def public_session(self, principal: PatientPrincipal | None) -> dict:
        return {
            "authenticated": principal is not None,
            "auth_required": self.settings.auth_required,
            "allow_registration": self.settings.allow_registration,
            "credential_persistence": self.credential_persistence,
            "account": (
                {
                    "account_id": principal.account_id,
                    "patient_id": principal.patient_id,
                    "email": principal.email,
                    "display_name": principal.display_name,
                }
                if principal
                else None
            ),
        }
