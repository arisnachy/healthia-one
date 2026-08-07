from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event, Lock


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PairingError(ValueError):
    pass


@dataclass(frozen=True)
class DevicePrincipal:
    patient_id: str
    connection_id: str
    device_id: str
    display_name: str
    issued_at: datetime
    expires_at: datetime


@dataclass
class PairingSession:
    code: str
    expires_at: datetime
    patient_id: str = "patient_demo"
    connection_id: str = ""
    claimed: bool = False
    device_id: str = ""
    display_name: str = ""


class DevicePairingManager:
    """Event-driven pairing plus restart-safe, patient-bound signed credentials."""

    def __init__(
        self,
        ttl_minutes: int = 10,
        *,
        token_secret: str | bytes | None = None,
        token_ttl_days: int = 90,
    ) -> None:
        self.ttl_minutes = ttl_minutes
        self.token_ttl_days = max(1, int(token_ttl_days))
        configured = token_secret or os.getenv("HEALTHIA_DEVICE_TOKEN_SECRET", "")
        if isinstance(configured, str):
            configured_bytes = configured.encode("utf-8")
        else:
            configured_bytes = configured or b""
        self._secret_is_persistent = len(configured_bytes) >= 32
        self._token_secret = configured_bytes if self._secret_is_persistent else secrets.token_bytes(32)
        self._sessions: dict[str, PairingSession] = {}
        self._claim_events: dict[str, Event] = {}
        self._lock = Lock()

    @property
    def credential_persistence(self) -> str:
        return "restart_safe" if self._secret_is_persistent else "process_local_secret"

    @staticmethod
    def _b64_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _b64_decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))

    def _sign(self, payload_segment: str) -> str:
        signature = hmac.new(self._token_secret, payload_segment.encode("ascii"), hashlib.sha256).digest()
        return self._b64_encode(signature)

    def _issue_token(self, principal: DevicePrincipal) -> str:
        payload = {
            "v": 1,
            "patient_id": principal.patient_id,
            "connection_id": principal.connection_id,
            "device_id": principal.device_id,
            "display_name": principal.display_name,
            "iat": int(principal.issued_at.timestamp()),
            "exp": int(principal.expires_at.timestamp()),
            "nonce": secrets.token_hex(8),
        }
        payload_segment = self._b64_encode(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        return f"h1.{payload_segment}.{self._sign(payload_segment)}"

    def _decode_token(self, token: str) -> DevicePrincipal | None:
        try:
            version, payload_segment, signature = token.split(".", 2)
            if version != "h1":
                return None
            expected = self._sign(payload_segment)
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(self._b64_decode(payload_segment).decode("utf-8"))
            if payload.get("v") != 1:
                return None
            issued_at = datetime.fromtimestamp(int(payload["iat"]), tz=timezone.utc)
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
            if expires_at <= utc_now():
                return None
            return DevicePrincipal(
                patient_id=str(payload["patient_id"]),
                connection_id=str(payload["connection_id"]),
                device_id=str(payload["device_id"]),
                display_name=str(payload.get("display_name") or "Android Health Connect")[:160],
                issued_at=issued_at,
                expires_at=expires_at,
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _cleanup_unlocked(self) -> None:
        now = utc_now()
        expired = [code for code, session in self._sessions.items() if session.expires_at <= now]
        for code in expired:
            self._sessions.pop(code, None)
            event = self._claim_events.pop(code, None)
            if event is not None:
                event.set()

    def _cleanup(self) -> None:
        with self._lock:
            self._cleanup_unlocked()

    def create(self, patient_id: str = "patient_demo") -> dict:
        with self._lock:
            self._cleanup_unlocked()
            for _ in range(20):
                code = f"{secrets.randbelow(1_000_000):06d}"
                if code not in self._sessions:
                    break
            else:
                raise PairingError("No se pudo generar un código de conexión.")
            session = PairingSession(
                code=code,
                expires_at=utc_now() + timedelta(minutes=self.ttl_minutes),
                patient_id=patient_id,
                connection_id=f"hc_{secrets.token_hex(8)}",
            )
            self._sessions[code] = session
            self._claim_events[code] = Event()
            return self._status_unlocked(session)

    @staticmethod
    def _status_unlocked(session: PairingSession) -> dict:
        return {
            "code": session.code,
            "expires_at": session.expires_at.isoformat(),
            "claimed": session.claimed,
            "device_id": session.device_id,
            "display_name": session.display_name,
            "connection_id": session.connection_id,
            "patient_id": session.patient_id,
        }

    def status(self, code: str) -> dict:
        with self._lock:
            self._cleanup_unlocked()
            session = self._sessions.get(code)
            if not session:
                raise PairingError("El código no existe o expiró.")
            return self._status_unlocked(session)

    def claim(self, code: str, device_id: str, display_name: str) -> dict:
        clean_device_id = str(device_id or "").strip()
        if len(clean_device_id) < 3:
            raise PairingError("La identidad del dispositivo no es válida.")
        with self._lock:
            self._cleanup_unlocked()
            session = self._sessions.get(code)
            if not session:
                raise PairingError("El código no existe o expiró.")
            if session.claimed:
                if session.device_id != clean_device_id:
                    raise PairingError("El código ya fue utilizado por otro dispositivo.")
                raise PairingError("El código ya fue consumido. Genera uno nuevo para volver a vincular.")
            session.claimed = True
            session.device_id = clean_device_id
            session.display_name = (display_name or "Android Health Connect").strip()[:160]
            issued_at = utc_now()
            principal = DevicePrincipal(
                patient_id=session.patient_id,
                connection_id=session.connection_id,
                device_id=session.device_id,
                display_name=session.display_name,
                issued_at=issued_at,
                expires_at=issued_at + timedelta(days=self.token_ttl_days),
            )
            token = self._issue_token(principal)
            event = self._claim_events.get(code)
            if event is not None:
                event.set()
            return {
                "access_token": token,
                "token_type": "bearer",
                "device_id": session.device_id,
                "display_name": session.display_name,
                "connection_id": session.connection_id,
                "patient_id": session.patient_id,
                "pairing_expires_at": session.expires_at.isoformat(),
                "credential_expires_at": principal.expires_at.isoformat(),
                "credential_persistence": self.credential_persistence,
            }

    def wait_for_claim(self, code: str, timeout_seconds: float | None = None) -> dict:
        with self._lock:
            self._cleanup_unlocked()
            session = self._sessions.get(code)
            if not session:
                raise PairingError("El código no existe o expiró.")
            event = self._claim_events.get(code)
            if event is None:
                raise PairingError("La sesión de conexión ya no está disponible.")
            remaining = max(0.0, (session.expires_at - utc_now()).total_seconds())
            timeout = remaining if timeout_seconds is None else min(max(timeout_seconds, 0.0), remaining)
        event.wait(timeout)
        with self._lock:
            self._cleanup_unlocked()
            session = self._sessions.get(code)
            if not session:
                return {"code": code, "claimed": False, "expired": True}
            payload = self._status_unlocked(session)
            payload["expired"] = False
            return payload

    def identify(self, token: str, device_id: str) -> DevicePrincipal | None:
        """Authenticate a signed device and recover its patient scope without trusting request input."""
        if not token or not device_id:
            return None
        principal = self._decode_token(token)
        if principal is None or principal.device_id != device_id:
            return None
        return principal

    def authorize(self, token: str, device_id: str, patient_id: str = "patient_demo") -> DevicePrincipal | None:
        principal = self.identify(token, device_id)
        if principal is None or principal.patient_id != patient_id:
            return None
        return principal

    def validate(self, token: str, device_id: str, patient_id: str = "patient_demo") -> bool:
        return self.authorize(token, device_id, patient_id) is not None
