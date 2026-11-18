"""Thread-safe in-memory rate limiter for NEXUS IoT.

Each bucket tracks request counts in a sliding window. All state is
in-process (no external dependency) and expires automatically.

Usage::

    from .ratelimit import check_rate_limit

    # Raises ApiError(429) if the limit is exceeded.
    check_rate_limit("login_fail", ip, limit=5, window=900)
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Tuple

from .errors import ApiError

# _buckets: key -> list of timestamps (seconds since epoch)
_buckets: Dict[str, list] = {}
_lock = threading.Lock()

# IPs that are never rate-limited (loopback / test harness)
_LOCAL_IPS = {"127.0.0.1", "::1", "localhost", ""}

# Hardened limits (all per-IP unless noted)
LIMITS: Dict[str, Tuple[int, int]] = {
    # (max_requests, window_seconds)
    "login_fail":    (5,   900),   # 5 failed logins / 15 min
    "login":         (20,  900),   # 20 total login tries / 15 min (brute-force envelope)
    "register":      (3,   3600),  # 3 registrations / hour
    "api_global":    (300, 60),    # 300 API calls / minute (all endpoints)
    "ai_chat":       (30,  60),    # 30 AI requests / minute (expensive endpoint)
    "password_reset":(3,   3600),  # 3 password-reset attempts / hour
}


def _evict(timestamps: list, window: float, now: float) -> list:
    """Remove timestamps older than the window."""
    cutoff = now - window
    return [t for t in timestamps if t >= cutoff]


def _is_local(identifier: str) -> bool:
    """Return True for loopback / empty IPs that should bypass rate limits."""
    return identifier in _LOCAL_IPS or identifier.startswith("127.") or identifier.startswith("::1")


def check_rate_limit(limit_key: str, identifier: str, limit: int | None = None,
                     window: int | None = None) -> None:
    """Check whether *identifier* has exceeded the named limit.

    Raises ``ApiError(429)`` if the limit is exceeded.
    ``limit`` and ``window`` override the defaults in ``LIMITS``.
    Loopback / local IPs are never rate-limited.
    """
    # Never rate-limit local / test traffic
    if _is_local(identifier):
        return

    if limit is None or window is None:
        default_limit, default_window = LIMITS.get(limit_key, (300, 60))
        limit = limit if limit is not None else default_limit
        window = window if window is not None else default_window

    bucket_key = f"{limit_key}:{identifier}"
    now = time.time()
    with _lock:
        timestamps = _evict(_buckets.get(bucket_key, []), window, now)
        if len(timestamps) >= limit:
            retry_after = int(window - (now - timestamps[0])) + 1
            raise ApiError(
                429,
                f"Too many requests. Please try again in {retry_after} seconds.",
                "rate_limited",
                extra_headers={"Retry-After": str(retry_after)},
            )
        timestamps.append(now)
        _buckets[bucket_key] = timestamps


def record_event(limit_key: str, identifier: str) -> None:
    """Record one event in the bucket without checking the limit.

    Useful for counting failed attempts that need to be tracked but
    whose enforcement happens via ``check_rate_limit`` later.
    Loopback / local IPs are silently ignored.
    """
    if _is_local(identifier):
        return
    bucket_key = f"{limit_key}:{identifier}"
    now = time.time()
    _limit, window = LIMITS.get(limit_key, (300, 60))
    with _lock:
        timestamps = _evict(_buckets.get(bucket_key, []), window, now)
        timestamps.append(now)
        _buckets[bucket_key] = timestamps


def get_count(limit_key: str, identifier: str) -> int:
    """Return current bucket count (for telemetry only)."""
    if _is_local(identifier):
        return 0
    bucket_key = f"{limit_key}:{identifier}"
    _limit, window = LIMITS.get(limit_key, (300, 60))
    now = time.time()
    with _lock:
        return len(_evict(_buckets.get(bucket_key, []), window, now))


def cleanup_old_buckets() -> int:
    """Remove expired buckets; call periodically to prevent memory growth."""
    now = time.time()
    removed = 0
    with _lock:
        for key in list(_buckets.keys()):
            lk = key.split(":")[0]
            _limit, window = LIMITS.get(lk, (300, 60))
            _buckets[key] = _evict(_buckets[key], window, now)
            if not _buckets[key]:
                del _buckets[key]
                removed += 1
    return removed
