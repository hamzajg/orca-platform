"""
services/rate_limiter.py — Per-key sliding-window rate limiter.

Uses a simple in-memory deque of timestamps per key.
No Redis required — works fine for a single-gateway deployment.

Algorithm: sliding window counter.
  - Keep a deque of request timestamps for each key.
  - On each request, drop all timestamps older than 60 seconds.
  - If len(deque) >= limit → reject with HTTP 429.
  - Otherwise append current timestamp → allow.

Thread/async safety: a single asyncio.Lock per key prevents races.

Usage:
    limiter = RateLimiter()                         # one instance on app.state
    allowed, retry_after = await limiter.check("my-key", limit=60)
    if not allowed:
        raise HTTPException(429, detail=f"Rate limit exceeded. Retry after {retry_after}s")
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Optional


class RateLimiter:
    """
    Sliding-window rate limiter.  One instance lives on app.state.rate_limiter.
    """

    WINDOW_SECONDS = 60  # sliding window size

    def __init__(self) -> None:
        # key → deque of float timestamps (monotonic)
        self._windows: dict[str, deque] = defaultdict(deque)
        # key → asyncio.Lock  (created lazily)
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_lock(self, key: str) -> asyncio.Lock:
        """Lazily create per-key lock."""
        async with self._global_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def check(self, key: str, limit: int) -> tuple[bool, int]:
        """
        Check whether `key` is within its rate limit.

        Args:
            key:   The API key string (or any unique identifier).
            limit: Maximum requests allowed per 60-second window.
                   0 means unlimited.

        Returns:
            (allowed: bool, retry_after_seconds: int)
            retry_after_seconds is 0 when allowed=True.
        """
        if limit <= 0:
            return True, 0

        lock = await self._get_lock(key)
        async with lock:
            now = time.monotonic()
            window = self._windows[key]
            cutoff = now - self.WINDOW_SECONDS

            # Evict expired timestamps from the left
            while window and window[0] < cutoff:
                window.popleft()

            if len(window) >= limit:
                # Earliest timestamp in window tells us when a slot opens
                oldest = window[0]
                retry_after = int(oldest + self.WINDOW_SECONDS - now) + 1
                return False, max(retry_after, 1)

            window.append(now)
            return True, 0

    def current_usage(self, key: str) -> int:
        """Return current request count in the sliding window (for metrics)."""
        now = time.monotonic()
        cutoff = now - self.WINDOW_SECONDS
        window = self._windows.get(key)
        if not window:
            return 0
        return sum(1 for ts in window if ts >= cutoff)

    def reset(self, key: str) -> None:
        """Clear the rate-limit window for a key (admin use)."""
        self._windows.pop(key, None)
