"""
Rate Limiting Middleware for CLONNECT API
Implements per-IP and per-user rate limiting using token bucket algorithm.
"""
import os
import time
import logging
from typing import Dict, Tuple
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimitBucket:
    """Token bucket for rate limiting."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_size: int = 10
    ):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        self.burst_size = burst_size

        # Storage: key -> (tokens_minute, tokens_hour, last_refill)
        self.buckets: Dict[str, Tuple[float, float, float]] = {}

    def _refill(self, key: str) -> Tuple[float, float]:
        """Refill tokens based on elapsed time."""
        if key not in self.buckets:
            return float(self.rpm), float(self.rph)

        tokens_min, tokens_hour, last_refill = self.buckets[key]
        now = time.time()
        elapsed = now - last_refill

        # Refill rates
        refill_min = self.rpm / 60 * elapsed
        refill_hour = self.rph / 3600 * elapsed

        tokens_min = min(self.rpm + self.burst_size, tokens_min + refill_min)
        tokens_hour = min(self.rph, tokens_hour + refill_hour)

        return tokens_min, tokens_hour

    def check(self, key: str, cost: float = 1.0) -> Tuple[bool, str, Dict]:
        """
        Check if request is allowed.

        Returns:
            Tuple of (allowed, reason, headers)
        """
        tokens_min, tokens_hour = self._refill(key)
        now = time.time()

        headers = {
            "X-RateLimit-Limit-Minute": str(self.rpm),
            "X-RateLimit-Remaining-Minute": str(int(max(0, tokens_min - cost))),
            "X-RateLimit-Limit-Hour": str(self.rph),
            "X-RateLimit-Remaining-Hour": str(int(max(0, tokens_hour - cost))),
        }

        if tokens_min < cost:
            headers["Retry-After"] = "60"
            return False, "Rate limit exceeded (per minute)", headers

        if tokens_hour < cost:
            headers["Retry-After"] = "3600"
            return False, "Rate limit exceeded (per hour)", headers

        # Consume tokens
        self.buckets[key] = (tokens_min - cost, tokens_hour - cost, now)

        # Evict stale entries to prevent memory leak (every 500 entries)
        if len(self.buckets) > 500:
            stale_cutoff = now - 3600  # Remove entries inactive for 1h
            stale_keys = [k for k, (_, _, ts) in self.buckets.items() if ts < stale_cutoff]
            for k in stale_keys:
                del self.buckets[k]

        return True, "OK", headers

    def reset(self, key: str):
        """Reset rate limit for a key."""
        if key in self.buckets:
            del self.buckets[key]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Features:
    - Per-IP rate limiting
    - Per-user rate limiting (via API key header)
    - Configurable limits for different endpoints
    - Returns proper 429 responses with retry headers
    """

    # Paths that should be excluded from rate limiting
    EXCLUDED_PATHS = {
        "/health",
        "/",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    }

    # Paths with higher limits (webhooks need more throughput)
    HIGH_LIMIT_PATHS = {
        "/webhook/instagram",
        "/webhook/telegram",
        "/webhook/stripe",
        "/webhook/hotmart",
        "/webhook/whatsapp",
    }

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        webhook_rpm: int = 200,
    ):
        super().__init__(app)
        self.default_bucket = RateLimitBucket(requests_per_minute, requests_per_hour)
        self.webhook_bucket = RateLimitBucket(webhook_rpm, webhook_rpm * 60)
        self.enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

    def _get_client_key(self, request: Request) -> str:
        """Get unique identifier for the client."""
        # Try to get API key from header first
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"api:{api_key[:16]}"

        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Get first IP in chain (original client)
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # Skip excluded paths
        if path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Get client identifier
        client_key = self._get_client_key(request)

        # Choose bucket based on path
        if any(path.startswith(p) for p in self.HIGH_LIMIT_PATHS):
            bucket = self.webhook_bucket
        else:
            bucket = self.default_bucket

        # Check rate limit
        allowed, reason, headers = bucket.check(client_key)

        if not allowed:
            logger.warning(f"Rate limited: {client_key} on {path} - {reason}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": reason,
                    "error": "rate_limit_exceeded",
                },
                headers=headers
            )

        # Add rate limit headers to successful response
        response = await call_next(request)
        for key, value in headers.items():
            response.headers[key] = value

        return response


# Global instance
_rate_limit_middleware = None


def get_rate_limit_middleware() -> RateLimitBucket:
    """Get global rate limit bucket for manual checks."""
    global _rate_limit_middleware
    if _rate_limit_middleware is None:
        _rate_limit_middleware = RateLimitBucket()
    return _rate_limit_middleware
