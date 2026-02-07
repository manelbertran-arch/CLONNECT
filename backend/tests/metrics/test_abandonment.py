from datetime import datetime, timedelta, timezone

import pytest
from metrics.collectors.abandonment import AbandonmentCollector


class TestAbandonment:
    @pytest.fixture
    def collector(self):
        return AbandonmentCollector(creator_id="test")

    def test_short_conversation_bot_last(self, collector):
        messages = [
            {"role": "lead", "created_at": datetime.now(timezone.utc) - timedelta(hours=2)},
            {"role": "assistant", "created_at": datetime.now(timezone.utc) - timedelta(hours=2)},
        ]

        is_abandoned, reason = collector._check_abandonment(messages)
        assert is_abandoned is True
        assert reason == "user_no_response_short"

    def test_short_conversation_user_last(self, collector):
        messages = [
            {"role": "lead", "created_at": datetime.now(timezone.utc) - timedelta(minutes=5)},
            {"role": "assistant", "created_at": datetime.now(timezone.utc) - timedelta(minutes=4)},
            {"role": "lead", "created_at": datetime.now(timezone.utc) - timedelta(minutes=3)},
        ]

        is_abandoned, reason = collector._check_abandonment(messages)
        assert is_abandoned is False
        assert reason == "too_few_messages"

    def test_timeout_abandonment(self, collector):
        now = datetime.now(timezone.utc)
        messages = [
            {"role": "lead", "created_at": now - timedelta(hours=2)},
            {"role": "assistant", "created_at": now - timedelta(hours=2)},
            {"role": "lead", "created_at": now - timedelta(hours=2)},
            {"role": "assistant", "created_at": now - timedelta(hours=1)},
        ]

        is_abandoned, reason = collector._check_abandonment(messages)
        assert is_abandoned is True
        assert reason == "user_no_response_timeout"

    def test_active_conversation(self, collector):
        now = datetime.now(timezone.utc)
        messages = [
            {"role": "lead", "created_at": now - timedelta(minutes=10)},
            {"role": "assistant", "created_at": now - timedelta(minutes=9)},
            {"role": "lead", "created_at": now - timedelta(minutes=8)},
            {"role": "assistant", "created_at": now - timedelta(minutes=2)},
        ]

        is_abandoned, reason = collector._check_abandonment(messages)
        assert is_abandoned is False
        assert reason == "active"

    def test_configurable_threshold(self, collector):
        assert collector.abandonment_threshold_minutes == 30
        assert collector.min_messages_for_completion == 4
