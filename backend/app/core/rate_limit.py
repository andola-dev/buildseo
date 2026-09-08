"""Rate limiting abstraction.

``RateLimiter`` is a protocol so the in-process limiter below can be swapped
for a Redis (or other shared-store) implementation without touching the
middleware: a multi-instance deployment needs a shared counter, and only the
provider changes.

The in-memory limiter uses a token bucket rather than a fixed window, because a
fixed window lets a caller spend two full quotas across a window boundary.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """Outcome of a limiter check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int

    def as_headers(self) -> dict[str, str]:
        """Standard ``X-RateLimit-*`` headers for the HTTP response."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
        }
        if not self.allowed:
            headers["Retry-After"] = str(max(1, self.retry_after_seconds))
        return headers


@runtime_checkable
class RateLimiter(Protocol):
    """Consumes one unit of quota for ``key``."""

    async def acquire(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult: ...

    async def reset(self, key: str) -> None: ...


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class InMemoryRateLimiter:
    """Token-bucket limiter for a single process.

    Correct for local development and single-instance deployments. Behind more
    than one replica each process keeps its own bucket, so the effective limit
    multiplies by the replica count — that is the point at which the Redis
    implementation should be wired in.
    """

    __slots__ = ("_buckets", "_lock", "_max_keys")

    def __init__(self, *, max_keys: int = 100_000) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()
        self._max_keys = max_keys

    async def acquire(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit and window_seconds must be positive")

        refill_per_second = limit / window_seconds
        now = time.monotonic()

        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._max_keys:
                    self._evict_stale(now, window_seconds)
                bucket = _Bucket(tokens=float(limit), updated_at=now)
                self._buckets[key] = bucket
            else:
                elapsed = now - bucket.updated_at
                bucket.tokens = min(float(limit), bucket.tokens + elapsed * refill_per_second)
                bucket.updated_at = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return RateLimitResult(
                    allowed=True,
                    limit=limit,
                    remaining=int(bucket.tokens),
                    retry_after_seconds=0,
                )

            deficit = 1.0 - bucket.tokens
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                retry_after_seconds=max(1, int(deficit / refill_per_second) + 1),
            )

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._buckets.pop(key, None)

    def _evict_stale(self, now: float, window_seconds: int) -> None:
        """Drop buckets that have had time to refill completely.

        Called only when the key ceiling is reached, so an attacker cycling
        keys cannot grow the map without bound.
        """
        cutoff = now - window_seconds
        stale = [key for key, bucket in self._buckets.items() if bucket.updated_at < cutoff]
        for key in stale:
            del self._buckets[key]
        if not stale:
            # Nothing refilled yet: shed the oldest tenth to stay bounded.
            oldest = sorted(self._buckets.items(), key=lambda item: item[1].updated_at)
            for key, _ in oldest[: max(1, len(oldest) // 10)]:
                del self._buckets[key]


class NullRateLimiter:
    """Always allows. Used when rate limiting is disabled by configuration."""

    async def acquire(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        return RateLimitResult(allowed=True, limit=limit, remaining=limit, retry_after_seconds=0)

    async def reset(self, key: str) -> None:
        return None
