from __future__ import annotations

import threading
from datetime import datetime, timezone

from healthia_one.pairing import PairingError, PairingSession, utc_now


class FirestorePairingBackend:
    """Durable, multi-instance pairing state backed by Firestore.

    Pairing codes are created with Firestore's create precondition and claimed in
    a transaction, so two Cloud Run instances cannot consume the same code for
    different devices. A retry from the already-committed device is idempotent,
    which closes the failure window where the transaction commits but the HTTP
    response is lost. Waiting uses Firestore's snapshot listener rather than
    process-local Events or browser polling.
    """

    COLLECTION = "healthia_device_pairings"
    persistence = "firestore_transactional"

    def __init__(self, project: str | None = None) -> None:
        self.project = project
        self._firestore = None
        self._client = None

    @property
    def firestore(self):
        if self._firestore is None:
            from google.cloud import firestore

            self._firestore = firestore
        return self._firestore

    @property
    def client(self):
        if self._client is None:
            self._client = self.firestore.Client(project=self.project)
        return self._client

    @property
    def client_initialized(self) -> bool:
        return self._client is not None

    def _ref(self, code: str):
        return self.client.collection(self.COLLECTION).document(code)

    @staticmethod
    def _serialize(session: PairingSession) -> dict:
        return {
            "code": session.code,
            "expires_at": session.expires_at.isoformat(),
            "patient_id": session.patient_id,
            "connection_id": session.connection_id,
            "claimed": bool(session.claimed),
            "device_id": session.device_id,
            "display_name": session.display_name,
            # This field can be configured as a Firestore TTL field. Keeping it
            # as a native timestamp makes automatic cleanup possible without a
            # polling worker.
            "ttl_at": session.expires_at,
        }

    @staticmethod
    def _parse_datetime(value) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)

    @classmethod
    def _deserialize(cls, payload: dict) -> PairingSession:
        return PairingSession(
            code=str(payload["code"]),
            expires_at=cls._parse_datetime(payload["expires_at"]),
            patient_id=str(payload.get("patient_id") or "patient_demo"),
            connection_id=str(payload.get("connection_id") or ""),
            claimed=bool(payload.get("claimed")),
            device_id=str(payload.get("device_id") or ""),
            display_name=str(payload.get("display_name") or ""),
        )

    def create(self, session: PairingSession) -> bool:
        ref = self._ref(session.code)
        try:
            ref.create(self._serialize(session))
            return True
        except Exception as exc:
            # AlreadyExists is the expected collision path. Avoid importing a
            # private exception hierarchy so this remains compatible across the
            # pinned google-cloud-firestore line.
            if exc.__class__.__name__ in {"AlreadyExists", "Conflict"}:
                return False
            raise

    def get(self, code: str) -> PairingSession | None:
        snapshot = self._ref(code).get()
        if not snapshot.exists:
            return None
        session = self._deserialize(snapshot.to_dict())
        if session.expires_at <= utc_now():
            try:
                snapshot.reference.delete()
            except Exception:
                pass
            return None
        return session

    def delete(self, code: str) -> None:
        self._ref(code).delete()

    def claim(self, code: str, device_id: str, display_name: str) -> PairingSession:
        ref = self._ref(code)
        transaction = self.client.transaction()
        firestore = self.firestore

        @firestore.transactional
        def consume(txn):
            snapshot = ref.get(transaction=txn)
            if not snapshot.exists:
                raise PairingError("El código no existe o expiró.")
            session = self._deserialize(snapshot.to_dict())
            if session.expires_at <= utc_now():
                txn.delete(ref)
                raise PairingError("El código no existe o expiró.")
            if session.claimed:
                if session.device_id != device_id:
                    raise PairingError("El código ya fue utilizado por otro dispositivo.")
                # The same device may safely retry if the transaction committed
                # but its first HTTP response was lost. The manager reissues a
                # fresh signed bearer; no second device can cross this boundary.
                return session
            session.claimed = True
            session.device_id = device_id
            session.display_name = display_name
            txn.set(ref, self._serialize(session), merge=True)
            return session

        return consume(transaction)

    def wait_for_claim(self, code: str, timeout_seconds: float) -> PairingSession | None:
        initial = self.get(code)
        if initial is None:
            raise PairingError("El código no existe o expiró.")
        if initial.claimed:
            return initial

        ref = self._ref(code)
        done = threading.Event()
        latest: dict[str, PairingSession | None] = {"session": initial}

        def on_snapshot(doc_snapshots, _changes, _read_time) -> None:
            if not doc_snapshots:
                latest["session"] = None
                done.set()
                return
            snapshot = doc_snapshots[0]
            if not snapshot.exists:
                latest["session"] = None
                done.set()
                return
            session = self._deserialize(snapshot.to_dict())
            latest["session"] = session
            if session.claimed or session.expires_at <= utc_now():
                done.set()

        watch = ref.on_snapshot(on_snapshot)
        try:
            done.wait(max(0.0, timeout_seconds))
        finally:
            watch.unsubscribe()

        session = latest.get("session")
        if session is None or session.expires_at <= utc_now():
            return None
        return session
