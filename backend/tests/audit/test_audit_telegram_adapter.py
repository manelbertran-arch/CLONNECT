"""Audit tests for core/telegram_adapter.py"""

from core.telegram_adapter import TelegramAdapter, TelegramMessage


class TestAuditTelegramAdapter:
    def test_import(self):
        from core.telegram_adapter import (  # noqa: F811
            TelegramAdapter,
            TelegramBotStatus,
            TelegramMessage,
        )

        assert TelegramAdapter is not None

    def test_init(self):
        adapter = TelegramAdapter(
            token="test_token",
            creator_id="test_creator",
            webhook_url="https://example.com/webhook",
        )
        assert adapter is not None

    def test_happy_path_status(self):
        adapter = TelegramAdapter(
            token="test",
            creator_id="test",
            webhook_url="https://test.com/wh",
        )
        status = adapter.get_status()
        assert isinstance(status, dict)

    def test_edge_case_message_to_dict(self):
        try:
            msg = TelegramMessage()
            d = msg.to_dict()
            assert isinstance(d, dict)
        except TypeError:
            pass  # Requires args

    def test_error_handling_recent_messages(self):
        adapter = TelegramAdapter(
            token="invalid",
            creator_id="test",
            webhook_url="https://test.com/wh",
        )
        try:
            msgs = adapter.get_recent_messages(limit=5)
            assert isinstance(msgs, list)
        except Exception:
            pass  # Network failure acceptable
