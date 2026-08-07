from __future__ import annotations

import hashlib
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


@dataclass
class PairingSession:
    code: str
    expires_at: datetime
    patient_id: str = "patient_demo"
    connection_id: str = ""
    claimed: bool = False
    device_id: str = ""
    display_name: str = ""
    token_hash: str = ""


class DevicePairingManager:
    """Short-lived pairing codes with server-issued, patient-bound device identities.

    Pairing completion is signalled with an Event so the browser can wait once for
    the claim instead of polling every few seconds. Bearer tokens are stored only
    as hashes and are bound to patient + server-generated connection + device id.
    """

    def __init__(self, ttl_minutes: int = 10) -> None:
        self.ttl_minutes = ttl_minutes
        self._sessions: dict[str, PairingSession] = {}
        self._tokens: dict[str, DevicePrincipal] = {}
        self._claim_events: dict[str, Event] = {}
        self._lock = Lock()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _cleanup_unlocked(self) -> None:
        now = utc_now()
        expired = [code for code, session in self._sessions.items() if session.expires_at <= now]
        for code in expired:
            self._sessions.pop(code, None)
            event = self._claim_events.pop(code, None)
            if event is not None:
                event.set()

    def _cleanup(self) -> None:
        """Compatibility wrapper used by tests and maintenance probes."""
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
            token = secrets.token_urlsafe(32)
            token_hash = self._hash(token)
            session.claimed = True
            session.device_id = clean_device_id
            session.display_name = (display_name or "Android Health Connect").strip()[:160]
            session.token_hash = token_hash
            principal = DevicePrincipal(
                patient_id=session.patient_id,
                connection_id=session.connection_id,
                device_id=session.device_id,
                display_name=session.display_name,
                issued_at=utc_now(),
            )
            self._tokens[token_hash] = principal
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

    def authorize(self, token: str, device_id: str, patient_id: str = "patient_demo") -> DevicePrincipal | None:
        if not token or not device_id:
            return None
        with self._lock:
            principal = self._tokens.get(self._hash(token))
            if principal is None:
                return None
            if principal.device_id != device_id or principal.patient_id != patient_id:
                return None
            return principal

    def validate(self, token: str, device_id: str, patient_id: str = "patient_demo") -> bool:
        return self.authorize(token, device_id, patient_id) is not None
