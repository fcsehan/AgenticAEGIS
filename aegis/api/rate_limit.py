"""AEGIS-1305: Token-Bucket Rate Limiting.

Per-client rate limiting for the Guard API.
Configurable via AEGIS_RATE_LIMIT_RPS and AEGIS_RATE_LIMIT_BURST.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse


class TokenBucket:
    """Thread-safe token bucket for rate limiting."""

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self) -> bool:
        """Try to consume a token. Returns True if allowed."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    @property
    def retry_after(self) -> float:
        """Seconds until next token is available."""
        with self._lock:
            if self._tokens >= 1.0:
                return 0.0
            return (1.0 - self._tokens) / self._rate


class RateLimiter:
    """Per-client rate limiter using token buckets.

    Clients are identified by X-API-Key header or IP address.
    /health and /metrics are exempt.
    """

    def __init__(self, rate: float = 100.0, burst: int = 200) -> None:
        self._rate = rate
        self._burst = burst
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, client_id: str) -> TokenBucket:
        with self._lock:
            if client_id not in self._buckets:
                self._buckets[client_id] = TokenBucket(self._rate, self._burst)
            return self._buckets[client_id]

    async def __call__(
        self, request: Request, call_next: Any
    ) -> Response:
        # Exempt health and metrics endpoints
        path = request.url.path
        if path in ("/v1/health", "/metrics"):
            return await call_next(request)  # type: ignore[no-any-return]

        client_id = request.headers.get(
            "X-API-Key",
            request.client.host if request.client else "unknown",
        )
        bucket = self._get_bucket(client_id)

        if not bucket.consume():
            retry_after = bucket.retry_after
            return JSONResponse(
                status_code=429,
                content={
                    "type": "about:blank",
                    "title": "Too Many Requests",
                    "status": 429,
                    "detail": "Rate limit exceeded",
                },
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        return await call_next(request)  # type: ignore[no-any-return]
