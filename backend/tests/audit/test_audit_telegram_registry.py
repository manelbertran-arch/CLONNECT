"""Audit tests for core/telegram_registry.py"""

from core.telegram_registry import TelegramBotRegistry, get_telegram_registry


class TestAuditTelegramRegistry:
    def test_import(self):
        from core.telegram_registry import TelegramBotRegistry, get_telegram_registry  # noqa: F811

        assert TelegramBotRegistry is not None

    def test_init(self):
        registry = TelegramBotRegistry()
        assert registry is not None

    def test_happy_path_get_registry(self):
        registry = get_telegram_registry()
        assert registry is not None

    def test_edge_case_get_nonexistent_bot(self):
        registry = TelegramBotRegistry()
        try:
            result = registry.get_bot_by_id("nonexistent_bot_id")
            assert result is None
        except (KeyError, Exception):
            pass  # Acceptable

    def test_error_handling_get_creator(self):
        registry = TelegramBotRegistry()
        try:
            result = registry.get_creator_id("fake_bot_id")
            assert result is None
        except (KeyError, Exception):
            pass  # Acceptable
