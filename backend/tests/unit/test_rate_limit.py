"""Token-bucket rate limiting."""

from __future__ import annotations

import asyncio

import pytest

from app.core.rate_limit import InMemoryRateLimiter, NullRateLimiter, RateLimiter

pytestmark = pytest.mark.unit


def run(coro):
    """Run a coroutine without depending on pytest-asyncio for these tests."""
    return asyncio.run(coro)


class TestProtocol:
    def test_both_implementations_satisfy_the_protocol(self) -> None:
        assert isinstance(InMemoryRateLimiter(), RateLimiter)
        assert isinstance(NullRateLimiter(), RateLimiter)


class TestQuota:
    def test_allows_up_to_the_limit_then_refuses(self) -> None:
        async def scenario() -> None:
            limiter = InMemoryRateLimiter()
            for expected_remaining in (2, 1, 0):
                result = await limiter.acquire("u1", limit=3, window_seconds=60)
                assert result.allowed
                assert result.remaining == expected_remaining

            refused = await limiter.acquire("u1", limit=3, window_seconds=60)
            assert not refused.allowed
            assert refused.remaining == 0
            assert refused.retry_after_seconds >= 1

        run(scenario())

    def test_keys_are_independent(self) -> None:
        async def scenario() -> None:
            limiter = InMemoryRateLimiter()
            for _ in range(3):
                await limiter.acquire("u1", limit=3, window_seconds=60)
            assert not (await limiter.acquire("u1", limit=3, window_seconds=60)).allowed
            assert (await limiter.acquire("u2", limit=3, window_seconds=60)).allowed

        run(scenario())

    def test_the_bucket_refills_over_time(self) -> None:
        async def scenario() -> None:
            limiter = InMemoryRateLimiter()
            assert (await limiter.acquire("k", limit=2, window_seconds=1)).allowed
            assert (await limiter.acquire("k", limit=2, window_seconds=1)).allowed
            assert not (await limiter.acquire("k", limit=2, window_seconds=1)).allowed
            await asyncio.sleep(0.6)
            # A token bucket refills continuously, so partial quota returns
            # before the full window elapses — unlike a fixed window, which
            # would allow two full quotas across a boundary.
            assert (await limiter.acquire("k", limit=2, window_seconds=1)).allowed

        run(scenario())

    def test_reset_clears_a_key(self) -> None:
        async def scenario() -> None:
            limiter = InMemoryRateLimiter()
            for _ in range(2):
                await limiter.acquire("k", limit=2, window_seconds=60)
            assert not (await limiter.acquire("k", limit=2, window_seconds=60)).allowed
            await limiter.reset("k")
            assert (await limiter.acquire("k", limit=2, window_seconds=60)).allowed

        run(scenario())


class TestHeaders:
    def test_a_refusal_carries_retry_after(self) -> None:
        async def scenario() -> None:
            limiter = InMemoryRateLimiter()
            await limiter.acquire("k", limit=1, window_seconds=60)
            headers = (await limiter.acquire("k", limit=1, window_seconds=60)).as_headers()
            assert headers["Retry-After"]
            assert headers["X-RateLimit-Limit"] == "1"
            assert headers["X-RateLimit-Remaining"] == "0"

        run(scenario())

    def test_an_allowed_request_has_no_retry_after(self) -> None:
        async def scenario() -> None:
            limiter = InMemoryRateLimiter()
            headers = (await limiter.acquire("k", limit=5, window_seconds=60)).as_headers()
            assert "Retry-After" not in headers

        run(scenario())


class TestBoundedMemory:
    def test_the_bucket_map_stays_bounded(self) -> None:
        # An attacker cycling keys must not be able to grow the map without
        # limit.
        async def scenario() -> None:
            limiter = InMemoryRateLimiter(max_keys=10)
            for index in range(200):
                await limiter.acquire(f"k{index}", limit=5, window_seconds=60)
            assert len(limiter._buckets) <= 11

        run(scenario())


class TestValidation:
    @pytest.mark.parametrize(("limit", "window"), [(0, 60), (5, 0), (-1, 60)])
    def test_rejects_a_nonsensical_quota(self, limit: int, window: int) -> None:
        async def scenario() -> None:
            with pytest.raises(ValueError):
                await InMemoryRateLimiter().acquire("k", limit=limit, window_seconds=window)

        run(scenario())


class TestNullLimiter:
    def test_always_allows(self) -> None:
        async def scenario() -> None:
            limiter = NullRateLimiter()
            for _ in range(100):
                assert (await limiter.acquire("k", limit=1, window_seconds=1)).allowed
            await limiter.reset("k")

        run(scenario())
