from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar


DEFAULT_PATIENT_ID = "patient_demo"
_current_patient_id: ContextVar[str] = ContextVar("healthia_patient_id", default=DEFAULT_PATIENT_ID)


def current_patient_id() -> str:
    return _current_patient_id.get()


def normalize_patient_id(value: str | None) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return DEFAULT_PATIENT_ID
    # Firebase/Identity Platform UIDs are safe Firestore document ids. Keep the
    # scope opaque rather than deriving it from email or other mutable PII.
    if "/" in candidate or len(candidate) > 128:
        raise ValueError("Invalid patient identity scope")
    return candidate


@contextmanager
def patient_scope(patient_id: str):
    normalized = normalize_patient_id(patient_id)
    token = _current_patient_id.set(normalized)
    try:
        yield normalized
    finally:
        _current_patient_id.reset(token)
