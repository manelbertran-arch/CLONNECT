"""Audit tests for core/instagram_rate_limiter.py."""

import time

from core.instagram_rate_limiter import (
    InstagramRateLimiter,
    RateLimitState,
    get_instagram_rate_limiter,
)

# =========================================================================
# TEST 1: Init / Import
# =========================================================================


class TestInstagramRateLimiterInit:
    """Verify Instagram rate limiter initialization and defaults."""

    def test_class_constants(self):
        """Class-level limits are reasonable for Meta API."""
        assert InstagramRateLimiter.CALLS_PER_MINUTE == 15
        assert InstagramRateLimiter.CALLS_PER_HOUR == 190
        assert InstagramRateLimiter.CALLS_PER_DAY == 4500

    def test_backoff_constants(self):
        """Backoff configuration has expected values."""
        assert InstagramRateLimiter.INITIAL_BACKOFF_SECONDS == 5
        assert InstagramRateLimiter.MAX_BACKOFF_SECONDS == 300
        assert InstagramRateLimiter.BACKOFF_MULTIPLIER == 2

    def test_rate_limit_codes(self):
        """RATE_LIMIT_CODES contains known Meta rate limit codes."""
        codes = InstagramRateLimiter.RATE_LIMIT_CODES
        assert 429 in codes
        assert 503 in codes
        assert 613 in codes

    def test_fresh_limiter_empty(self):
        """New limiter has no states and empty call history."""
        limiter = InstagramRateLimiter()
        assert len(limiter._call_history) == 0
        # defaultdict creates on access but should have no pre-existing keys
        assert len(limiter._states.keys()) == 0

    def test_rate_limit_state_defaults(self):
        """RateLimitState has sensible defaults."""
        state = RateLimitState()
        assert state.calls_minute == []
        assert state.consecutive_errors == 0
        assert state.backoff_until == 0


# =========================================================================
# TEST 2: Happy Path - Rate Limit Check
# =========================================================================


class TestRateLimitCheck:
    """Requests within limits are allowed."""

    def test_first_request_allowed(self):
        """First request for a creator is always allowed."""
        limiter = InstagramRateLimiter()
        allowed, reason, wait = limiter.can_make_request("creator1")
        assert allowed is True
        assert reason == "OK"
        assert wait == 0

    def test_recording_a_call(self):
        """record_call stores the call in all time buckets."""
        limiter = InstagramRateLimiter()
        limiter.record_call("creator1", "/conversations", 200)
        state = limiter._states["creator1"]
        assert len(state.calls_minute) == 1
        assert len(state.calls_hour) == 1
        assert len(state.calls_day) == 1

    def test_multiple_calls_under_limit(self):
        """Multiple calls under the minute limit are all allowed."""
        limiter = InstagramRateLimiter()
        for i in range(10):
            limiter.record_call("creator1", "/test", 200)
        allowed, reason, wait = limiter.can_make_request("creator1")
        assert allowed is True

    def test_successful_call_resets_errors(self):
        """A 200 response resets consecutive_errors to zero."""
        limiter = InstagramRateLimiter()
        state = limiter._states["creator1"]
        state.consecutive_errors = 3
        limiter.record_call("creator1", "/test", 200)
        assert state.consecutive_errors == 0

    def test_call_history_recorded(self):
        """Global call history stores APICallRecord entries."""
        limiter = InstagramRateLimiter()
        limiter.record_call("creator1", "/conversations", 200)
        limiter.record_call("creator1", "/messages", 200)
        assert len(limiter._call_history) == 2
        assert limiter._call_history[0].endpoint == "/conversations"


# =========================================================================
# TEST 3: Edge Case - Cooldown / Backoff Behavior
# =========================================================================


class TestCooldownBehavior:
    """Backoff triggers on rate limit errors."""

    def test_rate_limit_error_triggers_backoff(self):
        """A 429 response triggers backoff."""
        limiter = InstagramRateLimiter()
        limiter.record_call("creator1", "/test", 429)
        state = limiter._states["creator1"]
        assert state.consecutive_errors == 1
        assert state.backoff_until > time.time()

    def test_backoff_blocks_requests(self):
        """During backoff, can_make_request returns False."""
        limiter = InstagramRateLimiter()
        limiter.record_call("creator1", "/test", 429)
        allowed, reason, wait = limiter.can_make_request("creator1")
        assert allowed is False
        assert "Backoff" in reason
        assert wait > 0

    def test_exponential_backoff_increases(self):
        """Consecutive errors increase backoff duration exponentially."""
        limiter = InstagramRateLimiter()
        limiter.record_call("creator1", "/test", 429)
        state = limiter._states["creator1"]
        backoff_1 = state.backoff_until - time.time()

        limiter.record_call("creator1", "/test", 429)
        backoff_2 = state.backoff_until - time.time()
        assert backoff_2 > backoff_1

    def test_backoff_capped_at_max(self):
        """Backoff duration never exceeds MAX_BACKOFF_SECONDS."""
        limiter = InstagramRateLimiter()
        # Simulate many consecutive errors
        for _ in range(20):
            limiter.record_call("creator1", "/test", 429)
        state = limiter._states["creator1"]
        remaining = state.backoff_until - time.time()
        assert remaining <= InstagramRateLimiter.MAX_BACKOFF_SECONDS + 1

    def test_reset_backoff(self):
        """reset_backoff clears errors and backoff for a creator."""
        limiter = InstagramRateLimiter()
        limiter.record_call("creator1", "/test", 429)
        result = limiter.reset_backoff("creator1")
        assert result["reset"] is True
        assert result["previous_errors"] == 1
        state = limiter._states["creator1"]
        assert state.consecutive_errors == 0
        assert state.backoff_until == 0


# =========================================================================
# TEST 4: Per-User (Per-Creator) Tracking
# =========================================================================


class TestPerCreatorTracking:
    """Each creator has independent rate limit state."""

    def test_independent_creators(self):
        """Two creators have separate rate limit counters."""
        limiter = InstagramRateLimiter()
        for _ in range(14):
            limiter.record_call("creator_a", "/test", 200)
        limiter.record_call("creator_b", "/test", 200)

        allowed_a, _, _ = limiter.can_make_request("creator_a")
        allowed_b, _, _ = limiter.can_make_request("creator_b")
        assert allowed_a is True  # 14 < 15 limit
        assert allowed_b is True

    def test_one_creator_blocked_other_free(self):
        """When one creator hits minute limit, the other is unaffected."""
        limiter = InstagramRateLimiter()
        for _ in range(15):
            limiter.record_call("spammer", "/test", 200)

        allowed_spammer, _, _ = limiter.can_make_request("spammer")
        allowed_good, _, _ = limiter.can_make_request("good_creator")
        assert allowed_spammer is False
        assert allowed_good is True

    def test_backoff_per_creator(self):
        """Backoff for one creator does not affect another."""
        limiter = InstagramRateLimiter()
        limiter.record_call("bad_creator", "/test", 429)
        allowed_bad, _, _ = limiter.can_make_request("bad_creator")
        allowed_good, _, _ = limiter.can_make_request("good_creator")
        assert allowed_bad is False
        assert allowed_good is True

    def test_minute_limit_hit(self):
        """Exactly CALLS_PER_MINUTE calls blocks the next request."""
        limiter = InstagramRateLimiter()
        for _ in range(InstagramRateLimiter.CALLS_PER_MINUTE):
            limiter.record_call("creator1", "/test", 200)
        allowed, reason, _ = limiter.can_make_request("creator1")
        assert allowed is False
        assert "minuto" in reason.lower() or "minute" in reason.lower()

    def test_clean_old_calls_removes_stale(self):
        """_clean_old_calls removes timestamps older than their windows."""
        limiter = InstagramRateLimiter()
        state = limiter._states["creator1"]
        old_time = time.time() - 120  # 2 minutes ago
        state.calls_minute = [old_time]
        state.calls_hour = [old_time]
        state.calls_day = [old_time]
        limiter._clean_old_calls(state)
        assert len(state.calls_minute) == 0  # >60s old, cleaned
        assert len(state.calls_hour) == 1  # <3600s old, kept
        assert len(state.calls_day) == 1  # <86400s old, kept


# =========================================================================
# TEST 5: Integration - Stats Reporting
# =========================================================================


class TestStatsReporting:
    """get_stats and get_call_history return accurate data."""

    def test_global_stats_empty(self):
        """Global stats for fresh limiter show zero calls."""
        limiter = InstagramRateLimiter()
        stats = limiter.get_stats()
        assert stats["total_creators"] == 0
        assert stats["calls_last_minute"] == 0
        assert stats["calls_last_hour"] == 0

    def test_creator_stats_after_calls(self):
        """Per-creator stats reflect recorded calls."""
        limiter = InstagramRateLimiter()
        limiter.record_call("creator1", "/conversations", 200)
        limiter.record_call("creator1", "/messages", 200)
        stats = limiter.get_stats("creator1")
        assert stats["creator_id"] == "creator1"
        assert stats["calls_last_minute"] == 2
        assert stats["calls_last_hour"] == 2
        assert stats["remaining_minute"] == 13  # 15 - 2

    def test_global_stats_aggregates_creators(self):
        """Global stats aggregate across all creators."""
        limiter = InstagramRateLimiter()
        limiter.record_call("creator1", "/test", 200)
        limiter.record_call("creator2", "/test", 200)
        stats = limiter.get_stats()
        assert stats["total_creators"] == 2
        assert stats["calls_last_minute"] == 2

    def test_get_call_history(self):
        """get_call_history returns formatted call records."""
        limiter = InstagramRateLimiter()
        limiter.record_call("creator1", "/conversations", 200)
        history = limiter.get_call_history(creator_id="creator1", hours=1)
        assert len(history) == 1
        assert history[0]["endpoint"] == "/conversations"
        assert history[0]["response_code"] == 200

    def test_get_instagram_rate_limiter_singleton(self):
        """get_instagram_rate_limiter returns same instance."""
        import core.instagram_rate_limiter as mod

        mod._instagram_rate_limiter = None
        r1 = get_instagram_rate_limiter()
        r2 = get_instagram_rate_limiter()
        assert r1 is r2
        mod._instagram_rate_limiter = None  # Cleanup
