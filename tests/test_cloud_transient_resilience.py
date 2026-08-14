from __future__ import annotations

import asyncio
from pathlib import Path

from healthia_one.store import FirestoreStore


ROOT = Path(__file__).resolve().parents[1]


def test_firestore_retry_recovers_from_transient_read_failure() -> None:
    class TransientCloudError(Exception):
        pass

    store = object.__new__(FirestoreStore)
    store._transient_errors = (TransientCloudError,)
    store._RETRY_DELAYS = (0.0, 0.0, 0.0)
    calls = 0

    async def flaky_operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientCloudError("temporary Firestore read failure")
        return "ok"

    assert asyncio.run(store._with_transient_retry(flaky_operation)) == "ok"
    assert calls == 3


def test_firestore_retry_still_fails_closed_for_nontransient_errors() -> None:
    store = object.__new__(FirestoreStore)
    store._transient_errors = (TimeoutError,)
    store._RETRY_DELAYS = (0.0, 0.0, 0.0)
    calls = 0

    async def invalid_state():
        nonlocal calls
        calls += 1
        raise ValueError("patient identity mismatch")

    try:
        asyncio.run(store._with_transient_retry(invalid_state))
    except ValueError as exc:
        assert "identity mismatch" in str(exc)
    else:
        raise AssertionError("nontransient validation error must fail closed")
    assert calls == 1


def test_final_recorder_backs_off_on_transient_bootstrap_429_and_500() -> None:
    recorder = (ROOT / "scripts" / "record_final_live_english_demo.py").read_text(encoding="utf-8")

    assert '"HTTP 429" not in error_text and "HTTP 500" not in error_text' in recorder
    assert "persistent fault still fails at timeout" in recorder
    assert "rate_limit_backoff_ms=5000" in recorder
