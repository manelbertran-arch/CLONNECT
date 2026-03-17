"""
Tests for core/user_context_loader.py

Tests the User Context Loader module that provides unified user data loading
for LLM personalization.
"""

from unittest.mock import MagicMock

import pytest


class TestConversationMessage:
    """Tests for ConversationMessage dataclass."""

    def test_conversation_message_defaults(self):
        from core.user_context_loader import ConversationMessage

        msg = ConversationMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp == ""

    def test_conversation_message_to_dict(self):
        from core.user_context_loader import ConversationMessage

        msg = ConversationMessage(role="assistant", content="Hi there!", timestamp="2024-01-01T00:00:00")
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Hi there!"
        assert d["timestamp"] == "2024-01-01T00:00:00"

    def test_conversation_message_from_dict(self):
        from core.user_context_loader import ConversationMessage

        data = {"role": "user", "content": "Test message", "timestamp": "2024-01-01"}
        msg = ConversationMessage.from_dict(data)
        assert msg.role == "user"
        assert msg.content == "Test message"


class TestLeadInfo:
    """Tests for LeadInfo dataclass."""

    def test_lead_info_defaults(self):
        from core.user_context_loader import LeadInfo

        lead = LeadInfo()
        assert lead.status == "nuevo"
        assert lead.score == 0
        assert lead.tags == []

    def test_lead_info_from_db_row(self):
        from core.user_context_loader import LeadInfo

        mock_row = MagicMock()
        mock_row.id = "uuid-123"
        mock_row.status = "caliente"
        mock_row.score = 85
        mock_row.purchase_intent = 0.75
        mock_row.deal_value = 500.0
        mock_row.tags = ["vip", "interested"]
        mock_row.source = "instagram_dm"
        mock_row.notes = "Hot lead"
        mock_row.email = "test@example.com"
        mock_row.phone = "+34666123456"

        lead = LeadInfo.from_db_row(mock_row)
        assert lead.id == "uuid-123"
        assert lead.status == "caliente"
        assert lead.score == 85
        assert lead.purchase_intent == 0.75
        assert lead.deal_value == 500.0
        assert "vip" in lead.tags


class TestUserPreferences:
    """Tests for UserPreferences dataclass."""

    def test_user_preferences_defaults(self):
        from core.user_context_loader import UserPreferences

        prefs = UserPreferences()
        assert prefs.language == "es"
        assert prefs.response_style == "balanced"
        assert prefs.communication_tone == "friendly"


class TestUserContext:
    """Tests for UserContext dataclass."""

    def test_user_context_defaults(self):
        from core.user_context_loader import UserContext

        ctx = UserContext(follower_id="test_123", creator_id="creator_1")
        assert ctx.follower_id == "test_123"
        assert ctx.creator_id == "creator_1"
        assert ctx.is_first_message is True
        assert ctx.is_returning_user is False
        assert ctx.interests == []

    def test_get_display_name_with_name(self):
        from core.user_context_loader import UserContext

        ctx = UserContext(follower_id="test", creator_id="c1", name="John")
        assert ctx.get_display_name() == "John"

    def test_get_display_name_with_username(self):
        from core.user_context_loader import UserContext

        ctx = UserContext(follower_id="test", creator_id="c1", username="@john_doe")
        assert ctx.get_display_name() == "@john_doe"

    def test_get_display_name_fallback(self):
        from core.user_context_loader import UserContext

        ctx = UserContext(follower_id="test", creator_id="c1")
        assert ctx.get_display_name() == "amigo"

    def test_get_conversation_length(self):
        from core.user_context_loader import UserContext

        ctx = UserContext(follower_id="test", creator_id="c1")
        assert ctx.get_conversation_length() == "new"

        ctx.total_messages = 2
        assert ctx.get_conversation_length() == "short"

        ctx.total_messages = 5
        assert ctx.get_conversation_length() == "medium"

        ctx.total_messages = 15
        assert ctx.get_conversation_length() == "long"

    def test_get_engagement_level(self):
        from core.user_context_loader import UserContext

        ctx = UserContext(follower_id="test", creator_id="c1")
        ctx.engagement_score = 0.1
        assert ctx.get_engagement_level() == "low"

        ctx.engagement_score = 0.5
        assert ctx.get_engagement_level() == "medium"

        ctx.engagement_score = 0.8
        assert ctx.get_engagement_level() == "high"

    def test_get_purchase_intent_level(self):
        from core.user_context_loader import UserContext

        ctx = UserContext(follower_id="test", creator_id="c1")
        ctx.purchase_intent_score = 0.2
        assert ctx.get_purchase_intent_level() == "low"

        ctx.purchase_intent_score = 0.5
        assert ctx.get_purchase_intent_level() == "medium"

        ctx.purchase_intent_score = 0.8
        assert ctx.get_purchase_intent_level() == "high"

    def test_has_tag(self):
        from core.user_context_loader import LeadInfo, UserContext

        ctx = UserContext(follower_id="test", creator_id="c1")
        ctx.lead_info = LeadInfo(tags=["vip", "interested"])
        assert ctx.has_tag("vip") is True
        assert ctx.has_tag("VIP") is True  # Case insensitive
        assert ctx.has_tag("random") is False

    def test_is_vip(self):
        from core.user_context_loader import LeadInfo, UserContext

        ctx = UserContext(follower_id="test", creator_id="c1")
        assert ctx.is_vip() is False

        ctx.lead_info = LeadInfo(tags=["vip"])
        assert ctx.is_vip() is True

        ctx2 = UserContext(follower_id="test", creator_id="c1", is_customer=True)
        assert ctx2.is_vip() is True

    def test_is_price_sensitive(self):
        from core.user_context_loader import LeadInfo, UserContext

        ctx = UserContext(follower_id="test", creator_id="c1")
        assert ctx.is_price_sensitive() is False

        ctx.lead_info = LeadInfo(tags=["price_sensitive"])
        assert ctx.is_price_sensitive() is True

        ctx2 = UserContext(
            follower_id="test", creator_id="c1", objections_raised=["precio", "tiempo"]
        )
        assert ctx2.is_price_sensitive() is True

    def test_get_recent_messages(self):
        from core.user_context_loader import ConversationMessage, UserContext

        ctx = UserContext(follower_id="test", creator_id="c1")
        ctx.last_messages = [
            ConversationMessage(role="user", content=f"Message {i}") for i in range(10)
        ]

        recent = ctx.get_recent_messages(3)
        assert len(recent) == 3
        assert recent[0].content == "Message 7"
        assert recent[2].content == "Message 9"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_parse_datetime_valid(self):
        from core.user_context_loader import _parse_datetime

        dt = _parse_datetime("2024-01-15T10:30:00+00:00")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_parse_datetime_invalid(self):
        from core.user_context_loader import _parse_datetime

        assert _parse_datetime("") is None
        assert _parse_datetime("invalid") is None
        assert _parse_datetime(None) is None

    def test_calculate_days_since(self):
        from datetime import datetime, timedelta, timezone

        from core.user_context_loader import _calculate_days_since

        # Recent date
        recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        assert _calculate_days_since(recent) == 3

        # Empty string
        assert _calculate_days_since("") == 0


class TestLoadUserContext:
    """Tests for load_user_context function."""

    def test_load_returns_user_context_type(self):
        from core.user_context_loader import UserContext, load_user_context

        ctx = load_user_context("test_creator", "test_follower")
        assert isinstance(ctx, UserContext)
        assert ctx.creator_id == "test_creator"
        assert ctx.follower_id == "test_follower"

    def test_load_with_username_and_name(self):
        from core.user_context_loader import load_user_context

        ctx = load_user_context(
            "test_creator", "test_follower", username="@test_user", name="Test User"
        )
        assert ctx.username == "@test_user"
        assert ctx.name == "Test User"

    def test_is_first_message_flag(self):
        from core.user_context_loader import load_user_context

        ctx = load_user_context("test_creator", "new_user_123")
        # Without any stored data, should be first message
        assert ctx.is_first_message is True


class TestCaching:
    """Tests for caching functionality."""

    def test_cache_invalidation(self):
        from core.user_context_loader import (
            UserContext,
            _user_context_cache,
            clear_all_user_cache,
            invalidate_user_cache,
        )

        # Add to cache manually
        _user_context_cache.set("c1:f1", UserContext(follower_id="f1", creator_id="c1"))

        # Invalidate specific
        invalidate_user_cache("c1", "f1")
        assert "c1:f1" not in _user_context_cache

        # Clear all
        _user_context_cache.set("a:b", UserContext(follower_id="b", creator_id="a"))
        _user_context_cache.set("c:d", UserContext(follower_id="d", creator_id="c"))
        clear_all_user_cache()
        assert len(_user_context_cache) == 0


class TestFormatters:
    """Tests for prompt formatting functions."""

    def test_format_user_context_for_prompt_empty(self):
        from core.user_context_loader import UserContext, format_user_context_for_prompt

        ctx = UserContext(follower_id="test", creator_id="c1")
        # New user with no special context
        text = format_user_context_for_prompt(ctx)
        assert "PRIMER MENSAJE" in text

    def test_format_user_context_for_prompt_with_data(self):
        from core.user_context_loader import (
            LeadInfo,
            UserContext,
            format_user_context_for_prompt,
        )

        ctx = UserContext(
            follower_id="test",
            creator_id="c1",
            name="John",
            top_interests=["fitness", "nutrition"],
            products_discussed=["FitPack"],
            is_lead=True,
            purchase_intent_score=0.8,
            total_messages=5,
            is_first_message=False,
        )
        ctx.lead_info = LeadInfo(tags=["vip"])

        text = format_user_context_for_prompt(ctx)
        assert "John" in text
        assert "fitness" in text
        assert "FitPack" in text
        assert "VIP" in text
        assert "LEAD CALIENTE" in text

    def test_format_conversation_history_for_prompt(self):
        from core.user_context_loader import (
            ConversationMessage,
            UserContext,
            format_conversation_history_for_prompt,
        )

        ctx = UserContext(follower_id="test", creator_id="c1")
        ctx.last_messages = [
            ConversationMessage(role="user", content="Hola!"),
            ConversationMessage(role="assistant", content="Hola, como estas?"),
        ]

        text = format_conversation_history_for_prompt(ctx)
        assert "HISTORIAL RECIENTE" in text
        assert "Usuario: Hola!" in text
        assert "Bot: Hola, como estas?" in text

    def test_format_conversation_history_empty(self):
        from core.user_context_loader import UserContext, format_conversation_history_for_prompt

        ctx = UserContext(follower_id="test", creator_id="c1")
        text = format_conversation_history_for_prompt(ctx)
        assert text == ""

    def test_build_user_context_prompt(self):
        from core.user_context_loader import build_user_context_prompt

        # Should not raise even without data
        text = build_user_context_prompt("test_creator", "test_follower")
        # Should contain first message indicator
        assert "PRIMER MENSAJE" in text or text == ""


class TestIntegration:
    """Integration tests."""

    def test_full_flow_new_user(self):
        """Test complete flow for a new user."""
        from core.user_context_loader import get_user_context

        ctx = get_user_context("integration_test", "new_user_xyz", use_cache=False)

        assert ctx.is_first_message is True
        assert ctx.total_messages == 0
        assert ctx.get_display_name() == "amigo"

    def test_full_flow_with_hints(self):
        """Test complete flow with username/name hints."""
        from core.user_context_loader import get_user_context

        ctx = get_user_context(
            "integration_test",
            "user_with_hints",
            username="@maria",
            name="Maria Garcia",
            use_cache=False,
        )

        assert ctx.get_display_name() == "Maria Garcia"
        assert ctx.username == "@maria"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
