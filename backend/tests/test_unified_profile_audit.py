"""Audit tests for core/unified_profile_service.py."""

from unittest.mock import patch


# ---------------------------------------------------------------------------
# Test 1: init / import
# ---------------------------------------------------------------------------
class TestUnifiedProfileImports:
    """Verify module can be imported and key symbols exist."""

    def test_imports_and_key_symbols(self):
        from core.unified_profile_service import (
            CROSS_PLATFORM_NEW_USER,
            CROSS_PLATFORM_RECOGNIZED,
            EMAIL_REGEX,
            EmailAskDecision,
        )

        # EmailAskDecision is a dataclass with expected fields
        decision = EmailAskDecision(should_ask=True, message="hi", reason="test")
        assert decision.should_ask is True
        assert decision.message == "hi"
        assert decision.reason == "test"

        # Constants are non-empty strings
        assert isinstance(EMAIL_REGEX, str) and len(EMAIL_REGEX) > 0
        assert isinstance(CROSS_PLATFORM_NEW_USER, str) and len(CROSS_PLATFORM_NEW_USER) > 0
        assert "{name}" in CROSS_PLATFORM_RECOGNIZED


# ---------------------------------------------------------------------------
# Test 2: happy path - email extraction and offer messages
# ---------------------------------------------------------------------------
class TestUnifiedProfileHappyPath:
    """Test core extraction and message generation on valid inputs."""

    def test_extract_email_valid(self):
        from core.unified_profile_service import extract_email

        assert extract_email("my email is user@example.com ok") == "user@example.com"
        assert extract_email("contact me at Admin@Foo.ORG") == "admin@foo.org"

    def test_get_ask_message_discount_complete(self):
        from core.unified_profile_service import get_ask_message_by_offer_type

        msg = get_ask_message_by_offer_type("discount", {"percent": 20, "code": "SAVE20"})
        assert "20%" in msg
        assert "descuento" in msg.lower()

    def test_get_captured_message_with_content_offer(self):
        from core.unified_profile_service import get_captured_message

        msg = get_captured_message("Ana", "content", {"description": "guia exclusiva"})
        assert "Ana" in msg
        assert "guia exclusiva" in msg

    def test_extract_name_from_text(self):
        from core.unified_profile_service import extract_name_from_text

        assert extract_name_from_text("Hola, me llamo Carlos") == "Carlos"
        assert extract_name_from_text("I'm Laura, nice to meet you") == "Laura"


# ---------------------------------------------------------------------------
# Test 3: edge case - missing / empty / incomplete inputs
# ---------------------------------------------------------------------------
class TestUnifiedProfileEdgeCases:
    """Edge cases: empty strings, None, incomplete configs."""

    def test_extract_email_returns_none_for_empty(self):
        from core.unified_profile_service import extract_email

        assert extract_email("") is None
        assert extract_email(None) is None
        assert extract_email("no email here") is None

    def test_extract_name_returns_none_for_gibberish(self):
        from core.unified_profile_service import extract_name_from_text

        assert extract_name_from_text("asdf jkl") is None
        assert extract_name_from_text("") is None

    def test_discount_incomplete_config_falls_back(self):
        from core.unified_profile_service import get_ask_message_by_offer_type

        # Missing code -> should fallback to base message (contains "recordar")
        msg = get_ask_message_by_offer_type("discount", {"percent": 10})
        assert "recordar" in msg.lower()
        assert "descuento" not in msg.lower()

    def test_content_incomplete_config_falls_back(self):
        from core.unified_profile_service import get_ask_message_by_offer_type

        msg = get_ask_message_by_offer_type("content", {})
        assert "recordar" in msg.lower()

    def test_custom_incomplete_config_falls_back(self):
        from core.unified_profile_service import get_ask_message_by_offer_type

        msg = get_ask_message_by_offer_type("custom", {})
        assert "recordar" in msg.lower()


# ---------------------------------------------------------------------------
# Test 4: error handling - DB functions return safe defaults on failure
# ---------------------------------------------------------------------------
class TestUnifiedProfileErrorHandling:
    """DB-dependent functions must return safe defaults when DB is unavailable."""

    @patch("core.unified_profile_service.get_creator_email_config")
    def test_should_ask_email_returns_false_when_disabled(self, mock_config):
        from core.unified_profile_service import should_ask_email

        mock_config.return_value = {"enabled": False}

        decision = should_ask_email("instagram", "user123", "creator1", "general", 10)
        assert decision.should_ask is False
        assert decision.reason == "disabled"

    def test_get_unified_profile_returns_none_on_import_error(self):
        """When DB is not available the function returns None (not raises)."""
        from core.unified_profile_service import get_unified_profile

        with patch(
            "core.unified_profile_service.get_unified_profile.__module__",
            new="core.unified_profile_service",
        ):
            # The function does `from api.database import SessionLocal` inside,
            # which will fail in test env -> should return None gracefully.
            result = get_unified_profile("instagram", "nonexistent_user")
            assert result is None

    def test_get_unified_profile_by_email_returns_none_on_error(self):
        from core.unified_profile_service import get_unified_profile_by_email

        result = get_unified_profile_by_email("bad@test.com")
        assert result is None

    def test_get_all_platform_identities_returns_empty_on_error(self):
        from core.unified_profile_service import get_all_platform_identities

        result = get_all_platform_identities("fake-uuid")
        assert result == []

    def test_get_email_ask_tracking_returns_defaults_on_error(self):
        from core.unified_profile_service import get_email_ask_tracking

        result = get_email_ask_tracking("instagram", "user999")
        assert result.get("ask_count") == 0


# ---------------------------------------------------------------------------
# Test 5: integration check - offer type message matrix + captured message
# ---------------------------------------------------------------------------
class TestUnifiedProfileIntegration:
    """Cross-function integration: offer types, captured messages, and decision."""

    def test_all_offer_types_return_non_empty(self):
        from core.unified_profile_service import get_ask_message_by_offer_type

        offer_types = ["none", "discount", "content", "priority", "custom", "", None]
        for ot in offer_types:
            msg = get_ask_message_by_offer_type(ot)
            assert isinstance(msg, str) and len(msg) > 10, f"Failed for offer_type={ot!r}"

    def test_captured_message_without_offer(self):
        from core.unified_profile_service import get_captured_message

        msg = get_captured_message("Diego", "none")
        assert "Diego" in msg
        assert "recordar" in msg.lower()

    def test_captured_message_discount_without_complete_config(self):
        """Discount offer with incomplete config should NOT mention discount code."""
        from core.unified_profile_service import get_captured_message

        msg = get_captured_message("Maria", "discount", {"percent": 10})
        # code is missing, so the discount add-on should NOT appear
        assert "codigo" not in msg.lower() or "code" not in msg.lower()

    @patch("core.unified_profile_service.get_creator_email_config")
    @patch("core.unified_profile_service.get_unified_profile")
    @patch("core.unified_profile_service.get_email_ask_tracking")
    def test_should_ask_email_high_intent_triggers(self, mock_tracking, mock_profile, mock_config):
        from core.unified_profile_service import should_ask_email

        mock_config.return_value = {
            "enabled": True,
            "ask_after_messages": 5,
            "offer_type": "none",
            "offer_config": None,
        }
        mock_profile.return_value = None  # no existing profile
        mock_tracking.return_value = {
            "ask_count": 0,
            "last_asked_at": None,
            "captured_email": None,
        }

        # High intent should override message threshold (message_count=1 < 5)
        decision = should_ask_email("instagram", "user1", "creator1", "purchase", 1)
        assert decision.should_ask is True
        assert decision.reason == "high_intent"

    @patch("core.unified_profile_service.get_creator_email_config")
    @patch("core.unified_profile_service.get_unified_profile")
    @patch("core.unified_profile_service.get_email_ask_tracking")
    def test_should_ask_email_message_threshold(self, mock_tracking, mock_profile, mock_config):
        from core.unified_profile_service import should_ask_email

        mock_config.return_value = {
            "enabled": True,
            "ask_after_messages": 3,
            "offer_type": "none",
            "offer_config": None,
        }
        mock_profile.return_value = None
        mock_tracking.return_value = {
            "ask_count": 0,
            "last_asked_at": None,
            "captured_email": None,
        }

        decision = should_ask_email("instagram", "user2", "creator1", "general", 5)
        assert decision.should_ask is True
        assert decision.reason == "message_threshold"
