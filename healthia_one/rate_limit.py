from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class RateLimitExceeded(ValueError):
    retry_after: int


class SlidingWindowRateLimiter:
    """Small process-local abuse boundary for the single-instance demo runtime."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        clean_key = str(key or "").strip()
        if not clean_key or limit < 1 or window_seconds < 1:
            raise ValueError("Invalid rate-limit policy")
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[clean_key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(events[0] + window_seconds - now) + 1)
                raise RateLimitExceeded(retry_after=retry_after)
            events.append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(str(key or "").strip(), None)
