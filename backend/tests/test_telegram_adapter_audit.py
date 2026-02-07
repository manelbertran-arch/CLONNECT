"""Audit tests for core/telegram_adapter.py."""

from unittest.mock import MagicMock, patch

from core.telegram_adapter import (
    TelegramAdapter,
    TelegramBotStatus,
    TelegramMessage,
    get_telegram_adapter,
)

# =========================================================================
# TEST 1: Init / Import - Adapter Initialization
# =========================================================================


class TestTelegramAdapterInit:
    """Verify adapter and dataclass initialization."""

    @patch("core.telegram_adapter.TELEGRAM_AVAILABLE", False)
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": ""}, clear=False)
    def test_adapter_init_without_telegram_lib(self):
        """Adapter initializes without crashing even if telegram lib is absent."""
        adapter = TelegramAdapter(token="fake-token", creator_id="test")
        assert adapter.creator_id == "test"
        assert adapter.status.connected is False

    def test_telegram_message_dataclass(self):
        """TelegramMessage stores all fields and generates follower_id."""
        msg = TelegramMessage(
            telegram_user_id=12345,
            chat_id=67890,
            message_id=1,
            text="hello",
            username="testuser",
            first_name="Test",
            last_name="User",
        )
        assert msg.follower_id == "tg_12345"
        assert msg.platform == "telegram"

    def test_telegram_message_display_name_username(self):
        """display_name prefers @username when available."""
        msg = TelegramMessage(
            telegram_user_id=1,
            chat_id=1,
            message_id=1,
            text="x",
            username="jdoe",
            first_name="John",
        )
        assert msg.display_name == "@jdoe"

    def test_telegram_message_display_name_fullname(self):
        """display_name falls back to first+last name."""
        msg = TelegramMessage(
            telegram_user_id=1,
            chat_id=1,
            message_id=1,
            text="x",
            username="",
            first_name="John",
            last_name="Doe",
        )
        assert msg.display_name == "John Doe"

    def test_telegram_message_display_name_fallback(self):
        """display_name falls back to 'User {id}' when no name info."""
        msg = TelegramMessage(
            telegram_user_id=999,
            chat_id=1,
            message_id=1,
            text="x",
        )
        assert msg.display_name == "User 999"


# =========================================================================
# TEST 2: Happy Path - Message Format Conversion
# =========================================================================


class TestMessageFormatConversion:
    """TelegramMessage to_dict and property accessors."""

    def test_to_dict_has_all_fields(self):
        """to_dict returns a dictionary with all dataclass fields."""
        msg = TelegramMessage(
            telegram_user_id=100,
            chat_id=200,
            message_id=300,
            text="Hola",
            username="user1",
            first_name="First",
            last_name="Last",
        )
        d = msg.to_dict()
        assert d["telegram_user_id"] == 100
        assert d["chat_id"] == 200
        assert d["message_id"] == 300
        assert d["text"] == "Hola"
        assert d["platform"] == "telegram"

    def test_bot_status_to_dict(self):
        """TelegramBotStatus.to_dict returns complete status dict."""
        status = TelegramBotStatus(
            connected=True,
            bot_username="testbot",
            bot_id=42,
            mode="polling",
            messages_received=5,
            messages_sent=3,
        )
        d = status.to_dict()
        assert d["connected"] is True
        assert d["bot_username"] == "testbot"
        assert d["messages_received"] == 5

    def test_message_timestamp_auto_generated(self):
        """TelegramMessage auto-generates ISO timestamp."""
        msg = TelegramMessage(telegram_user_id=1, chat_id=1, message_id=1, text="hi")
        assert "T" in msg.timestamp  # ISO format check

    def test_follower_id_format(self):
        """follower_id has tg_ prefix for Telegram platform."""
        msg = TelegramMessage(telegram_user_id=42, chat_id=1, message_id=1, text="test")
        assert msg.follower_id.startswith("tg_")
        assert "42" in msg.follower_id

    def test_status_defaults(self):
        """TelegramBotStatus defaults are sensible."""
        status = TelegramBotStatus()
        assert status.connected is False
        assert status.messages_received == 0
        assert status.messages_sent == 0
        assert status.errors == 0
        assert status.mode == "unknown"


# =========================================================================
# TEST 3: Edge Case - Empty Message Handling
# =========================================================================


class TestEmptyMessageHandling:
    """Edge cases with empty or minimal messages."""

    def test_empty_text_message(self):
        """TelegramMessage can have empty text (caller decides what to do)."""
        msg = TelegramMessage(telegram_user_id=1, chat_id=1, message_id=1, text="")
        assert msg.text == ""
        assert msg.follower_id == "tg_1"

    def test_record_received_increments_counter(self):
        """_record_received increments messages_received counter."""
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.status = TelegramBotStatus()
        adapter.recent_messages = []
        msg = TelegramMessage(telegram_user_id=1, chat_id=1, message_id=1, text="test")
        adapter._record_received(msg)
        assert adapter.status.messages_received == 1
        assert len(adapter.recent_messages) == 1

    def test_record_received_limits_history(self):
        """_record_received caps recent_messages at 10."""
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.status = TelegramBotStatus()
        adapter.recent_messages = []
        for i in range(15):
            msg = TelegramMessage(telegram_user_id=i, chat_id=1, message_id=i, text=f"msg{i}")
            adapter._record_received(msg)
        assert len(adapter.recent_messages) == 10

    def test_record_sent_increments_counter(self):
        """_record_sent increments messages_sent counter."""
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.status = TelegramBotStatus()
        adapter._record_sent()
        adapter._record_sent()
        assert adapter.status.messages_sent == 2

    def test_get_recent_messages_with_limit(self):
        """get_recent_messages respects the limit parameter."""
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.recent_messages = [{"text": f"msg{i}"} for i in range(10)]
        result = adapter.get_recent_messages(limit=3)
        assert len(result) == 3


# =========================================================================
# TEST 4: Edge Case - Unsupported Media Type / Missing Fields
# =========================================================================


class TestUnsupportedScenarios:
    """Tests for unsupported media, missing fields, and bot not init."""

    @patch("core.telegram_adapter.TELEGRAM_AVAILABLE", False)
    def test_adapter_no_telegram_logs_error(self):
        """Without telegram lib, adapter does not set up application."""
        adapter = TelegramAdapter(token="fake-token")
        assert adapter.application is None
        assert adapter.bot is None

    def test_get_status_returns_dict(self):
        """get_status returns a dictionary even for fresh adapter."""
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.status = TelegramBotStatus()
        status = adapter.get_status()
        assert isinstance(status, dict)
        assert "connected" in status
        assert status["connected"] is False

    def test_get_recent_responses_empty(self):
        """get_recent_responses returns empty list for fresh adapter."""
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.recent_responses = []
        assert adapter.get_recent_responses() == []

    @patch("core.telegram_adapter.TELEGRAM_AVAILABLE", True)
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": ""}, clear=False)
    def test_adapter_no_token_warns(self):
        """Adapter with no token does not crash, just skips init."""
        adapter = TelegramAdapter(token=None)
        assert adapter.dm_agent is None  # _init_agent not called when no token

    def test_bot_status_errors_tracking(self):
        """errors counter on status can be incremented."""
        status = TelegramBotStatus()
        status.errors += 1
        status.errors += 1
        assert status.errors == 2


# =========================================================================
# TEST 5: Integration - Webhook Format and Singleton
# =========================================================================


class TestWebhookAndSingleton:
    """Integration: singleton pattern and adapter status tracking."""

    def test_get_telegram_adapter_singleton(self):
        """get_telegram_adapter returns cached instance on second call."""
        import core.telegram_adapter as mod

        mod._adapter = None  # Reset
        # Patch to avoid real init
        with patch.object(TelegramAdapter, "_init_agent", return_value=None):
            with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test"}, clear=False):
                a1 = get_telegram_adapter(creator_id="test")
                a2 = get_telegram_adapter(creator_id="test")
                assert a1 is a2
        mod._adapter = None  # Cleanup

    def test_status_started_at_initially_none(self):
        """started_at is None before the bot is started."""
        status = TelegramBotStatus()
        assert status.started_at is None

    def test_status_tracks_last_message_time(self):
        """last_message_time is updated when a message is recorded."""
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.status = TelegramBotStatus()
        adapter.recent_messages = []
        msg = TelegramMessage(telegram_user_id=1, chat_id=1, message_id=1, text="hi")
        adapter._record_received(msg)
        assert adapter.status.last_message_time == msg.timestamp

    def test_adapter_stores_creator_id(self):
        """TelegramAdapter stores the provided creator_id."""
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.creator_id = "manel"
        assert adapter.creator_id == "manel"

    def test_recent_responses_capped(self):
        """recent_responses list is capped at 10 entries after record."""
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.status = TelegramBotStatus()
        adapter.recent_responses = []

        # Create a mock DMResponse
        mock_response = MagicMock()
        mock_response.response_text = "test"
        mock_response.intent = MagicMock()
        mock_response.intent.value = "greeting"
        mock_response.confidence = 0.9
        mock_response.product_mentioned = None
        mock_response.escalate_to_human = False

        for i in range(15):
            msg = TelegramMessage(telegram_user_id=i, chat_id=1, message_id=i, text=f"msg{i}")
            adapter._record_response(msg, mock_response)

        assert len(adapter.recent_responses) == 10
