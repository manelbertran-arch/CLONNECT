"""Audit tests for core/rate_limiter.py."""

import time

from core.rate_limiter import RateLimiter, get_rate_limiter

# =========================================================================
# TEST 1: Init / Import
# =========================================================================


class TestRateLimiterInit:
    """Verify RateLimiter initialization and defaults."""

    def test_default_limits(self):
        """RateLimiter has sensible default limits for Instagram."""
        limiter = RateLimiter()
        assert limiter.rpm == 20
        assert limiter.rph == 200
        assert limiter.rpd == 1000

    def test_custom_limits(self):
        """RateLimiter accepts custom limits."""
        limiter = RateLimiter(
            requests_per_minute=5,
            requests_per_hour=50,
            requests_per_day=500,
        )
        assert limiter.rpm == 5
        assert limiter.rph == 50
        assert limiter.rpd == 500

    def test_buckets_start_empty(self):
        """No buckets exist until a key is first checked."""
        limiter = RateLimiter()
        assert len(limiter.buckets) == 0

    def test_stats_empty(self):
        """stats() reports zero tracked keys for fresh limiter."""
        limiter = RateLimiter()
        s = limiter.stats()
        assert s["tracked_keys"] == 0
        assert s["limits"]["per_minute"] == 20

    def test_get_rate_limiter_singleton(self):
        """get_rate_limiter returns a singleton RateLimiter."""
        import core.rate_limiter as mod

        mod._rate_limiter = None
        r1 = get_rate_limiter()
        r2 = get_rate_limiter()
        assert r1 is r2
        mod._rate_limiter = None  # Cleanup


# =========================================================================
# TEST 2: Happy Path - Under Limit Allowed
# =========================================================================


class TestUnderLimitAllowed:
    """Requests under the limit are allowed."""

    def test_first_request_allowed(self):
        """The very first request for a key is always allowed."""
        limiter = RateLimiter()
        allowed, reason = limiter.check_limit("user1")
        assert allowed is True
        assert reason == "OK"

    def test_multiple_requests_under_limit(self):
        """Multiple requests under the minute limit all succeed."""
        limiter = RateLimiter(requests_per_minute=10)
        for i in range(9):
            allowed, _ = limiter.check_limit("user1")
            assert allowed is True, f"Request {i+1} should be allowed"

    def test_get_remaining_shows_deduction(self):
        """get_remaining reflects consumed tokens."""
        limiter = RateLimiter(requests_per_minute=10, requests_per_hour=100, requests_per_day=1000)
        limiter.check_limit("user1")
        limiter.check_limit("user1")
        remaining = limiter.get_remaining("user1")
        assert remaining["minute"] <= 8  # At least 2 consumed
        assert remaining["hour"] <= 98

    def test_different_keys_independent(self):
        """Different keys have independent rate limits."""
        limiter = RateLimiter(requests_per_minute=2)
        limiter.check_limit("user_a")
        limiter.check_limit("user_a")
        # user_a is at limit, but user_b should still be allowed
        allowed_b, _ = limiter.check_limit("user_b")
        assert allowed_b is True

    def test_stats_after_requests(self):
        """stats() reports tracked keys after requests are made."""
        limiter = RateLimiter()
        limiter.check_limit("alpha")
        limiter.check_limit("beta")
        s = limiter.stats()
        assert s["tracked_keys"] == 2


# =========================================================================
# TEST 3: Edge Case - Over Limit Blocked
# =========================================================================


class TestOverLimitBlocked:
    """Requests over the limit are rejected."""

    def test_minute_limit_blocks(self):
        """Exceeding per-minute limit returns False."""
        limiter = RateLimiter(requests_per_minute=2, requests_per_hour=200, requests_per_day=1000)
        limiter.check_limit("user1")
        limiter.check_limit("user1")
        allowed, reason = limiter.check_limit("user1")
        assert allowed is False
        assert "minuto" in reason.lower() or "minute" in reason.lower()

    def test_hour_limit_blocks(self):
        """Exceeding per-hour limit returns False with hour message."""
        limiter = RateLimiter(requests_per_minute=1000, requests_per_hour=3, requests_per_day=10000)
        limiter.check_limit("user1")
        limiter.check_limit("user1")
        limiter.check_limit("user1")
        allowed, reason = limiter.check_limit("user1")
        assert allowed is False
        assert "hora" in reason.lower() or "hour" in reason.lower()

    def test_day_limit_blocks(self):
        """Exceeding per-day limit returns False with day message."""
        limiter = RateLimiter(requests_per_minute=1000, requests_per_hour=1000, requests_per_day=2)
        limiter.check_limit("user1")
        limiter.check_limit("user1")
        allowed, reason = limiter.check_limit("user1")
        assert allowed is False
        assert "diario" in reason.lower() or "d\u00eda" in reason.lower()

    def test_cost_parameter_consumes_more(self):
        """cost > 1.0 consumes multiple tokens at once."""
        limiter = RateLimiter(requests_per_minute=5, requests_per_hour=500, requests_per_day=5000)
        allowed, _ = limiter.check_limit("user1", cost=4.0)
        assert allowed is True
        # Only 1 token left in minute bucket
        allowed, _ = limiter.check_limit("user1", cost=2.0)
        assert allowed is False

    def test_blocked_key_reason_is_not_empty(self):
        """Blocked requests always include a non-empty reason."""
        limiter = RateLimiter(requests_per_minute=1)
        limiter.check_limit("user1")
        allowed, reason = limiter.check_limit("user1")
        assert not allowed
        assert len(reason) > 0


# =========================================================================
# TEST 4: Error Handling - Reset After Window
# =========================================================================


class TestResetAfterWindow:
    """Token refill and reset behavior."""

    def test_reset_removes_bucket(self):
        """reset() removes the key from buckets entirely."""
        limiter = RateLimiter()
        limiter.check_limit("user1")
        assert "user1" in limiter.buckets
        limiter.reset("user1")
        assert "user1" not in limiter.buckets

    def test_reset_nonexistent_key_no_error(self):
        """reset() on a key that doesn't exist does not raise."""
        limiter = RateLimiter()
        limiter.reset("nonexistent")  # Should not raise

    def test_tokens_refill_over_time(self):
        """Tokens refill based on elapsed time since last check."""
        limiter = RateLimiter(requests_per_minute=2, requests_per_hour=200, requests_per_day=1000)
        limiter.check_limit("user1")
        limiter.check_limit("user1")
        # Blocked now
        allowed_before, _ = limiter.check_limit("user1")
        assert allowed_before is False

        # Simulate time passing (manipulate bucket timestamp)
        tokens_min, tokens_hour, tokens_day, _ = limiter.buckets["user1"]
        old_time = time.time() - 120  # 2 minutes ago
        limiter.buckets["user1"] = (tokens_min, tokens_hour, tokens_day, old_time)

        # After refill, should be allowed again
        allowed_after, _ = limiter.check_limit("user1")
        assert allowed_after is True

    def test_refill_capped_at_max(self):
        """Tokens do not exceed the max bucket capacity after refill."""
        limiter = RateLimiter(requests_per_minute=5)
        # Set bucket timestamp far in the past to trigger large refill
        now = time.time()
        limiter.buckets["user1"] = (0.0, 200.0, 1000.0, now - 3600)
        limiter._refill_tokens("user1")
        tokens_min = limiter.buckets["user1"][0]
        assert tokens_min <= limiter.rpm  # Capped at 5

    def test_get_remaining_after_reset(self):
        """After reset, next get_remaining creates fresh bucket at max."""
        limiter = RateLimiter(requests_per_minute=10, requests_per_hour=100, requests_per_day=1000)
        limiter.check_limit("user1")
        limiter.reset("user1")
        remaining = limiter.get_remaining("user1")
        assert remaining["minute"] == 10
        assert remaining["hour"] == 100


# =========================================================================
# TEST 5: Integration - Concurrent Check Simulation
# =========================================================================


class TestConcurrentCheckSimulation:
    """Simulated concurrent access patterns."""

    def test_multiple_users_simultaneous(self):
        """Multiple users making requests simultaneously are tracked independently."""
        limiter = RateLimiter(requests_per_minute=3)
        users = [f"user_{i}" for i in range(10)]
        for user in users:
            allowed, _ = limiter.check_limit(user)
            assert allowed is True
        assert limiter.stats()["tracked_keys"] == 10

    def test_burst_then_wait(self):
        """After a burst that hits the limit, time travel allows requests again."""
        limiter = RateLimiter(requests_per_minute=3, requests_per_hour=1000, requests_per_day=10000)
        for _ in range(3):
            limiter.check_limit("burst_user")
        allowed, _ = limiter.check_limit("burst_user")
        assert allowed is False

        # Time travel: set last refill to 2 minutes ago
        t_min, t_hour, t_day, _ = limiter.buckets["burst_user"]
        limiter.buckets["burst_user"] = (t_min, t_hour, t_day, time.time() - 120)
        allowed, _ = limiter.check_limit("burst_user")
        assert allowed is True

    def test_interleaved_users(self):
        """Interleaved requests from two users don't cross-affect."""
        limiter = RateLimiter(requests_per_minute=2)
        limiter.check_limit("alice")
        limiter.check_limit("bob")
        limiter.check_limit("alice")
        # alice is at limit (2), bob should still have 1
        allowed_bob, _ = limiter.check_limit("bob")
        assert allowed_bob is True
        allowed_alice, _ = limiter.check_limit("alice")
        assert allowed_alice is False

    def test_stats_reflect_all_tracked(self):
        """stats accurately reflects the number of tracked keys."""
        limiter = RateLimiter()
        for i in range(25):
            limiter.check_limit(f"key_{i}")
        assert limiter.stats()["tracked_keys"] == 25

    def test_get_or_create_bucket_idempotent(self):
        """_get_or_create_bucket creates once, then returns existing."""
        limiter = RateLimiter()
        b1 = limiter._get_or_create_bucket("test_key")
        b2 = limiter._get_or_create_bucket("test_key")
        assert b1 == b2
