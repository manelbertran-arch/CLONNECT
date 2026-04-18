"""Tests for DNA auto-update triggers.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.

Triggers determine WHEN to re-analyze DNA based on:
- New message count thresholds
- Time since last analysis
- Conversation phase changes
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch



class TestDNAUpdateTriggers:
    """Test suite for DNA auto-update triggers."""

    def test_trigger_on_new_messages(self):
        """Should trigger update when new message count exceeds threshold."""
        from services.dna_update_triggers import DNAUpdateTriggers

        triggers = DNAUpdateTriggers()

        # DNA analyzed 25 hours ago (past cooldown period)
        existing_dna = {
            "total_messages_analyzed": 10,
            "last_analyzed_at": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
        }

        # 5 new messages - should NOT trigger (below threshold)
        assert triggers.should_update(existing_dna, current_count=15) is False

        # 15 new messages - should trigger (above threshold of 10)
        assert triggers.should_update(existing_dna, current_count=25) is True

    def test_trigger_on_threshold(self):
        """Should trigger at specific message count milestones."""
        from services.dna_update_triggers import DNAUpdateTriggers

        triggers = DNAUpdateTriggers()

        # First analysis at 5 messages
        no_dna = None
        assert triggers.should_update(no_dna, current_count=5) is True
        assert triggers.should_update(no_dna, current_count=3) is False

        # Subsequent updates at milestones (past cooldown)
        dna_at_5 = {
            "total_messages_analyzed": 5,
            "last_analyzed_at": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        }
        assert triggers.should_update(dna_at_5, current_count=10) is False  # Not enough new
        assert triggers.should_update(dna_at_5, current_count=20) is True   # 15 new messages

    def test_cooldown_respected(self):
        """Should respect cooldown period between updates."""
        from services.dna_update_triggers import DNAUpdateTriggers

        triggers = DNAUpdateTriggers()

        # Recently analyzed (1 hour ago)
        recent_dna = {
            "total_messages_analyzed": 50,
            "last_analyzed_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }

        # Even with many new messages, should NOT trigger during cooldown
        assert triggers.should_update(recent_dna, current_count=100) is False

        # After cooldown (25 hours ago)
        old_dna = {
            "total_messages_analyzed": 50,
            "last_analyzed_at": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
        }

        # Should trigger after cooldown with enough new messages
        assert triggers.should_update(old_dna, current_count=65) is True

    def test_async_update(self):
        """Should schedule async update without blocking."""
        from services.dna_update_triggers import DNAUpdateTriggers

        triggers = DNAUpdateTriggers()

        with patch("services.dna_update_triggers.schedule_dna_update") as mock_schedule:
            mock_schedule.return_value = True

            # Schedule async update
            result = triggers.schedule_async_update("stefan", "lead123", [])

            assert result is True
            mock_schedule.assert_called_once()


class TestInflightDedup:
    """W8-T1-BUG3: dedup by (creator_id, follower_id)."""

    def setup_method(self):
        from services.dna_update_triggers import _inflight, _inflight_lock
        with _inflight_lock:
            _inflight.clear()

    def test_register_returns_true_first_time(self):
        from services.dna_update_triggers import (
            try_register_inflight, release_inflight,
        )
        assert try_register_inflight("c1", "f1") is True
        release_inflight("c1", "f1")

    def test_register_returns_false_if_already_inflight(self):
        from services.dna_update_triggers import (
            try_register_inflight, release_inflight,
        )
        assert try_register_inflight("c1", "f1") is True
        assert try_register_inflight("c1", "f1") is False
        release_inflight("c1", "f1")
        assert try_register_inflight("c1", "f1") is True
        release_inflight("c1", "f1")

    def test_different_pairs_independent(self):
        from services.dna_update_triggers import (
            try_register_inflight, release_inflight,
        )
        assert try_register_inflight("c1", "f1") is True
        assert try_register_inflight("c1", "f2") is True
        assert try_register_inflight("c2", "f1") is True
        release_inflight("c1", "f1")
        release_inflight("c1", "f2")
        release_inflight("c2", "f1")

    def test_schedule_dna_update_skips_double(self):
        """Second schedule_dna_update for same pair returns False without scheduling."""
        from services.dna_update_triggers import (
            schedule_dna_update, try_register_inflight,
        )
        # Pre-register to simulate a concurrent analysis already in-flight.
        assert try_register_inflight("c1", "f1") is True
        try:
            with patch("threading.Thread") as mock_thread:
                result = schedule_dna_update("c1", "f1", [])
                assert result is False
                mock_thread.assert_not_called()
        finally:
            from services.dna_update_triggers import release_inflight
            release_inflight("c1", "f1")

    def test_release_is_idempotent(self):
        from services.dna_update_triggers import release_inflight
        release_inflight("never-registered", "x")  # No error
