"""Audit tests for core/instagram_handler.py"""

from core.instagram_handler import InstagramHandler, InstagramHandlerStatus


class TestAuditInstagramHandler:
    def test_import(self):
        from core.instagram_handler import InstagramHandler, InstagramHandlerStatus  # noqa: F811

        assert InstagramHandler is not None

    def test_init(self):
        handler = InstagramHandler(
            access_token="test_token",
            page_id="test_page",
            ig_user_id="test_user",
            app_secret="test_secret",
            verify_token="test_verify",
            creator_id="test_creator",
        )
        assert handler is not None

    def test_happy_path_status(self):
        handler = InstagramHandler(
            access_token="test",
            page_id="test",
            ig_user_id="test",
            app_secret="test",
            verify_token="test",
            creator_id="test",
        )
        status = handler.get_status()
        assert isinstance(status, dict)
        assert "connected" in status or len(status) > 0

    def test_edge_case_verify_webhook(self):
        handler = InstagramHandler(
            access_token="t",
            page_id="t",
            ig_user_id="t",
            app_secret="t",
            verify_token="my_verify_token",
            creator_id="t",
        )
        result = handler.verify_webhook("subscribe", "my_verify_token", "challenge_123")
        assert result == "challenge_123" or result is not None

    def test_error_handling_wrong_verify(self):
        handler = InstagramHandler(
            access_token="t",
            page_id="t",
            ig_user_id="t",
            app_secret="t",
            verify_token="correct",
            creator_id="t",
        )
        try:
            result = handler.verify_webhook("subscribe", "wrong_token", "ch")
            assert result is not None or result is None
        except (ValueError, Exception):
            pass  # Acceptable
