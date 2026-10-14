"""Token-bucket sliding-window rate limiter.

PROJECT.md §6 & §7: Phase 6 Hardening - rate limiting for API endpoints.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window rate limiter."""

    def __init__(self, requests_per_minute: int = 60, window_seconds: float = 60.0) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, key: str) -> tuple[bool, int]:
        """Check if request for key is within allowed quota.

        Returns (is_allowed, retry_after_seconds).
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._lock:
            # Prune timestamps outside current sliding window
            timestamps = [t for t in self._history[key] if t > cutoff]
            self._history[key] = timestamps

            if len(timestamps) >= self.requests_per_minute:
                oldest = timestamps[0]
                retry_after = max(1, int(cutoff + self.window_seconds - oldest + 1))
                return False, retry_after

            self._history[key].append(now)
            return True, 0

    def reset(self) -> None:
        """Clear all rate limit state (useful in testing)."""
        self._history.clear()


# Default global rate limiter instances
default_api_limiter = SlidingWindowRateLimiter(requests_per_minute=60)
trigger_rate_limiter = SlidingWindowRateLimiter(requests_per_minute=10)


def get_client_ip(request: Request) -> str:
    """Extract client IP handling reverse proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def RateLimitGuard(  # noqa: N802
    limiter: SlidingWindowRateLimiter,
) -> Callable[[Request], Coroutine[Any, Any, None]]:
    """FastAPI dependency factory enforcing sliding-window rate limits."""

    async def _guard(request: Request) -> None:
        key = get_client_ip(request)
        allowed, retry_after = await limiter.check_rate_limit(key)
        if not allowed:
            logger.warning("Rate limit exceeded for client %s (retry_after=%ds)", key, retry_after)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    return _guard
