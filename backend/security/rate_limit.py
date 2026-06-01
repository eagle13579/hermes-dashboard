"""
Rate Limit Middleware — in-process token-bucket rate limiter.

Design
------
* Uses an in-process token-bucket per client IP.
* Configurable via ``settings.rate_limit_per_minute`` (default: 0 = off).
* Buckets are cleaned up every 60 seconds to prevent memory leaks.
* For production, replace with Redis-backed rate limiting (e.g. slowapi).

Note
----
This is a minimal in-process implementation suitable for single-worker
deployments. For multi-worker / multi-host setups, use a Redis-backed
solution such as ``slowapi`` or ``fastapi-limiter``.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)


class TokenBucket:
    """Simple token-bucket rate limiter.

    Attributes
    ----------
    capacity : int
        Maximum number of tokens (burst allowance).
    refill_rate : float
        Tokens added per second.
    tokens : float
        Current token count.
    last_refill : float
        Timestamp of last refill.
    """

    __slots__ = ("capacity", "refill_rate", "tokens", "last_refill")

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume *tokens* from the bucket.

        Returns
        -------
        bool
            ``True`` if tokens were consumed, ``False`` if rate-limited.
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now

        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies token-bucket rate limiting per IP.

    The limit is configured via ``settings.rate_limit_per_minute``.
    When set to 0 (or less) rate limiting is disabled.
    """

    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)
        self._buckets: dict[str, TokenBucket] = {}
        self._last_cleanup: float = time.monotonic()

        limit = settings.rate_limit_per_minute
        if limit > 0:
            self._enabled = True
            # Allow a small burst (20 % above the per-minute rate)
            self._capacity = int(limit * 1.2)
            self._refill_rate = limit / 60.0
            logger.info(
                "Rate limiting enabled: %d req/min (burst: %d)",
                limit,
                self._capacity,
            )
        else:
            self._enabled = False
            logger.info("Rate limiting disabled (rate_limit_per_minute=0)")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self._enabled:
            return await call_next(request)

        # Determine client identity
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        # Exempt health check from rate limiting
        if request.url.path == "/health":
            return await call_next(request)

        # Get or create bucket
        bucket = self._buckets.get(client_ip)
        if bucket is None:
            bucket = TokenBucket(self._capacity, self._refill_rate)
            self._buckets[client_ip] = bucket

        if not bucket.consume():
            logger.debug("Rate-limited IP: %s", client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": "Too many requests. Please slow down.",
                    "retry_after_seconds": math.ceil(
                        (1.0 / self._refill_rate) if self._refill_rate > 0 else 60
                    ),
                },
                headers={"Retry-After": str(math.ceil(60.0 / self._refill_rate))},
            )

        response = await call_next(request)
        return response

    def _cleanup_stale_buckets(self) -> None:
        """Remove buckets that haven't been touched in over 5 minutes."""
        now = time.monotonic()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        stale_ips = [
            ip
            for ip, bucket in self._buckets.items()
            if now - bucket.last_refill > 300
        ]
        for ip in stale_ips:
            del self._buckets[ip]
        if stale_ips:
            logger.debug("Cleaned up %d stale rate-limit buckets", len(stale_ips))
