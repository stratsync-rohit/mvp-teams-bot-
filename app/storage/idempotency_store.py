"""
Small short-lived idempotency cache used to protect against double-clicked
Adaptive Card buttons in Microsoft Teams.

V1 implementation is in-memory and time-window based. Replace with a
Redis-backed implementation (e.g. SETNX with TTL) for multi-instance
deployments without changing the calling code in the bot layer.
"""

from __future__ import annotations

import time
from threading import Lock


class IdempotencyStore:
    def __init__(self, window_seconds: float = 5.0) -> None:
        self._window_seconds = window_seconds
        self._seen: dict[str, float] = {}
        self._lock = Lock()

    def seen_recently(self, key: str) -> bool:
        """
        Returns True (and records the key) if this key was already seen
        within the idempotency window - callers should treat this as
        "skip processing, this is a duplicate".
        """
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            last_seen = self._seen.get(key)
            self._seen[key] = now
            if last_seen is not None and (now - last_seen) < self._window_seconds:
                return True
        return False

    def _evict_expired(self, now: float) -> None:
        expired = [
            k for k, ts in self._seen.items() if (now - ts) >= self._window_seconds
        ]
        for k in expired:
            del self._seen[k]


# Process-wide singleton used by the FastAPI app.
idempotency_store = IdempotencyStore(window_seconds=5.0)
