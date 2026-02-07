"""Audit tests for core/alerts.py."""

from unittest.mock import AsyncMock, patch

import pytest
from core.alerts import (
    Alert,
    AlertLevel,
    AlertManager,
    alert_exception,
    alert_llm_error,
    get_alert_manager,
    send_alert,
)

# =========================================================================
# TEST 1: Init / Import
# =========================================================================


class TestAlertSystemInit:
    """Verify module imports and AlertManager initialization."""

    def test_alert_level_enum_values(self):
        """AlertLevel has four levels: info, warning, error, critical."""
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.ERROR.value == "error"
        assert AlertLevel.CRITICAL.value == "critical"

    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    def test_manager_disabled_by_default(self):
        """AlertManager is disabled when env var is 'false'."""
        manager = AlertManager()
        assert manager.enabled is False

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_ALERTS_ENABLED": "true",
            "TELEGRAM_ALERTS_BOT_TOKEN": "test-token",
            "TELEGRAM_ALERTS_CHAT_ID": "12345",
        },
        clear=False,
    )
    def test_manager_enabled_with_config(self):
        """AlertManager is enabled when all env vars are set."""
        manager = AlertManager()
        assert manager.enabled is True
        assert manager.bot_token == "test-token"
        assert manager.chat_id == "12345"

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_ALERTS_ENABLED": "true",
            "TELEGRAM_ALERTS_BOT_TOKEN": "",
            "TELEGRAM_ALERTS_CHAT_ID": "",
        },
        clear=False,
    )
    def test_manager_disabled_when_missing_token(self):
        """AlertManager disables itself if token/chat_id are empty."""
        manager = AlertManager()
        assert manager.enabled is False

    def test_alert_dataclass_auto_timestamp(self):
        """Alert auto-generates timestamp when not provided."""
        alert = Alert(level=AlertLevel.INFO, title="Test", message="msg")
        assert alert.timestamp != ""
        assert "T" in alert.timestamp  # ISO format


# =========================================================================
# TEST 2: Happy Path - Alert Creation
# =========================================================================


class TestAlertCreation:
    """Verify alert creation and formatting."""

    def test_format_message_includes_level_and_title(self):
        """Formatted message contains the level and title."""
        manager = AlertManager()
        alert = Alert(
            level=AlertLevel.ERROR,
            title="DB Down",
            message="Database unreachable",
        )
        formatted = manager._format_message(alert)
        assert "ERROR" in formatted
        assert "DB Down" in formatted
        assert "Database unreachable" in formatted

    def test_format_message_includes_creator_id(self):
        """Formatted message includes creator_id when provided."""
        manager = AlertManager()
        alert = Alert(
            level=AlertLevel.WARNING,
            title="Test",
            message="msg",
            creator_id="manel",
        )
        formatted = manager._format_message(alert)
        assert "manel" in formatted

    def test_format_message_includes_metadata(self):
        """Formatted message includes metadata key-value pairs."""
        manager = AlertManager()
        alert = Alert(
            level=AlertLevel.INFO,
            title="Test",
            message="msg",
            metadata={"provider": "openai"},
        )
        formatted = manager._format_message(alert)
        assert "provider" in formatted
        assert "openai" in formatted

    def test_level_emoji_mapping(self):
        """Each alert level has a corresponding emoji."""
        manager = AlertManager()
        for level in AlertLevel:
            assert level in manager.LEVEL_EMOJI

    def test_alert_with_no_optional_fields(self):
        """Alert works with only required fields."""
        alert = Alert(level=AlertLevel.CRITICAL, title="Panic", message="Help")
        assert alert.creator_id is None
        assert alert.metadata is None


# =========================================================================
# TEST 3: Edge Case - Alert Routing (Rate Limiting / Dedup)
# =========================================================================


class TestAlertRouting:
    """Rate limiting prevents duplicate alerts from being sent."""

    def test_first_alert_allowed(self):
        """The first alert with a given key is allowed."""
        manager = AlertManager()
        assert manager._should_send("error:DB Down") is True

    def test_duplicate_alert_blocked_within_window(self):
        """Identical alert key is blocked within the rate limit window."""
        manager = AlertManager()
        manager._should_send("error:DB Down")  # First call records time
        assert manager._should_send("error:DB Down") is False

    def test_different_alert_key_allowed(self):
        """A different alert key is allowed even after blocking another."""
        manager = AlertManager()
        manager._should_send("error:DB Down")
        assert manager._should_send("warning:Rate Limit") is True

    def test_alert_allowed_after_window(self):
        """Alert is allowed again after the rate limit window expires."""
        manager = AlertManager()
        # Manually set last alert time in the distant past (epoch = very old)
        manager._last_alert_time["error:DB Down"] = 0
        assert manager._should_send("error:DB Down") is True

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    async def test_send_returns_false_when_disabled(self):
        """send_telegram_alert returns False when manager is disabled."""
        manager = AlertManager()
        result = await manager.send_telegram_alert(
            message="test", level=AlertLevel.ERROR, title="Test"
        )
        assert result is False


# =========================================================================
# TEST 4: Error Handling - Missing Recipient
# =========================================================================


class TestAlertErrorHandling:
    """Error scenarios: disabled alerts, network failures."""

    @pytest.mark.asyncio
    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_ALERTS_ENABLED": "true",
            "TELEGRAM_ALERTS_BOT_TOKEN": "fake-token",
            "TELEGRAM_ALERTS_CHAT_ID": "fake-chat",
        },
        clear=False,
    )
    async def test_network_error_returns_false(self):
        """Network error during send returns False, does not raise."""
        manager = AlertManager()
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.post.side_effect = ConnectionError("Network down")
            mock_session_cls.return_value = mock_session
            result = await manager.send_telegram_alert(
                message="test", level=AlertLevel.ERROR, title="Test"
            )
            assert result is False

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    async def test_convenience_methods_work_when_disabled(self):
        """Convenience methods (info, warning, error, critical) don't raise when disabled."""
        manager = AlertManager()
        assert await manager.info("T", "msg") is False
        assert await manager.warning("T", "msg") is False
        assert await manager.error("T", "msg") is False
        assert await manager.critical("T", "msg") is False

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    async def test_alert_llm_error_no_raise(self):
        """alert_llm_error does not raise when alerts are disabled."""
        manager = AlertManager()
        await manager.alert_llm_error("timeout", creator_id="manel", provider="openai")

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    async def test_alert_exception_no_raise(self):
        """alert_exception does not raise when alerts are disabled."""
        manager = AlertManager()
        exc = ValueError("bad value")
        await manager.alert_exception(exc, context="testing", creator_id="manel")

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    async def test_alert_health_check_failed_no_raise(self):
        """alert_health_check_failed does not raise when disabled."""
        manager = AlertManager()
        await manager.alert_health_check_failed("db", "down", details={"latency": 5000})


# =========================================================================
# TEST 5: Integration - Singleton and Convenience Functions
# =========================================================================


class TestAlertIntegration:
    """Integration: singleton pattern and module-level convenience functions."""

    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    def test_get_alert_manager_returns_singleton(self):
        """get_alert_manager returns the same instance on repeated calls."""
        import core.alerts as alerts_mod

        # Reset singleton for clean test
        alerts_mod._alert_manager = None
        m1 = get_alert_manager()
        m2 = get_alert_manager()
        assert m1 is m2
        # Cleanup
        alerts_mod._alert_manager = None

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    async def test_send_alert_convenience_function(self):
        """Module-level send_alert works with string level."""
        import core.alerts as alerts_mod

        alerts_mod._alert_manager = None
        result = await send_alert(message="test", level="error", title="Test")
        assert result is False
        alerts_mod._alert_manager = None

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    async def test_module_alert_llm_error(self):
        """Module-level alert_llm_error delegates to singleton."""
        import core.alerts as alerts_mod

        alerts_mod._alert_manager = None
        await alert_llm_error("timeout", creator_id="manel")
        alerts_mod._alert_manager = None

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    async def test_module_alert_exception(self):
        """Module-level alert_exception delegates to singleton."""
        import core.alerts as alerts_mod

        alerts_mod._alert_manager = None
        await alert_exception(RuntimeError("boom"), context="test")
        alerts_mod._alert_manager = None

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_ALERTS_ENABLED": "false"}, clear=False)
    async def test_alert_rate_limit_method(self):
        """alert_rate_limit method runs without raising."""
        manager = AlertManager()
        await manager.alert_rate_limit(
            creator_id="manel", follower_id="follower_123", reason="too many messages"
        )
