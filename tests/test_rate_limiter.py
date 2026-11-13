"""
Sliding-window rate limiter — the gateway's only abuse guard on the hot path.

The smoke test covers the happy path; these pin the edges that actually
matter in production: window expiry, per-key isolation, retry_after math,
and the admin reset. Time is injected by writing timestamps straight into
the limiter's window deque, so the tests are deterministic — no sleeps.
"""
import time

import pytest

from app.services.rate_limiter import RateLimiter

WINDOW = RateLimiter.WINDOW_SECONDS


def _age_window(limiter: RateLimiter, key: str, age_seconds: float) -> None:
    """Backdate every timestamp in `key`'s window by `age_seconds`."""
    window = limiter._windows[key]
    for i, ts in enumerate(window):
        window[i] = ts - age_seconds


class TestWindowExpiry:
    async def test_old_requests_stop_counting(self):
        limiter = RateLimiter()
        for _ in range(3):
            await limiter.check("k", limit=3)

        # All three requests are now older than the window.
        _age_window(limiter, "k", WINDOW + 1)

        allowed, retry = await limiter.check("k", limit=3)
        assert allowed is True
        assert retry == 0

    async def test_partially_expired_window(self):
        limiter = RateLimiter()
        await limiter.check("k", limit=2)
        await limiter.check("k", limit=2)
        # Age only the *first* request past the window — it should be evicted,
        # leaving room for exactly one more.
        window = limiter._windows["k"]
        window[0] -= WINDOW + 1

        allowed, _ = await limiter.check("k", limit=2)
        assert allowed is True
        # …and the next one is blocked again.
        allowed, retry = await limiter.check("k", limit=2)
        assert allowed is False
        assert retry >= 1


class TestIsolation:
    async def test_keys_have_independent_windows(self):
        limiter = RateLimiter()
        for _ in range(2):
            await limiter.check("a", limit=2)
        blocked, _ = await limiter.check("a", limit=2)
        assert blocked is False

        # Key "b" is untouched.
        allowed, _ = await limiter.check("b", limit=2)
        assert allowed is True

    async def test_different_limits_per_key(self):
        limiter = RateLimiter()
        for _ in range(5):
            await limiter.check("strict", limit=5)
        for _ in range(1):
            await limiter.check("loose", limit=50)

        allowed_strict, _ = await limiter.check("strict", limit=5)
        allowed_loose, _ = await limiter.check("loose", limit=50)
        assert allowed_strict is False
        assert allowed_loose is True


class TestRetryAfter:
    async def test_retry_after_is_positive_and_bounded(self):
        limiter = RateLimiter()
        await limiter.check("k", limit=1)
        allowed, retry = await limiter.check("k", limit=1)
        assert allowed is False
        assert 1 <= retry <= WINDOW + 1

    async def test_retry_after_shrinks_as_window_ages(self):
        limiter = RateLimiter()
        await limiter.check("k", limit=1)
        _age_window(limiter, "k", WINDOW - 10)  # 10s left in window

        _, retry = await limiter.check("k", limit=1)
        assert retry <= 12


class TestUsageAndReset:
    async def test_current_usage_counts_only_in_window(self):
        limiter = RateLimiter()
        await limiter.check("k", limit=10)
        await limiter.check("k", limit=10)
        assert limiter.current_usage("k") == 2

        _age_window(limiter, "k", WINDOW + 1)
        # current_usage filters expired timestamps even before a check() runs.
        assert limiter.current_usage("k") == 0

    async def test_unknown_key_reports_zero(self):
        assert RateLimiter().current_usage("never-seen") == 0

    async def test_reset_clears_the_window(self):
        limiter = RateLimiter()
        await limiter.check("k", limit=1)
        blocked, _ = await limiter.check("k", limit=1)
        assert blocked is False

        limiter.reset("k")
        allowed, _ = await limiter.check("k", limit=1)
        assert allowed is True

    async def test_reset_unknown_key_is_a_noop(self):
        RateLimiter().reset("never-seen")  # must not raise
