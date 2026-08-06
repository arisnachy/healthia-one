from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PairingError(ValueError):
    pass


@dataclass
class PairingSession:
    code: str
    expires_at: datetime
    claimed: bool = False
    device_id: str = ""
    display_name: str = ""
    token_hash: str = ""


class DevicePairingManager:
    """Short-lived local pairing codes and hashed bearer tokens."""

    def __init__(self, ttl_minutes: int = 10) -> None:
        self.ttl_minutes = ttl_minutes
        self._sessions: dict[str, PairingSession] = {}
        self._tokens: dict[str, str] = {}

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _cleanup(self) -> None:
        now = utc_now()
        expired = [code for code, session in self._sessions.items() if session.expires_at <= now]
        for code in expired:
            # Pairing codes expire quickly, but a successfully claimed device token
            # remains valid for the lifetime of this local server process.
            self._sessions.pop(code)

    def create(self) -> dict:
        self._cleanup()
        for _ in range(20):
            code = f"{secrets.randbelow(1_000_000):06d}"
            if code not in self._sessions:
                break
        else:
            raise PairingError("No se pudo generar un código de conexión.")
        session = PairingSession(code=code, expires_at=utc_now() + timedelta(minutes=self.ttl_minutes))
        self._sessions[code] = session
        return self.status(code)

    def status(self, code: str) -> dict:
        self._cleanup()
        session = self._sessions.get(code)
        if not session:
            raise PairingError("El código no existe o expiró.")
        return {
            "code": session.code,
            "expires_at": session.expires_at.isoformat(),
            "claimed": session.claimed,
            "device_id": session.device_id,
            "display_name": session.display_name,
        }

    def claim(self, code: str, device_id: str, display_name: str) -> dict:
        self._cleanup()
        session = self._sessions.get(code)
        if not session:
            raise PairingError("El código no existe o expiró.")
        if session.claimed and session.device_id != device_id:
            raise PairingError("El código ya fue utilizado por otro dispositivo.")
        token = secrets.token_urlsafe(32)
        token_hash = self._hash(token)
        session.claimed = True
        session.device_id = device_id
        session.display_name = display_name or "Android Health Connect"
        session.token_hash = token_hash
        self._tokens[token_hash] = device_id
        return {
            "access_token": token,
            "token_type": "bearer",
            "device_id": device_id,
            "display_name": session.display_name,
            "expires_at": session.expires_at.isoformat(),
        }

    def validate(self, token: str, device_id: str) -> bool:
        self._cleanup()
        if not token or not device_id:
            return False
        return self._tokens.get(self._hash(token)) == device_id
