"""4-layer rate-limiter for DNA Engine auto-create.

Sprint top-6 (2026-04-23). Spec: docs/forensic/dna_engine_create/04_state_of_art.md
and docs/forensic/dna_engine_create/05_optimization.md.

Layers (checked in order):
  1. Per-lead debounce 60s     — block repeated create attempts for same lead
  2. Token bucket 20/hour/creator — cap the rate per creator
  3. Global semaphore 3        — cap in-flight concurrent creates process-wide
  4. LLM-fallback circuit breaker 300s — skip when the relationship detector has been
     failing (Gemini 429 etc.); avoids cascading failures.

All state is in-process (single-node Railway deployment). Redis is intentionally
avoided; see 04_state_of_art.md §5 for the rationale.

Usage:
    limiter = get_dna_auto_create_limiter()
    if await limiter.acquire(creator_id, follower_id):
        try:
            await _do_the_create()
        except SomeLLMDownstreamError:
            limiter.trip_circuit(creator_id)
            raise
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Tunables (constants intentionally at module scope for easy tests) ──────
DEBOUNCE_SECONDS: int = 60
TOKEN_BUCKET_CAPACITY: int = 20
TOKEN_BUCKET_WINDOW_SECONDS: int = 3600
GLOBAL_CONCURRENCY: int = 3
CIRCUIT_OPEN_SECONDS: int = 300


@dataclass
class _CreatorBucket:
    """Simple refill-on-read token bucket. Not thread-safe; guarded by Lock."""
    capacity: int = TOKEN_BUCKET_CAPACITY
    window: int = TOKEN_BUCKET_WINDOW_SECONDS
    tokens: float = field(default_factory=lambda: float(TOKEN_BUCKET_CAPACITY))
    last_refill_ts: float = field(default_factory=time.monotonic)

    def try_consume(self, now: float) -> bool:
        elapsed = max(0.0, now - self.last_refill_ts)
        self.tokens = min(self.capacity, self.tokens + (elapsed * self.capacity / self.window))
        self.last_refill_ts = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class DnaAutoCreateLimiter:
    """4-layer limiter. Single shared instance via ``get_dna_auto_create_limiter``."""

    def __init__(self) -> None:
        self._debounce: Dict[Tuple[str, str], float] = {}
        self._buckets: Dict[str, _CreatorBucket] = {}
        self._circuit_open_until: Dict[str, float] = {}
        self._semaphore = asyncio.Semaphore(GLOBAL_CONCURRENCY)
        self._lock = asyncio.Lock()

    async def acquire(self, creator_id: str, follower_id: str, *, now: Optional[float] = None) -> bool:
        """Return True iff all four layers admit this creation attempt.

        Acquires the global semaphore when True. The caller MUST invoke
        ``release()`` in a finally block after the create completes.

        When False: the caller should skip the create silently; no semaphore is held.
        """
        t = now if now is not None else time.monotonic()

        # Layer 4 — circuit breaker
        open_until = self._circuit_open_until.get(creator_id, 0.0)
        if t < open_until:
            logger.debug("[dna-limiter] circuit OPEN for %s, skipping", creator_id)
            return False

        # Layers 1+2 under a single lock (cheap state mutations)
        async with self._lock:
            key = (creator_id, follower_id)
            last = self._debounce.get(key, 0.0)
            if t - last < DEBOUNCE_SECONDS:
                logger.debug("[dna-limiter] debounce hit (%ss) for %s/%s", t - last, creator_id, follower_id)
                return False

            bucket = self._buckets.get(creator_id)
            if bucket is None:
                bucket = _CreatorBucket()
                self._buckets[creator_id] = bucket
            if not bucket.try_consume(t):
                logger.debug("[dna-limiter] token bucket empty for %s", creator_id)
                return False

            # Commit debounce only after all non-concurrency layers admitted.
            self._debounce[key] = t

        # Layer 3 — global concurrency.
        await self._semaphore.acquire()
        return True

    def release(self) -> None:
        """Release the global semaphore after the create completes (success or failure)."""
        try:
            self._semaphore.release()
        except ValueError:
            # Defensive: calling release() without matching acquire() is a bug,
            # but we don't want it to crash the DM pipeline.
            logger.warning("[dna-limiter] release() called without matching acquire()")

    def trip_circuit(self, creator_id: str, *, now: Optional[float] = None) -> None:
        """Open the per-creator circuit for CIRCUIT_OPEN_SECONDS after downstream failure."""
        t = now if now is not None else time.monotonic()
        self._circuit_open_until[creator_id] = t + CIRCUIT_OPEN_SECONDS
        logger.warning("[dna-limiter] circuit TRIPPED for %s (open for %ss)", creator_id, CIRCUIT_OPEN_SECONDS)

    def reset_for_tests(self) -> None:
        """Test hook: drop all in-process state."""
        self._debounce.clear()
        self._buckets.clear()
        self._circuit_open_until.clear()
        self._semaphore = asyncio.Semaphore(GLOBAL_CONCURRENCY)


_LIMITER_SINGLETON: Optional[DnaAutoCreateLimiter] = None


def get_dna_auto_create_limiter() -> DnaAutoCreateLimiter:
    global _LIMITER_SINGLETON
    if _LIMITER_SINGLETON is None:
        _LIMITER_SINGLETON = DnaAutoCreateLimiter()
    return _LIMITER_SINGLETON
