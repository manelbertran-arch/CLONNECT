"""Tests for Sprint top-6: DNA Engine auto-create 4-layer limiter.

Covers:
  1. Fresh acquire returns True (creation path opens)
  2. Per-lead debounce: second acquire within 60s returns False
  3. Token bucket: after 20 acquires for same creator, 21st returns False
  4. Global semaphore caps concurrent in-flight creates to 3
  5. Circuit breaker: trip_circuit → next acquire returns False (300s window)
  6. Idempotence: after bucket refill (window elapses), new acquires re-open
  7. Release semaphore counts correctly (double-release is a warning, not a crash)
  8. Different leads for same creator do NOT share the debounce key
  9. Separate creators have separate buckets (isolation)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


pytestmark = pytest.mark.asyncio


@pytest.fixture
def limiter():
    from services.dna_auto_create_limiter import DnaAutoCreateLimiter
    return DnaAutoCreateLimiter()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Happy path: fresh acquire returns True
# ─────────────────────────────────────────────────────────────────────────────

async def test_dna_limiter_fresh_acquire_returns_true(limiter):
    admitted = await limiter.acquire("iris_bertran", "lead_001", now=1000.0)
    assert admitted is True
    limiter.release()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Per-lead debounce
# ─────────────────────────────────────────────────────────────────────────────

async def test_dna_limiter_debounce_blocks_second_attempt(limiter):
    first = await limiter.acquire("iris_bertran", "lead_001", now=1000.0)
    assert first is True
    limiter.release()

    # 30s later — within 60s debounce window
    second = await limiter.acquire("iris_bertran", "lead_001", now=1030.0)
    assert second is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Token bucket cap
# ─────────────────────────────────────────────────────────────────────────────

async def test_dna_limiter_token_bucket_caps_per_creator(limiter):
    # Use distinct leads so debounce doesn't interfere.
    # Space requests by only 1s so the bucket refills negligibly (1/3600 of window).
    # With capacity=20 and ~25 requests in a 25s span, ≥5 denials must occur.
    admitted_count = 0
    denied_count = 0
    for i in range(25):
        t = 1000.0 + i * 1.0
        admitted = await limiter.acquire("iris_bertran", f"lead_{i:03d}", now=t)
        if admitted:
            admitted_count += 1
            limiter.release()
        else:
            denied_count += 1
    # Capacity 20; refill during 25s is 25 * (20/3600) ≈ 0.14 tokens. Admits ≤ ~20.
    assert admitted_count <= 21
    assert denied_count >= 4, (
        f"Expected at least 4 denials under fast-fire (25 in 25s), got "
        f"admitted={admitted_count} denied={denied_count}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Global semaphore concurrency cap
# ─────────────────────────────────────────────────────────────────────────────

async def test_dna_limiter_global_semaphore_caps_concurrency(limiter):
    from services.dna_auto_create_limiter import GLOBAL_CONCURRENCY
    # Acquire GLOBAL_CONCURRENCY in-flight permits; the next acquire must await.
    t = 1000.0
    acquired_permits = []
    for i in range(GLOBAL_CONCURRENCY):
        admitted = await limiter.acquire("iris_bertran", f"lead_{i}", now=t + i * 61.0)
        assert admitted
        acquired_permits.append(True)

    # One more acquire for a brand-new lead: the internal semaphore is drained,
    # so this acquire will block. Use a small timeout to assert "blocks".
    async def _next_acquire():
        return await limiter.acquire("iris_bertran", "lead_overflow",
                                     now=t + GLOBAL_CONCURRENCY * 61.0 + 61.0)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_next_acquire(), timeout=0.1)

    # Release all permits so the test tears down cleanly.
    for _ in acquired_permits:
        limiter.release()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Circuit breaker
# ─────────────────────────────────────────────────────────────────────────────

async def test_dna_limiter_circuit_breaker_blocks_until_window_expires(limiter):
    limiter.trip_circuit("iris_bertran", now=1000.0)

    # Within the 300s window
    blocked = await limiter.acquire("iris_bertran", "lead_xyz", now=1100.0)
    assert blocked is False

    # After the window
    reopened = await limiter.acquire("iris_bertran", "lead_after", now=1301.0)
    assert reopened is True
    limiter.release()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Idempotence after debounce window
# ─────────────────────────────────────────────────────────────────────────────

async def test_dna_limiter_debounce_releases_after_window(limiter):
    first = await limiter.acquire("iris_bertran", "lead_001", now=1000.0)
    assert first is True
    limiter.release()

    # 61s later — past the 60s debounce
    second = await limiter.acquire("iris_bertran", "lead_001", now=1061.0)
    assert second is True
    limiter.release()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Release safety — double release does not crash
# ─────────────────────────────────────────────────────────────────────────────

async def test_dna_limiter_double_release_is_safe(limiter):
    admitted = await limiter.acquire("iris_bertran", "lead_001", now=1000.0)
    assert admitted
    limiter.release()
    # Second release should be silently tolerated (logged warning, no exception).
    limiter.release()


# ─────────────────────────────────────────────────────────────────────────────
# 8. Per-lead debounce isolation
# ─────────────────────────────────────────────────────────────────────────────

async def test_dna_limiter_different_leads_same_creator_independent(limiter):
    first = await limiter.acquire("iris_bertran", "lead_A", now=1000.0)
    assert first is True
    limiter.release()

    # Different lead, same creator, same timestamp — must NOT be debounced.
    second = await limiter.acquire("iris_bertran", "lead_B", now=1000.0)
    assert second is True
    limiter.release()


# ─────────────────────────────────────────────────────────────────────────────
# 9. Creator-level bucket isolation
# ─────────────────────────────────────────────────────────────────────────────

async def test_dna_limiter_separate_creators_separate_buckets(limiter):
    # Drain iris' bucket aggressively over a short time window.
    for i in range(20):
        admitted = await limiter.acquire("iris_bertran", f"lead_{i}", now=1000.0 + i * 61.0)
        if admitted:
            limiter.release()

    # Stefano has his own bucket — must still be admitted at a nearby timestamp.
    ok = await limiter.acquire("stefano", "lead_s", now=1100.0)
    assert ok is True
    limiter.release()
