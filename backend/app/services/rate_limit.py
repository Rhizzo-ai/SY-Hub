"""In-process token-bucket rate limiter.

Per-key (e.g. per-IP, per-email) counters held in memory. Thread-safe via
a single lock — fine for single-worker FastAPI, and fine enough for Phase 1
multi-worker as long as the error budget tolerates per-worker drift.

Migrate to Redis when we deploy properly (roadmap note).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

_startup_log = logging.getLogger("syhomes.rate_limit")


@dataclass
class Bucket:
    tokens: float
    last_refill: float


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, Bucket] = {}
        self._lock = threading.Lock()

    def check(
        self, key: str, capacity: int, window_seconds: float,
    ) -> tuple[bool, float]:
        """Returns (allowed, retry_after_seconds).

        On first call a bucket starts full. Each call costs 1 token.
        Tokens refill linearly: `capacity / window_seconds` per second.
        """
        now = time.monotonic()
        refill_rate = capacity / window_seconds
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = Bucket(tokens=capacity - 1, last_refill=now)
                self._buckets[key] = b
                return True, 0.0

            elapsed = now - b.last_refill
            b.tokens = min(capacity, b.tokens + elapsed * refill_rate)
            b.last_refill = now

            if b.tokens >= 1:
                b.tokens -= 1
                return True, 0.0

            needed = 1 - b.tokens
            retry = needed / refill_rate
            return False, retry

    def reset(self, key: Optional[str] = None) -> None:
        """Clear all buckets (if key is None) or a single bucket. Tests use this."""
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)


# Module-level singleton. Endpoints pull this directly.
rate_limiter = RateLimiter()


# Per-endpoint limits — centralised so rate decisions live next to each other.
LIMITS = {
    "login_per_ip":            (10, 60),        # 10/min per IP
    "login_per_email":         (5, 60),         # 5/min per email
    "pw_reset_request_per_email": (3, 3600),    # 3/hour per email
    "pw_reset_request_per_ip":    (10, 3600),   # 10/hour per IP
    "pw_reset_complete_per_ip":   (10, 3600),   # 10/hour per IP
}


def _is_bypass_active() -> bool:
    """Rate limiting is bypassed ONLY when BOTH flags are set:

      - SYHOMES_RATE_LIMIT_DISABLED=1
      - APP_ENV=test

    A stray `SYHOMES_RATE_LIMIT_DISABLED=1` in production is a footgun we
    refuse to honour; we log an ERROR instead and leave the limiter active.
    """
    disabled_flag = os.environ.get("SYHOMES_RATE_LIMIT_DISABLED") == "1"
    app_env = os.environ.get("APP_ENV", "")
    if disabled_flag and app_env == "test":
        return True
    if disabled_flag and app_env != "test":
        _startup_log.error(
            "SYHOMES_RATE_LIMIT_DISABLED is set but APP_ENV=%r. "
            "Rate limiting REMAINS ACTIVE. The disable flag only takes effect "
            "when APP_ENV=test.",
            app_env or "(unset)",
        )
    return False


# Emit startup-time confirmation so operators see the decision in the logs
# instead of having to reason about env pairs.
if os.environ.get("SYHOMES_RATE_LIMIT_DISABLED") == "1" and os.environ.get("APP_ENV") == "test":
    _startup_log.warning("Rate limiting disabled — APP_ENV=test.")


def enforce(kind: str, key: str) -> tuple[bool, float]:
    if _is_bypass_active():
        return True, 0.0
    cap, window = LIMITS[kind]
    return rate_limiter.check(f"{kind}:{key}", cap, window)
