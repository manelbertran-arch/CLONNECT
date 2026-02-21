"""Audit tests for core/notifications.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.notifications import (
    EscalationNotification,
    NotificationService,
    NotificationType,
    get_notification_service,
)


def _make_notification(**overrides) -> EscalationNotification:
    """Factory for EscalationNotification with sensible defaults."""
    defaults = {
        "creator_id": "creator1",
        "follower_id": "follower1",
        "follower_username": "testuser",
        "follower_name": "Test User",
        "reason": "User asked for human",
        "last_message": "I want to speak to a person",
        "conversation_summary": "User inquired about pricing",
        "purchase_intent_score": 0.85,
        "total_messages": 10,
        "products_discussed": ["course_a"],
    }
    defaults.update(overrides)
    return EscalationNotification(**defaults)


class TestNotificationServiceInit:
    """Test 1: Initialization and imports."""

    def test_service_init_defaults(self):
        """NotificationService initializes with env-based defaults."""
        with patch.dict("os.environ", {}, clear=True):
            service = NotificationService()
            assert service.webhook_url == ""
            assert service.telegram_bot_token == ""
            assert service.telegram_chat_id == ""
            assert service.smtp_enabled is False
            assert service._cooldown_seconds == 300
            assert service._sent_notifications == {}

    def test_service_reads_env_vars(self):
        """NotificationService reads config from environment."""
        with patch.dict(
            "os.environ",
            {
                "ESCALATION_WEBHOOK_URL": "https://hooks.slack.com/test",
                "TELEGRAM_BOT_TOKEN": "bot_token_123",
                "TELEGRAM_CHAT_ID": "chat_123",
                "SMTP_ENABLED": "true",
            },
        ):
            service = NotificationService()
            assert service.webhook_url == "https://hooks.slack.com/test"
            assert service.telegram_bot_token == "bot_token_123"
            assert service.telegram_chat_id == "chat_123"
            assert service.smtp_enabled is True

    def test_notification_type_enum_values(self):
        """NotificationType enum has all expected types."""
        expected = {"escalation", "hot_lead", "new_lead", "support", "daily_summary"}
        actual = {nt.value for nt in NotificationType}
        assert actual == expected

    def test_get_notification_service_returns_instance(self):
        """get_notification_service returns a NotificationService."""
        import core.notifications as mod

        original = mod._notification_service
        mod._notification_service = None
        try:
            service = get_notification_service()
            assert isinstance(service, NotificationService)
        finally:
            mod._notification_service = original

    def test_escalation_notification_post_init_defaults(self):
        """EscalationNotification.__post_init__ fills timestamp and sanitizes None."""
        notif = EscalationNotification(
            creator_id="c1",
            follower_id="f1",
            follower_username="user1",
            follower_name="Name",
            reason="test",
            last_message="msg",
            conversation_summary="summary",
            purchase_intent_score=None,
            total_messages=None,
            products_discussed=None,
        )
        assert notif.timestamp is not None
        assert notif.purchase_intent_score == 0.0
        assert notif.total_messages == 0
        assert notif.products_discussed == []


class TestNotificationCreation:
    """Test 2: Happy path - notification creation and formatting."""

    def test_to_dict_returns_all_fields(self):
        """to_dict serializes all fields."""
        notif = _make_notification()
        d = notif.to_dict()
        assert d["creator_id"] == "creator1"
        assert d["follower_username"] == "testuser"
        assert d["purchase_intent_score"] == 0.85
        assert isinstance(d["products_discussed"], list)

    def test_to_slack_message_has_blocks(self):
        """to_slack_message returns dict with text and blocks."""
        notif = _make_notification()
        slack = notif.to_slack_message()
        assert "text" in slack
        assert "blocks" in slack
        assert len(slack["blocks"]) > 0
        assert "testuser" in slack["text"]

    def test_to_email_html_contains_username(self):
        """to_email_html returns HTML containing the follower username."""
        notif = _make_notification()
        html = notif.to_email_html()
        assert "@testuser" in html
        assert "Escalaci" in html  # "Escalacion" in Spanish

    def test_to_telegram_message_contains_intent(self):
        """to_telegram_message includes purchase intent percentage."""
        notif = _make_notification(purchase_intent_score=0.85)
        msg = notif.to_telegram_message()
        assert "85%" in msg
        assert "@testuser" in msg

    def test_log_notification_writes_file(self, tmp_path):
        """_log_notification writes to JSONL file."""
        with patch.dict("os.environ", {}, clear=True):
            service = NotificationService()
            notif = _make_notification()

            # Patch the log directory to temp
            with patch("core.notifications.os.makedirs"):
                with patch("builtins.open", MagicMock()):
                    result = service._log_notification(notif)
            assert result is True


class TestEmptyRecipientHandling:
    """Test 3: Edge case - empty recipient and missing config."""

    @pytest.mark.asyncio
    async def test_send_webhook_returns_false_when_no_url(self):
        """_send_webhook returns False when webhook_url is empty."""
        with patch.dict("os.environ", {}, clear=True):
            service = NotificationService()
            notif = _make_notification()
            result = await service._send_webhook(notif)
            assert result is False

    @pytest.mark.asyncio
    async def test_send_telegram_returns_false_when_no_token(self):
        """_send_telegram returns False when bot token is missing."""
        with patch.dict("os.environ", {}, clear=True):
            service = NotificationService()
            notif = _make_notification()
            result = await service._send_telegram(notif)
            assert result is False

    @pytest.mark.asyncio
    async def test_send_email_returns_false_when_no_api_key(self):
        """_send_email returns False when RESEND_API_KEY is missing."""
        with patch.dict("os.environ", {"RESEND_API_KEY": "", "CREATOR_EMAIL": ""}, clear=True):
            service = NotificationService()
            notif = _make_notification()
            result = await service._send_email(notif)
            assert result is False

    @pytest.mark.asyncio
    async def test_notify_escalation_cooldown_skips(self):
        """notify_escalation skips if same follower notified within cooldown."""
        with patch.dict("os.environ", {}, clear=True):
            service = NotificationService()
            notif = _make_notification()

            # Simulate a recent notification (must be timezone-aware to match source)
            cooldown_key = f"{notif.creator_id}:{notif.follower_id}"
            service._sent_notifications[cooldown_key] = datetime.now(tz=timezone.utc)

            result = await service.notify_escalation(notif)
            assert result.get("skipped") is True
            assert result.get("reason") == "cooldown"

    @pytest.mark.asyncio
    async def test_notify_escalation_no_cooldown_after_expiry(self):
        """notify_escalation sends after cooldown period expires."""
        with patch.dict("os.environ", {}, clear=True):
            service = NotificationService()
            notif = _make_notification()

            # Simulate an old notification beyond cooldown (must be timezone-aware to match source)
            cooldown_key = f"{notif.creator_id}:{notif.follower_id}"
            service._sent_notifications[cooldown_key] = datetime.now(tz=timezone.utc) - timedelta(seconds=600)

            # Will only use "log" channel since no external services configured
            with patch.object(service, "_log_notification", return_value=True):
                result = await service.notify_escalation(notif, channels=["log"])
            assert result.get("log") is True


class TestTypeValidation:
    """Test 4: Error handling - notification type and data validation."""

    def test_high_intent_emoji_in_slack(self):
        """High purchase intent (>0.7) gets fire emoji in Slack."""
        notif = _make_notification(purchase_intent_score=0.85)
        slack = notif.to_slack_message()
        # The fire emoji is part of the text
        assert "\U0001f525" in slack["text"]  # fire emoji

    def test_medium_intent_emoji_in_slack(self):
        """Medium purchase intent (0.4-0.7) gets lightning emoji in Slack."""
        notif = _make_notification(purchase_intent_score=0.55)
        slack = notif.to_slack_message()
        assert "\u26a1" in slack["text"]  # lightning emoji

    def test_low_intent_emoji_in_slack(self):
        """Low purchase intent (<0.4) gets mail emoji in Slack."""
        notif = _make_notification(purchase_intent_score=0.2)
        slack = notif.to_slack_message()
        assert "\U0001f4e9" in slack["text"]  # mail emoji

    def test_email_color_varies_by_intent(self):
        """Email HTML color varies based on purchase intent score."""
        high = _make_notification(purchase_intent_score=0.85)
        mid = _make_notification(purchase_intent_score=0.55)
        low = _make_notification(purchase_intent_score=0.2)

        assert "#e74c3c" in high.to_email_html()  # red for high
        assert "#f39c12" in mid.to_email_html()  # orange for medium
        assert "#3498db" in low.to_email_html()  # blue for low

    def test_products_discussed_empty_shows_ninguno(self):
        """Empty products list shows 'Ninguno' in formatted messages."""
        notif = _make_notification(products_discussed=[])
        slack = notif.to_slack_message()
        telegram = notif.to_telegram_message()
        # Check that at least one format shows Ninguno
        found = False
        for block in slack.get("blocks", []):
            text = block.get("text", {})
            if isinstance(text, dict) and "Ninguno" in text.get("text", ""):
                found = True
                break
        assert found or "Ninguno" in telegram


class TestBatchNotification:
    """Test 5: Integration check - batch and multi-channel notifications."""

    @pytest.mark.asyncio
    async def test_notify_hot_lead(self):
        """notify_hot_lead creates notification and passes to notify_escalation."""
        with patch.dict("os.environ", {}, clear=True):
            service = NotificationService()

            with patch.object(
                service, "notify_escalation", new_callable=AsyncMock, return_value={"log": True}
            ) as mock_notify:
                _result = await service.notify_hot_lead(  # noqa: F841
                    creator_id="creator1",
                    follower_id="follower1",
                    follower_username="hotuser",
                    purchase_intent_score=0.9,
                    products_discussed=["product_a"],
                )
                assert mock_notify.called
                call_notif = mock_notify.call_args[0][0]
                assert call_notif.notification_type == "hot_lead"
                assert call_notif.purchase_intent_score == 0.9

    @pytest.mark.asyncio
    async def test_notify_escalation_uses_all_configured_channels(self):
        """When channels=None, service auto-detects configured channels."""
        with patch.dict(
            "os.environ",
            {
                "ESCALATION_WEBHOOK_URL": "https://hooks.example.com",
                "TELEGRAM_BOT_TOKEN": "bot_tok",
                "TELEGRAM_CHAT_ID": "chat_id",
            },
        ):
            service = NotificationService()
            notif = _make_notification()

            with patch.object(
                service, "_send_webhook", new_callable=AsyncMock, return_value=True
            ) as mock_wh:
                with patch.object(
                    service, "_send_telegram", new_callable=AsyncMock, return_value=True
                ) as mock_tg:
                    with patch.object(service, "_log_notification", return_value=True) as mock_log:
                        result = await service.notify_escalation(notif)

            assert mock_wh.called
            assert mock_tg.called
            assert mock_log.called
            assert result["webhook"] is True
            assert result["telegram"] is True
            assert result["log"] is True

    @pytest.mark.asyncio
    async def test_notify_escalation_handles_channel_exception(self):
        """If one channel raises, others still execute."""
        with patch.dict("os.environ", {}, clear=True):
            service = NotificationService()
            notif = _make_notification()

            with patch.object(service, "_log_notification", side_effect=RuntimeError("disk full")):
                result = await service.notify_escalation(notif, channels=["log"])
            assert result["log"] is False

    @pytest.mark.asyncio
    async def test_send_weekly_summary_no_api_key(self):
        """send_weekly_summary returns False without RESEND_API_KEY."""
        with patch.dict("os.environ", {"RESEND_API_KEY": ""}, clear=True):
            service = NotificationService()
            result = await service.send_weekly_summary(
                "creator1", "test@example.com", {"total_messages": 100}
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_multiple_escalations_different_followers(self):
        """Different followers can be notified within same cooldown window."""
        with patch.dict("os.environ", {}, clear=True):
            service = NotificationService()

            n1 = _make_notification(follower_id="f1")
            n2 = _make_notification(follower_id="f2")

            with patch.object(service, "_log_notification", return_value=True):
                r1 = await service.notify_escalation(n1, channels=["log"])
                r2 = await service.notify_escalation(n2, channels=["log"])

            assert r1.get("log") is True
            assert r2.get("log") is True
